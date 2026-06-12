"""弹性与可靠性模块 - 超时保护、错误分类、熔断器、上下文预算分配

提供 UIAI 框架运行时的核心可靠性保障：
1. ActionTimeout — 三层超时保护（动作/步骤/LLM）
2. 错误分类体系 — 自动识别瞬态/持续/基础设施/业务错误
3. CircuitBreaker — 熔断器，防止级联故障
4. ContextBudget — 上下文窗口预算分配与截断
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. ActionTimeout — 三层超时保护
# ═══════════════════════════════════════════════════════════════


@dataclass
class TimeoutConfig:
    """超时配置

    三层超时从内到外：LLM 调用 → 单个动作 → 完整步骤（含 LLM 推理）。
    """

    action_timeout: float = 180.0   # 单个动作最大执行时间(秒)
    step_timeout: float = 300.0     # 单步(含LLM推理)最大时间(秒)
    llm_timeout: float = 90.0       # LLM调用最大等待时间(秒)


class ActionTimeout:
    """三层超时保护

    为 UI 自动化的不同粒度操作提供超时包装：
    - wrap_llm:   LLM 接口调用（最内层，超时最短）
    - wrap_action: 单个浏览器动作（中间层）
    - wrap_step:   完整测试步骤，含 LLM 推理 + 动作执行（最外层，超时最长）
    """

    def __init__(self, config: TimeoutConfig | None = None) -> None:
        self._config = config or TimeoutConfig()

    async def wrap_action(self, coro: Coroutine, action_name: str = "") -> Any:
        """包装单个动作，添加超时保护

        Args:
            coro: 待执行的协程。
            action_name: 动作名称，用于日志标识。

        Returns:
            协程执行结果。

        Raises:
            asyncio.TimeoutError: 动作执行超时。
        """
        label = action_name or "action"
        try:
            return await asyncio.wait_for(coro, timeout=self._config.action_timeout)
        except asyncio.TimeoutError:
            logger.warning("ActionTimeout: 动作 '%s' 超时 (%.1fs)", label, self._config.action_timeout)
            raise

    async def wrap_step(self, coro: Coroutine, step_name: str = "") -> Any:
        """包装完整步骤，添加超时保护

        Args:
            coro: 待执行的协程。
            step_name: 步骤名称，用于日志标识。

        Returns:
            协程执行结果。

        Raises:
            asyncio.TimeoutError: 步骤执行超时。
        """
        label = step_name or "step"
        try:
            return await asyncio.wait_for(coro, timeout=self._config.step_timeout)
        except asyncio.TimeoutError:
            logger.warning("ActionTimeout: 步骤 '%s' 超时 (%.1fs)", label, self._config.step_timeout)
            raise

    async def wrap_llm(self, coro: Coroutine, model: str = "") -> Any:
        """包装 LLM 调用，添加超时保护

        Args:
            coro: 待执行的协程。
            model: 模型名称，用于日志标识。

        Returns:
            协程执行结果。

        Raises:
            asyncio.TimeoutError: LLM 调用超时。
        """
        label = model or "llm"
        try:
            return await asyncio.wait_for(coro, timeout=self._config.llm_timeout)
        except asyncio.TimeoutError:
            logger.warning("ActionTimeout: LLM '%s' 调用超时 (%.1fs)", label, self._config.llm_timeout)
            raise


# ═══════════════════════════════════════════════════════════════
# 2. 错误分类体系
# ═══════════════════════════════════════════════════════════════


class ErrorCategory(Enum):
    """错误类别枚举"""

    TRANSIENT = "transient"             # 短暂可恢复(网络超时、限流)
    PERSISTENT = "persistent"           # 持续性(元素不存在、断言失败)
    INFRASTRUCTURE = "infrastructure"   # 基础设施(浏览器崩溃、OOM)
    BUSINESS = "business"               # 业务逻辑(数据不一致、权限不足)


class UIAIError(Exception):
    """UIAI 统一错误基类

    所有框架内异常均应转换为 UIAIError 或其子类，
    携带错误类别、可恢复标记和上下文信息。
    """

    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.PERSISTENT,
        recoverable: bool = False,
        context: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.recoverable = recoverable
        self.context = context or {}

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.args[0]!r}, "
            f"category={self.category.value!r}, "
            f"recoverable={self.recoverable})"
        )


class TransientError(UIAIError):
    """短暂可恢复错误

    网络超时、连接中断、限流(429/503)等，通常可通过重试恢复。
    """

    def __init__(self, message: str = "", *, context: dict | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.TRANSIENT,
            recoverable=True,
            context=context,
        )


class PersistentError(UIAIError):
    """持续性错误

    元素不存在、断言失败、404 等，重试无法恢复。
    """

    def __init__(self, message: str = "", *, context: dict | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.PERSISTENT,
            recoverable=False,
            context=context,
        )


class InfrastructureError(UIAIError):
    """基础设施错误

    浏览器崩溃、OOM、进程退出等，需要重启基础设施后可恢复。
    """

    def __init__(self, message: str = "", *, context: dict | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.INFRASTRUCTURE,
            recoverable=True,
            context=context,
        )


class BusinessError(UIAIError):
    """业务逻辑错误

    数据不一致、权限不足、参数错误等，不可自动恢复。
    """

    def __init__(self, message: str = "", *, context: dict | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.BUSINESS,
            recoverable=False,
            context=context,
        )


# ── 错误分类规则 ──────────────────────────────────────────────

# 瞬态错误：超时 / 连接错误 / 限流
_TRANSIENT_PATTERNS: list[str] = [
    r"timeout",
    r"timed?\s*out",
    r"connection\s*(error|reset|refused|aborted|closed)",
    r"network\s*(error|unreachable)",
    r"429",                             # Too Many Requests
    r"503",                             # Service Unavailable
    r"rate\s*limit",
    r"retry",
    r"temporary",
    r"socket\s*(error|closed)",
]

# 持续性错误：元素不存在 / 断言失败 / 404
_PERSISTENT_PATTERNS: list[str] = [
    r"nosuchelement",
    r"no\s*such\s*element",
    r"element\s*not\s*found",
    r"element\s*not\s*interactable",
    r"stale\s*element",
    r"assertion\s*(error|failed)",
    r"assert\s*failed",
    r"404",
    r"not\s*found",
    r"selector\s*.*\s*(invalid|not\s*match)",
]

# 基础设施错误：崩溃 / OOM / 进程退出
_INFRASTRUCTURE_PATTERNS: list[str] = [
    r"crash",
    r"browser\s*(crash|closed|disconnected)",
    r"oom",
    r"out\s*of\s*memory",
    r"process\s*exit",
    r"segmentation\s*fault",
    r"renderer\s*.*\s*(crash|killed)",
    r"target\s*closed",
    r"disconnected",
]

# 业务错误：权限 / 数据不一致 / 参数错误
_BUSINESS_PATTERNS: list[str] = [
    r"permission\s*denied",
    r"forbidden",
    r"unauthorized",
    r"access\s*denied",
    r"value\s*error",
    r"data\s*inconsisten",
    r"invalid\s*(parameter|argument|input)",
    r"403",
    r"401",
]

# 编译正则
_TRANSIENT_RE = re.compile("|".join(_TRANSIENT_PATTERNS), re.IGNORECASE)
_PERSISTENT_RE = re.compile("|".join(_PERSISTENT_PATTERNS), re.IGNORECASE)
_INFRASTRUCTURE_RE = re.compile("|".join(_INFRASTRUCTURE_PATTERNS), re.IGNORECASE)
_BUSINESS_RE = re.compile("|".join(_BUSINESS_PATTERNS), re.IGNORECASE)

# 异常类型到错误类别的映射
_TRANSIENT_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    ConnectionRefusedError,
    ConnectionAbortedError,
    BrokenPipeError,
)

_PERSISTENT_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    AssertionError,
    FileNotFoundError,
    KeyError,
    LookupError,
)

_BUSINESS_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    PermissionError,
    ValueError,
)


def classify_error(error: Exception) -> UIAIError:
    """自动分类异常，返回对应的 UIAIError 子类

    分类优先级：
    1. 已是 UIAIError → 直接返回
    2. 异常类型精确匹配
    3. 错误消息正则匹配（按 基础设施 → 瞬态 → 持续 → 业务 优先级）
    4. 无法识别 → PersistentError

    Args:
        error: 原始异常。

    Returns:
        对应的 UIAIError 子类实例，保留原始异常链。
    """
    # 已经是 UIAIError，直接返回
    if isinstance(error, UIAIError):
        return error

    message = str(error)
    context: dict[str, Any] = {
        "original_type": type(error).__name__,
        "original_message": message,
    }

    # 按异常类型精确匹配
    if isinstance(error, _INFRASTRUCTURE_EXCEPTION_TYPES):
        return InfrastructureError(message, context=context)
    if isinstance(error, _TRANSIENT_EXCEPTION_TYPES):
        return TransientError(message, context=context)
    if isinstance(error, _BUSINESS_EXCEPTION_TYPES):
        return BusinessError(message, context=context)
    if isinstance(error, _PERSISTENT_EXCEPTION_TYPES):
        return PersistentError(message, context=context)

    # 按错误消息正则匹配（基础设施优先，因为 crash 等关键词更关键）
    if _INFRASTRUCTURE_RE.search(message):
        return InfrastructureError(message, context=context)
    if _TRANSIENT_RE.search(message):
        return TransientError(message, context=context)
    if _PERSISTENT_RE.search(message):
        return PersistentError(message, context=context)
    if _BUSINESS_RE.search(message):
        return BusinessError(message, context=context)

    # 无法识别 → 默认持续性错误
    logger.debug("classify_error: 无法识别的错误类型 '%s'，默认归类为 PersistentError", type(error).__name__)
    return PersistentError(message, context=context)


# ═══════════════════════════════════════════════════════════════
# 3. CircuitBreaker — 熔断器
# ═══════════════════════════════════════════════════════════════


class CircuitState(Enum):
    """熔断器状态"""

    CLOSED = "closed"          # 正常
    OPEN = "open"              # 熔断
    HALF_OPEN = "half_open"    # 半开(试探)


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""

    failure_threshold: int = 5       # 连续失败次数阈值
    recovery_timeout: float = 30.0   # 熔断恢复超时(秒)
    half_open_max_calls: int = 3     # 半开状态最大试探调用数


class CircuitBreakerOpenError(UIAIError):
    """熔断器开启时拒绝调用的错误"""

    def __init__(self, name: str, *, context: dict | None = None) -> None:
        super().__init__(
            f"熔断器 '{name}' 处于开启状态，拒绝调用",
            category=ErrorCategory.INFRASTRUCTURE,
            recoverable=True,
            context=context or {},
        )
        self.circuit_name = name


class CircuitBreaker:
    """熔断器：防止级联故障

    状态转换：
    - CLOSED → 正常运行，累计连续失败次数；达到阈值 → OPEN
    - OPEN   → 拒绝所有调用；经过 recovery_timeout → HALF_OPEN
    - HALF_OPEN → 允许有限次试探调用；成功 → CLOSED，失败 → OPEN
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._total_failures: int = 0
        self._total_successes: int = 0
        self._last_failure_time: float | None = None
        self._half_open_calls: int = 0

    @property
    def state(self) -> CircuitState:
        """当前熔断器状态（自动检查是否应从 OPEN 转为 HALF_OPEN）"""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._config.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_open(self) -> bool:
        """熔断器是否处于开启（拒绝）状态"""
        return self.state == CircuitState.OPEN

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """通过熔断器调用函数

        Args:
            fn: 待调用的可调用对象（支持同步和异步）。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            函数执行结果。

        Raises:
            CircuitBreakerOpenError: 熔断器处于 OPEN 状态时拒绝调用。
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(self._name)

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self._config.half_open_max_calls:
                # 半开状态下试探调用数已满，视为熔断
                raise CircuitBreakerOpenError(self._name)
            self._half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def record_success(self) -> None:
        """记录一次成功调用"""
        self._success_count += 1
        self._total_successes += 1

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下成功 → 关闭熔断器
            self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            # 正常状态下成功，重置连续失败计数
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录一次失败调用"""
        self._failure_count += 1
        self._total_failures += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下失败 → 重新开启熔断器
            self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._config.failure_threshold:
                # 连续失败达到阈值 → 开启熔断器
                self._transition_to(CircuitState.OPEN)

    def reset(self) -> None:
        """重置熔断器到关闭状态"""
        self._transition_to(CircuitState.CLOSED)

    @property
    def stats(self) -> dict[str, Any]:
        """获取熔断器统计信息"""
        return {
            "state": self.state.value,
            "failures": self._total_failures,
            "successes": self._total_successes,
            "consecutive_failures": self._failure_count,
            "last_failure_time": self._last_failure_time,
        }

    def _transition_to(self, new_state: CircuitState) -> None:
        """状态转换

        Args:
            new_state: 目标状态。
        """
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state

        # 转换时重置对应计数器
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            self._half_open_calls = 0

        logger.info(
            "CircuitBreaker '%s': 状态转换 %s → %s",
            self._name, old_state.value, new_state.value,
        )


# ═══════════════════════════════════════════════════════════════
# 4. ContextBudget — 上下文窗口预算分配
# ═══════════════════════════════════════════════════════════════


@dataclass
class BudgetConfig:
    """上下文预算配置

    各比例之和应为 1.0，分配器会自动归一化处理。
    """

    total_tokens: int = 8000
    system_ratio: float = 0.10       # 10% 系统提示词
    rag_ratio: float = 0.15          # 15% 业务RAG知识
    perception_ratio: float = 0.40   # 40% 页面感知信息
    history_ratio: float = 0.25      # 25% 历史操作记录
    dynamic_ratio: float = 0.10      # 10% 动态预留


# 简易 token 估算：中文约 1.5 字符/token，英文约 4 字符/token
# 取折中值 2 字符/token 作为粗略估算
_CHARS_PER_TOKEN: int = 2


class ContextBudget:
    """上下文窗口预算分配器

    将有限的 LLM 上下文窗口按比例分配给五个区域，
    并提供截断功能确保各区域内容不超预算。
    """

    def __init__(self, config: BudgetConfig | None = None) -> None:
        self._config = config or BudgetConfig()

    def allocate(self) -> dict[str, int]:
        """计算各区域的 token 预算

        自动归一化比例，确保各区域预算之和不超过 total_tokens。

        Returns:
            各区域 token 预算字典 {system, rag, perception, history, dynamic}。
        """
        cfg = self._config
        ratios = {
            "system": cfg.system_ratio,
            "rag": cfg.rag_ratio,
            "perception": cfg.perception_ratio,
            "history": cfg.history_ratio,
            "dynamic": cfg.dynamic_ratio,
        }

        # 归一化
        total_ratio = sum(ratios.values())
        if total_ratio <= 0:
            # 比例全为零时等分
            equal = cfg.total_tokens // len(ratios)
            return {k: equal for k in ratios}

        allocated: dict[str, int] = {}
        remaining = cfg.total_tokens

        for name, ratio in ratios.items():
            normalized = ratio / total_ratio
            tokens = int(cfg.total_tokens * normalized)
            allocated[name] = tokens
            remaining -= tokens

        # 将余量分配给最大比例区域（通常是 perception）
        max_key = max(ratios, key=ratios.get)
        allocated[max_key] += remaining

        return allocated

    def fit_content(
        self,
        system: str,
        rag: str,
        perception: str,
        history: str,
        dynamic: str,
    ) -> dict[str, str]:
        """将各区域内容截断至预算范围内

        Args:
            system: 系统提示词内容。
            rag: RAG 知识内容。
            perception: 页面感知内容。
            history: 历史操作记录。
            dynamic: 动态预留内容。

        Returns:
            截断后的各区域内容字典。
        """
        budgets = self.allocate()
        sections = {
            "system": system,
            "rag": rag,
            "perception": perception,
            "history": history,
            "dynamic": dynamic,
        }

        result: dict[str, str] = {}
        for name, content in sections.items():
            max_tokens = budgets[name]
            result[name] = self._truncate(content, max_tokens)

        return result

    def _truncate(self, text: str, max_tokens: int) -> str:
        """将文本截断至指定 token 预算内

        使用字符/token 比例粗略估算，在安全边界处截断。
        截断时在末尾添加省略标记。

        Args:
            text: 待截断文本。
            max_tokens: 最大 token 数。

        Returns:
            截断后的文本。
        """
        if not text:
            return ""

        max_chars = max_tokens * _CHARS_PER_TOKEN

        if len(text) <= max_chars:
            return text

        # 预留省略标记的空间
        ellipsis = "...[截断]"
        truncated_len = max_chars - len(ellipsis)
        if truncated_len <= 0:
            return ellipsis

        return text[:truncated_len] + ellipsis
