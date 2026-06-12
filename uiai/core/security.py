"""安全模块 - 敏感数据保护与LLM降级策略

提供两大核心能力：

1. SensitiveDataProtector — 敏感数据保护器
   参照 browser-use 的 sensitive_data 机制，对密码、Token、密钥等
   敏感信息进行脱敏（文本遮蔽/截图区域遮挡），确保日志、截图、
   LLM上下文中不泄露敏感数据，同时在执行时恢复原始值。

2. FallbackLLM — LLM降级客户端
   主备模型自动切换，当主模型遇到可恢复错误（限流、超时）时，
   自动降级到备用模型，保障测试流程不中断。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from uiai.agent.llm import BaseLLMClient

logger = logging.getLogger(__name__)


# ── 敏感数据保护 ─────────────────────────────────────────────


@dataclass
class SensitiveDataConfig:
    """敏感数据保护配置

    Attributes:
        sensitive_keys: 需要脱敏的键名列表，如 ["password", "token", "api_key", "secret"]
        mask_char: 文本脱敏替换字符
        visual_mask: 是否在截图中遮挡敏感区域
        mask_color: 截图遮挡颜色（十六进制）
    """

    sensitive_keys: list[str] = field(default_factory=lambda: [
        "password", "token", "api_key", "secret", "apikey",
        "access_token", "refresh_token", "private_key", "credential",
        "authorization", "cookie", "session_id",
    ])
    mask_char: str = "***"
    visual_mask: bool = True
    mask_color: str = "#000000"


class SensitiveDataProtector:
    """敏感数据保护器

    对字典、文本和截图中的敏感信息进行脱敏处理，
    确保敏感数据不会出现在日志、LLM上下文或截图中。

    使用示例::

        protector = SensitiveDataProtector()

        # 文本脱敏
        safe_text = protector.mask_text("password=abc123&token=xyz")

        # 字典脱敏
        safe_dict = protector.mask_dict({"username": "admin", "password": "secret123"})

        # 截图区域遮挡
        safe_screenshot = protector.mask_screenshot(screenshot_bytes, [
            {"x": 100, "y": 200, "width": 300, "height": 40}
        ])

        # 执行时恢复原始值
        original = protector.unmask_dict(safe_dict, {"username": "admin", "password": "secret123"})
    """

    def __init__(self, config: Optional[SensitiveDataConfig] = None) -> None:
        """初始化敏感数据保护器

        Args:
            config: 敏感数据配置，为None时使用默认配置
        """
        self._config = config or SensitiveDataConfig()
        self._key_patterns: set[str] = set(self._config.sensitive_keys)

    def mask_dict(self, data: dict) -> dict:
        """对字典中的敏感值进行脱敏

        递归遍历字典，将键名匹配敏感关键词的值替换为遮蔽字符。
        支持嵌套字典。

        Args:
            data: 原始字典

        Returns:
            脱敏后的字典副本
        """
        return self._mask_dict_recursive(data)

    def _mask_dict_recursive(self, data: dict) -> dict:
        """递归脱敏字典"""
        masked = {}
        for key, value in data.items():
            if isinstance(value, dict):
                masked[key] = self._mask_dict_recursive(value)
            elif isinstance(value, list):
                masked[key] = [
                    self._mask_dict_recursive(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif self.is_sensitive_key(str(key)):
                masked[key] = self._config.mask_char
            else:
                masked[key] = value
        return masked

    def mask_text(self, text: str, patterns: Optional[list[str]] = None) -> str:
        """对文本中的敏感模式进行脱敏

        默认检测常见敏感键值对模式（如 password=xxx, token: xxx），
        也可自定义额外的正则模式。

        Args:
            text: 原始文本
            patterns: 额外的正则模式列表

        Returns:
            脱敏后的文本
        """
        result = text

        # 默认敏感键值对模式：匹配 key=value 或 key: value 或 key":"value 等
        default_patterns = []
        for key in self._key_patterns:
            # 匹配 key=xxx, key:xxx, key": "xxx", key': 'xxx' 等常见格式
            default_patterns.append(
                rf'({key}\s*[=:]\s*["\']?)([^"\'\s,;&\}}\]]+)'
            )

        all_patterns = default_patterns + (patterns or [])

        for pattern in all_patterns:
            try:
                result = re.sub(
                    pattern,
                    rf'\1{self._config.mask_char}',
                    result,
                    flags=re.IGNORECASE,
                )
            except re.error:
                logger.warning("无效的正则模式，跳过: %s", pattern)

        return result

    def mask_screenshot(self, screenshot: bytes, regions: list[dict]) -> bytes:
        """对截图中的敏感区域进行遮挡

        在截图的指定区域绘制遮蔽色块，隐藏敏感信息。
        使用 Pillow 进行图像处理。

        Args:
            screenshot: 原始截图字节（PNG/JPEG格式）
            regions: 需要遮挡的区域列表，每个区域为
                     {"x": int, "y": int, "width": int, "height": int}

        Returns:
            遮挡后的截图字节
        """
        if not self._config.visual_mask or not regions:
            return screenshot

        try:
            from PIL import Image, ImageDraw
            import io
        except ImportError:
            logger.warning("Pillow未安装，无法进行截图遮挡。安装: pip install Pillow")
            return screenshot

        try:
            img = Image.open(io.BytesIO(screenshot))
            draw = ImageDraw.Draw(img)

            # 解析遮蔽颜色
            mask_color = self._parse_color(self._config.mask_color)

            for region in regions:
                x = region.get("x", 0)
                y = region.get("y", 0)
                w = region.get("width", 0)
                h = region.get("height", 0)
                if w > 0 and h > 0:
                    draw.rectangle([x, y, x + w, y + h], fill=mask_color)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        except Exception:
            logger.exception("截图遮挡处理失败，返回原图")
            return screenshot

    @staticmethod
    def _parse_color(hex_color: str) -> tuple[int, int, int]:
        """解析十六进制颜色为RGB元组

        Args:
            hex_color: 十六进制颜色，如 "#000000" 或 "000000"

        Returns:
            (R, G, B) 元组
        """
        hex_str = hex_color.lstrip("#")
        if len(hex_str) != 6:
            return (0, 0, 0)
        return (
            int(hex_str[0:2], 16),
            int(hex_str[2:4], 16),
            int(hex_str[4:6], 16),
        )

    def unmask_dict(self, masked_data: dict, original_data: dict) -> dict:
        """恢复脱敏字典中的原始值

        将脱敏后的字典中被遮蔽的值恢复为原始数据中的对应值，
        用于实际执行时还原敏感数据。

        Args:
            masked_data: 脱敏后的字典
            original_data: 原始字典

        Returns:
            恢复原始值后的字典
        """
        return self._unmask_dict_recursive(masked_data, original_data)

    def _unmask_dict_recursive(self, masked: dict, original: dict) -> dict:
        """递归恢复脱敏字典"""
        result = {}
        for key, value in masked.items():
            if key not in original:
                result[key] = value
                continue

            orig_value = original[key]
            if isinstance(value, dict) and isinstance(orig_value, dict):
                result[key] = self._unmask_dict_recursive(value, orig_value)
            elif isinstance(value, list) and isinstance(orig_value, list):
                result[key] = [
                    self._unmask_dict_recursive(v, o) if isinstance(v, dict) and isinstance(o, dict) else o
                    for v, o in zip(value, orig_value)
                ]
            elif value == self._config.mask_char and self.is_sensitive_key(str(key)):
                result[key] = orig_value
            else:
                result[key] = value
        return result

    def add_sensitive_key(self, key: str) -> None:
        """添加敏感键名

        Args:
            key: 需要脱敏的键名
        """
        self._key_patterns.add(key.lower())

    def remove_sensitive_key(self, key: str) -> None:
        """移除敏感键名

        Args:
            key: 不再需要脱敏的键名
        """
        self._key_patterns.discard(key.lower())

    def is_sensitive_key(self, key: str) -> bool:
        """判断键名是否为敏感键

        采用子串匹配策略：键名（小写）包含任一敏感关键词即判定为敏感。

        Args:
            key: 待判断的键名

        Returns:
            是否为敏感键
        """
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in self._key_patterns)


# ── LLM 降级策略 ─────────────────────────────────────────────


class FallbackLLM:
    """LLM降级客户端

    主备模型自动切换策略：优先使用主模型，当主模型遇到
    可恢复错误（限流、超时）时，自动降级到备用模型。

    使用示例::

        primary = OpenAIClient(config1)
        fallback = OllamaClient(config2)
        llm = FallbackLLM(primary, fallback, max_retries=2)

        # 自动降级
        result = await llm.chat(messages)
    """

    def __init__(
        self,
        primary: BaseLLMClient,
        fallback: BaseLLMClient,
        max_retries: int = 2,
    ) -> None:
        """初始化降级客户端

        Args:
            primary: 主LLM客户端
            fallback: 备用LLM客户端
            max_retries: 主模型最大重试次数（超过后降级到备用）
        """
        self._primary = primary
        self._fallback = fallback
        self._max_retries = max_retries

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """文本对话，主模型失败时自动降级

        先尝试主模型（最多 max_retries 次），若均失败且错误可恢复，
        则降级到备用模型。

        Args:
            messages: 消息列表
            **kwargs: 传递给LLM的额外参数

        Returns:
            LLM响应文本

        Raises:
            Exception: 主备模型均失败时抛出最后一次异常
        """
        last_error: Exception | None = None

        # 尝试主模型
        for attempt in range(1, self._max_retries + 1):
            try:
                return await self._primary.chat(messages, **kwargs)
            except Exception as e:
                last_error = e
                if not self._is_recoverable(e):
                    logger.warning("主模型遇到不可恢复错误，直接降级: %s", e)
                    break
                logger.warning(
                    "主模型调用失败（第%d/%d次）: %s",
                    attempt, self._max_retries, e,
                )

        # 降级到备用模型
        logger.info("降级到备用LLM模型")
        try:
            return await self._fallback.chat(messages, **kwargs)
        except Exception as fallback_error:
            logger.error("备用模型也失败: %s", fallback_error)
            raise last_error or fallback_error

    async def chat_with_images(
        self,
        messages: list[dict],
        images: list[bytes],
        **kwargs,
    ) -> str:
        """多模态对话，主模型失败时自动降级

        先尝试主模型（最多 max_retries 次），若均失败且错误可恢复，
        则降级到备用模型。

        Args:
            messages: 消息列表
            images: 图片字节列表
            **kwargs: 传递给LLM的额外参数

        Returns:
            LLM响应文本

        Raises:
            Exception: 主备模型均失败时抛出最后一次异常
        """
        last_error: Exception | None = None

        # 尝试主模型
        for attempt in range(1, self._max_retries + 1):
            try:
                return await self._primary.chat_with_images(messages, images, **kwargs)
            except Exception as e:
                last_error = e
                if not self._is_recoverable(e):
                    logger.warning("主模型遇到不可恢复错误，直接降级: %s", e)
                    break
                logger.warning(
                    "主模型多模态调用失败（第%d/%d次）: %s",
                    attempt, self._max_retries, e,
                )

        # 降级到备用模型
        logger.info("降级到备用LLM模型（多模态）")
        try:
            return await self._fallback.chat_with_images(messages, images, **kwargs)
        except Exception as fallback_error:
            logger.error("备用模型也失败（多模态）: %s", fallback_error)
            raise last_error or fallback_error

    @staticmethod
    def _is_recoverable(error: Exception) -> bool:
        """判断错误是否可恢复

        可恢复错误包括：限流（429）、超时、服务端临时错误（5xx）等。
        不可恢复错误包括：认证失败、参数错误等。

        Args:
            error: 异常对象

        Returns:
            是否为可恢复错误
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # 限流 / 超时 / 服务端临时错误
        recoverable_keywords = [
            "rate limit",
            "rate_limit",
            "429",
            "timeout",
            "timed out",
            "connection",
            "server error",
            "500",
            "502",
            "503",
            "504",
            "overloaded",
            "capacity",
            "too many requests",
            "retry",
        ]

        # 认证 / 参数错误等不可恢复
        unrecoverable_keywords = [
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "invalid api key",
            "invalid_api_key",
            "authentication",
            "invalid request",
            "invalid_request",
            "model not found",
        ]

        # 先检查不可恢复
        for keyword in unrecoverable_keywords:
            if keyword in error_str or keyword in error_type:
                return False

        # 再检查可恢复
        for keyword in recoverable_keywords:
            if keyword in error_str or keyword in error_type:
                return True

        # 未知错误默认视为可恢复（允许重试）
        return True
