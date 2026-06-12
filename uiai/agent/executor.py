"""ExecutorAgent — 执行Agent，核心Agent循环（感知-决策-执行）"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from uiai.agent.base import AgentOutput as BaseAgentOutput
from uiai.agent.base import AgentRole, AgentState, BaseAgent
from uiai.agent.llm import BaseLLMClient, LLMMessage
from uiai.agent.loop_detector import LoopDetector
from uiai.core.perception import PerceptionEngine, PerceptionMode, PerceptionResult

if TYPE_CHECKING:
    from uiai.executor.base import BaseExecutor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class FlashMode(Enum):
    """快速模式枚举

    STANDARD: 完整输出（所有字段）
    FLASH: 快速输出（仅 memory + action）
    """

    STANDARD = "standard"
    FLASH = "flash"


@dataclass
class ActionModel:
    """动作模型

    Attributes:
        action_type: 动作类型，如 click、input、scroll 等
        params: 动作参数字典
        description: 动作的自然语言描述
    """

    action_type: str
    params: dict[str, Any]
    description: str


@dataclass
class ExecutorOutput:
    """执行Agent增强输出

    Attributes:
        thinking: 内部思考
        evaluation_previous_goal: 评估上一步执行结果
        memory: 跨步记忆，在步骤间传递关键信息
        next_goal: 下一步目标
        action: 动作列表（每步可执行多个动作）
        is_done: 目标是否完成
        current_plan_item: 当前计划项索引
        plan_update: 计划更新列表
        structured_output: 结构化输出（如提取的数据）
    """

    thinking: Optional[str] = None
    evaluation_previous_goal: Optional[str] = None
    memory: Optional[str] = None
    next_goal: Optional[str] = None
    action: list[ActionModel] = field(default_factory=list)
    is_done: bool = False
    current_plan_item: Optional[int] = None
    plan_update: Optional[list[str]] = None
    structured_output: Optional[dict[str, Any]] = None


@dataclass
class ActionResult:
    """动作执行结果

    Attributes:
        is_done: 该动作是否标志着任务完成
        success: 动作是否执行成功
        error: 执行错误信息
        extracted_content: 动作提取的内容（如文本值）
    """

    is_done: bool
    success: Optional[bool] = None
    error: Optional[str] = None
    extracted_content: Optional[str] = None


@dataclass
class StepResult:
    """单步执行结果

    Attributes:
        step_number: 步骤编号
        perception: 感知结果
        agent_output: Agent决策输出
        action_results: 动作执行结果列表
        duration_seconds: 该步骤耗时（秒）
        timestamp: 步骤开始时间戳
    """

    step_number: int
    perception: Optional[PerceptionResult] = None
    agent_output: Optional[ExecutorOutput] = None
    action_results: list[ActionResult] = field(default_factory=list)
    duration_seconds: float = 0.0
    timestamp: float = field(default_factory=time.time)


class AgentHistory:
    """Agent执行历史

    存储所有步骤结果，提供聚合查询方法。
    """

    def __init__(self) -> None:
        self._steps: list[StepResult] = []
        self._start_time: float = time.time()
        self._end_time: Optional[float] = None

    def add_step(self, step: StepResult) -> None:
        """添加步骤结果"""
        self._steps.append(step)

    def mark_done(self) -> None:
        """标记执行结束"""
        self._end_time = time.time()

    def final_result(self) -> Optional[ExecutorOutput]:
        """获取最终步骤的Agent输出"""
        if not self._steps:
            return None
        return self._steps[-1].agent_output

    def is_successful(self) -> bool:
        """判断任务是否成功完成"""
        final = self.final_result()
        if final is None:
            return False
        return final.is_done

    def errors(self) -> list[str]:
        """收集所有步骤中的错误信息"""
        error_list: list[str] = []
        for step in self._steps:
            for ar in step.action_results:
                if ar.error:
                    error_list.append(f"Step {step.step_number}: {ar.error}")
        return error_list

    def number_of_steps(self) -> int:
        """返回总步骤数"""
        return len(self._steps)

    def total_duration_seconds(self) -> float:
        """返回总耗时（秒）"""
        end = self._end_time or time.time()
        return end - self._start_time

    @property
    def steps(self) -> list[StepResult]:
        """获取所有步骤结果"""
        return self._steps

    @staticmethod
    def _is_step_successful(step: StepResult) -> bool:
        """判断步骤是否成功（所有动作结果均为成功）"""
        if not step.action_results:
            return False
        return all(ar.success is True for ar in step.action_results)

    @staticmethod
    def _get_step_action_types(step: StepResult) -> list[str]:
        """获取步骤中的所有动作类型"""
        if step.agent_output and step.agent_output.action:
            return [a.action_type for a in step.agent_output.action]
        return []

    def query(self, action_type: str | None = None, success: bool | None = None) -> list[StepResult]:
        """查询步骤结果，支持按动作类型和成功状态过滤"""
        results = self._steps
        if action_type is not None:
            results = [s for s in results if action_type in self._get_step_action_types(s)]
        if success is not None:
            results = [s for s in results if self._is_step_successful(s) == success]
        return results

    def get_step(self, index: int) -> StepResult | None:
        """获取指定步骤"""
        if 0 <= index < len(self._steps):
            return self._steps[index]
        return None

    def get_timeline(self) -> list[dict]:
        """获取执行时间线"""
        timeline = []
        for i, step in enumerate(self._steps):
            action_types = self._get_step_action_types(step)
            timeline.append({
                "step": i,
                "action_types": action_types,
                "success": self._is_step_successful(step),
                "duration_ms": step.duration_seconds * 1000,
                "timestamp": datetime.fromtimestamp(step.timestamp).isoformat() if step.timestamp else None,
            })
        return timeline

    def aggregate(self) -> dict:
        """聚合统计信息"""
        total = len(self._steps)
        succeeded = sum(1 for s in self._steps if self._is_step_successful(s))
        failed = total - succeeded
        total_duration_ms = sum(s.duration_seconds * 1000 for s in self._steps)
        by_action: dict[str, dict[str, int]] = {}
        for s in self._steps:
            for at in self._get_step_action_types(s):
                by_action.setdefault(at, {"count": 0, "success": 0})
                by_action[at]["count"] += 1
                if self._is_step_successful(s):
                    by_action[at]["success"] += 1
        return {
            "total_steps": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": succeeded / total if total > 0 else 0,
            "total_duration_ms": total_duration_ms,
            "avg_duration_ms": total_duration_ms / total if total > 0 else 0,
            "by_action_type": by_action,
        }


# ---------------------------------------------------------------------------
# 系统提示模板
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_STANDARD = """\
你是一个UI自动化执行Agent。你的任务是根据页面状态和用户目标，决定下一步操作。

你必须严格按照以下JSON格式输出：
{
  "thinking": "你的内部思考过程（分析页面状态、推理下一步）",
  "evaluation_previous_goal": "对上一步执行结果的评估（成功/失败/部分成功及原因）",
  "memory": "跨步骤记忆（需要记住的关键信息，如已完成的步骤、中间结果）",
  "next_goal": "下一步的具体目标",
  "action": [
    {
      "action_type": "动作类型",
      "params": {"参数名": "参数值"},
      "description": "动作描述"
    }
  ],
  "is_done": false,
  "current_plan_item": null,
  "plan_update": null,
  "structured_output": null
}

可用动作类型：
- navigate: 导航到URL，params: {"url": "..."}
- click: 点击元素，params: {"selector": "...", "index": 0}
- input: 输入文本，params: {"selector": "...", "text": "...", "clear": true}
- scroll: 滚动页面，params: {"direction": "down|up", "amount": 300}
- press_key: 按键，params: {"key": "Enter|Tab|Escape"}
- select_option: 选择下拉选项，params: {"selector": "...", "value": "..."}
- wait: 等待，params: {"seconds": 2}
- extract: 提取数据，params: {"selector": "...", "attribute": "textContent"}
- go_back: 浏览器后退，params: {}
- done: 任务完成，params: {"reason": "完成原因"}

规则：
1. 每步最多执行 {max_actions} 个动作
2. 优先使用 a11y snapshot 中的元素信息定位
3. 如果遇到循环或重复失败，尝试不同策略
4. is_done 为 true 时表示任务完成，无需继续
"""

_SYSTEM_PROMPT_FLASH = """\
你是UI自动化执行Agent（快速模式）。仅输出记忆和动作。

JSON格式：
{
  "memory": "跨步骤记忆",
  "action": [
    {
      "action_type": "动作类型",
      "params": {"参数名": "参数值"},
      "description": "动作描述"
    }
  ],
  "is_done": false
}

可用动作类型同标准模式。每步最多 {max_actions} 个动作。
"""


# ---------------------------------------------------------------------------
# ExecutorAgent
# ---------------------------------------------------------------------------


class ExecutorAgent(BaseAgent):
    """执行Agent — 核心Agent循环（感知-决策-执行）

    通过反复执行「感知页面状态 → LLM决策 → 执行动作」循环，
    逐步完成用户指定的任务。支持快速模式（减少LLM输出字段）、
    循环检测、初始动作等特性。
    """

    def __init__(
        self,
        executor: BaseExecutor,
        llm_client: BaseLLMClient,
        perception_engine: PerceptionEngine,
        loop_detector: LoopDetector,
        cache_manager: Optional[Any] = None,
        flash_mode: FlashMode = FlashMode.STANDARD,
        max_steps: int = 50,
        max_actions_per_step: int = 5,
        initial_actions: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        super().__init__(
            name="ExecutorAgent",
            role=AgentRole.EXECUTOR,
            llm_client=llm_client,
        )
        self._executor = executor
        self._perception_engine = perception_engine
        self._loop_detector = loop_detector
        self._cache_manager = cache_manager
        self._flash_mode = flash_mode
        self._max_steps = max_steps
        self._max_actions_per_step = max_actions_per_step
        self._initial_actions = initial_actions or []
        self._memory: Optional[str] = None
        self._plan: Optional[list[str]] = None
        self._current_plan_item: Optional[int] = None

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def run(self, task: str, **kwargs: Any) -> AgentHistory:
        """执行Agent主循环

        流程：
            1. 执行初始动作（如有）
            2. 循环：感知 → 决策 → 执行 → 后处理
            3. 终止条件：任务完成 / 达到最大步数 / 连续失败超限

        Args:
            task: 用户任务描述
            **kwargs: 扩展参数

        Returns:
            AgentHistory 执行历史
        """
        self.state = AgentState.RUNNING
        history = AgentHistory()
        self._loop_detector.reset()
        self._memory = None

        try:
            # 执行初始动作
            await self._execute_initial_actions()

            for step_num in range(1, self._max_steps + 1):
                step_start = time.time()
                logger.info("步骤 %d/%d 开始", step_num, self._max_steps)

                # 1. 感知
                perception = await self._prepare_context()

                # 2. 决策
                agent_output = await self._get_next_action(task, perception)

                # 3. 执行
                action_results = await self._execute_actions(agent_output.action)

                step_duration = time.time() - step_start
                step_result = StepResult(
                    step_number=step_num,
                    perception=perception,
                    agent_output=agent_output,
                    action_results=action_results,
                    duration_seconds=step_duration,
                )
                history.add_step(step_result)

                # 更新跨步记忆
                if agent_output.memory:
                    self._memory = agent_output.memory
                if agent_output.plan_update:
                    self._plan = agent_output.plan_update
                if agent_output.current_plan_item is not None:
                    self._current_plan_item = agent_output.current_plan_item

                # 4. 后处理（循环检测等）
                await self._post_process(action_results)

                # 检查终止条件
                if agent_output.is_done:
                    logger.info("任务完成，共 %d 步", step_num)
                    self.state = AgentState.COMPLETED
                    break

                if self._loop_detector.check_failure_limit():
                    logger.warning("连续失败次数超限，终止执行")
                    self.state = AgentState.FAILED
                    break
            else:
                logger.warning("达到最大步数 %d，终止执行", self._max_steps)
                self.state = AgentState.FAILED

        except Exception as exc:
            self.state = AgentState.FAILED
            logger.exception("ExecutorAgent 执行异常: %s", exc)
        finally:
            history.mark_done()

        return history

    # ------------------------------------------------------------------
    # 感知
    # ------------------------------------------------------------------

    async def _prepare_context(self) -> PerceptionResult:
        """感知当前页面状态

        Returns:
            感知结果
        """
        return await self._perception_engine.perceive()

    # ------------------------------------------------------------------
    # 决策
    # ------------------------------------------------------------------

    async def _get_next_action(
        self, task: str, perception: PerceptionResult
    ) -> ExecutorOutput:
        """通过LLM决策下一步动作

        Args:
            task: 用户任务描述
            perception: 当前页面感知结果

        Returns:
            Agent决策输出
        """
        system_prompt = self._build_system_prompt(self._flash_mode)
        user_message = self._build_user_message(task, perception)

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_message),
        ]

        # 如果有截图，使用多模态对话
        if perception.screenshot:
            raw_output = await self.llm_client.chat_with_images(
                messages, [perception.screenshot]
            )
        else:
            raw_output = await self.llm_client.chat(messages)

        return self._parse_llm_output(raw_output)

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def _execute_actions(self, actions: list[ActionModel]) -> list[ActionResult]:
        """执行动作列表

        按顺序执行每个动作，记录结果。单个动作失败不阻断后续动作。

        Args:
            actions: 待执行的动作列表

        Returns:
            动作执行结果列表
        """
        results: list[ActionResult] = []

        for action in actions[: self._max_actions_per_step]:
            result = await self._execute_single_action(action)
            results.append(result)

            # 记录动作到循环检测器
            self._loop_detector.record_action(action.action_type, action.params)

            # 如果动作标记任务完成，直接返回
            if result.is_done:
                break

        return results

    async def _execute_single_action(self, action: ActionModel) -> ActionResult:
        """执行单个动作

        Args:
            action: 待执行的动作

        Returns:
            动作执行结果
        """
        from uiai.core.locator import Locator

        action_type = action.action_type
        params = action.params

        try:
            match action_type:
                case "navigate":
                    await self._executor.navigate(params["url"])
                    return ActionResult(is_done=False, success=True)

                case "click":
                    locator = Locator(css=params.get("selector", ""))
                    index = params.get("index", 0)
                    if index > 0:
                        # 通过索引定位第N个匹配元素
                        locator = Locator(css=f"{params.get('selector', '')}:nth-of-type({index + 1})")
                    await self._executor.click(locator)
                    return ActionResult(is_done=False, success=True)

                case "input":
                    locator = Locator(css=params.get("selector", ""))
                    text = params.get("text", "")
                    clear = params.get("clear", True)
                    await self._executor.type_text(locator, text, clear=clear)
                    return ActionResult(is_done=False, success=True)

                case "scroll":
                    direction = params.get("direction", "down")
                    amount = params.get("amount", 300)
                    scroll_y = amount if direction == "down" else -amount
                    await self._executor.evaluate(f"window.scrollBy(0, {scroll_y})")
                    return ActionResult(is_done=False, success=True)

                case "press_key":
                    key = params.get("key", "Enter")
                    await self._executor.press_key(key)
                    return ActionResult(is_done=False, success=True)

                case "select_option":
                    locator = Locator(css=params.get("selector", ""))
                    value = params.get("value", "")
                    await self._executor.select_option(locator, value)
                    return ActionResult(is_done=False, success=True)

                case "wait":
                    seconds = params.get("seconds", 2)
                    import asyncio
                    await asyncio.sleep(seconds)
                    return ActionResult(is_done=False, success=True)

                case "extract":
                    locator = Locator(css=params.get("selector", ""))
                    attribute = params.get("attribute", "textContent")
                    if attribute == "textContent":
                        content = await self._executor.get_text(locator)
                    else:
                        content = await self._executor.evaluate(
                            f'document.querySelector("{params.get("selector", "")}")?.getAttribute("{attribute}")'
                        )
                    return ActionResult(
                        is_done=False,
                        success=True,
                        extracted_content=str(content) if content else None,
                    )

                case "go_back":
                    await self._executor.go_back()
                    return ActionResult(is_done=False, success=True)

                case "done":
                    reason = params.get("reason", "任务完成")
                    return ActionResult(is_done=True, success=True, extracted_content=reason)

                case _:
                    logger.warning("未知动作类型: %s", action_type)
                    return ActionResult(
                        is_done=False, success=False, error=f"未知动作类型: {action_type}"
                    )

        except Exception as exc:
            logger.error("动作执行失败 [%s]: %s", action_type, exc)
            self._loop_detector.record_failure()
            return ActionResult(is_done=False, success=False, error=str(exc))

    # ------------------------------------------------------------------
    # 后处理
    # ------------------------------------------------------------------

    async def _post_process(self, results: list[ActionResult]) -> None:
        """后处理：循环检测、页面状态记录

        Args:
            results: 动作执行结果列表
        """
        # 记录页面状态到循环检测器
        try:
            url = await self._executor.get_url()
            a11y_tree = await self._executor.get_accessibility_tree()
            element_count = len(a11y_tree.get("children", [])) if isinstance(a11y_tree, dict) else 0
            page_text = str(a11y_tree) if a11y_tree else ""
            self._loop_detector.record_page_state(url, element_count, page_text)
        except Exception:
            logger.debug("记录页面状态失败，跳过")

        # 检查循环提示
        loop_warning = self._loop_detector.check_action_loop()
        if loop_warning:
            logger.warning(loop_warning)

        stall_warning = self._loop_detector.check_page_stall()
        if stall_warning:
            logger.warning(stall_warning)

        # 检查失败计数
        if self._loop_detector.check_failure_limit():
            logger.error("连续失败次数超限")

    # ------------------------------------------------------------------
    # 初始动作
    # ------------------------------------------------------------------

    async def _execute_initial_actions(self) -> None:
        """执行确定性预置动作

        在Agent循环开始前执行，如打开特定URL、接受Cookie等。
        """
        if not self._initial_actions:
            return

        logger.info("执行 %d 个初始动作", len(self._initial_actions))
        for action_dict in self._initial_actions:
            action = ActionModel(
                action_type=action_dict.get("action_type", ""),
                params=action_dict.get("params", {}),
                description=action_dict.get("description", "初始动作"),
            )
            result = await self._execute_single_action(action)
            if result.error:
                logger.warning("初始动作执行失败: %s", result.error)
            else:
                logger.debug("初始动作完成: %s", action.action_type)

    # ------------------------------------------------------------------
    # 提示构建
    # ------------------------------------------------------------------

    def _build_system_prompt(self, flash_mode: FlashMode) -> str:
        """根据模式构建系统提示

        Args:
            flash_mode: 快速模式

        Returns:
            系统提示字符串
        """
        if flash_mode == FlashMode.FLASH:
            return _SYSTEM_PROMPT_FLASH.format(max_actions=self._max_actions_per_step)
        return _SYSTEM_PROMPT_STANDARD.format(max_actions=self._max_actions_per_step)

    def _build_user_message(self, task: str, perception: PerceptionResult) -> str:
        """构建用户消息

        组装任务描述、感知结果、循环提示、跨步记忆等信息。

        Args:
            task: 用户任务描述
            perception: 感知结果

        Returns:
            用户消息字符串
        """
        parts: list[str] = []

        # 任务描述
        parts.append(f"## 任务\n{task}")

        # 页面状态
        page_state = self._perception_engine.format_for_llm(perception)
        if page_state:
            parts.append(f"## 当前页面状态\n{page_state}")

        # 跨步记忆
        if self._memory:
            parts.append(f"## 记忆\n{self._memory}")

        # 当前计划
        if self._plan:
            plan_text = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(self._plan))
            parts.append(f"## 当前计划\n{plan_text}")
            if self._current_plan_item is not None:
                parts.append(f"当前计划项: {self._current_plan_item + 1}")

        # 循环检测提示
        hints = self._loop_detector.get_loop_hints()
        if hints:
            parts.append("## ⚠️ 循环检测提示\n" + "\n".join(f"- {h}" for h in hints))

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # LLM输出解析
    # ------------------------------------------------------------------

    def _parse_llm_output(self, raw_output: str) -> ExecutorOutput:
        """解析LLM响应为AgentOutput

        尝试从LLM原始输出中提取JSON，解析为结构化的ExecutorOutput。
        支持Markdown代码块包裹的JSON。

        Args:
            raw_output: LLM原始输出文本

        Returns:
            解析后的ExecutorOutput
        """
        # 尝试提取JSON（处理Markdown代码块包裹的情况）
        json_str = self._extract_json(raw_output)

        if json_str is None:
            logger.warning("无法从LLM输出中提取JSON，原始输出: %s", raw_output[:200])
            return ExecutorOutput(
                thinking="LLM输出解析失败",
                next_goal="等待重新决策",
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.warning("JSON解析失败: %s，原始内容: %s", exc, json_str[:200])
            return ExecutorOutput(
                thinking=f"JSON解析失败: {exc}",
                next_goal="等待重新决策",
            )

        # 解析动作列表
        actions: list[ActionModel] = []
        for action_data in data.get("action", []):
            if isinstance(action_data, dict):
                actions.append(
                    ActionModel(
                        action_type=action_data.get("action_type", ""),
                        params=action_data.get("params", {}),
                        description=action_data.get("description", ""),
                    )
                )

        return ExecutorOutput(
            thinking=data.get("thinking"),
            evaluation_previous_goal=data.get("evaluation_previous_goal"),
            memory=data.get("memory"),
            next_goal=data.get("next_goal"),
            action=actions,
            is_done=bool(data.get("is_done", False)),
            current_plan_item=data.get("current_plan_item"),
            plan_update=data.get("plan_update"),
            structured_output=data.get("structured_output"),
        )

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从文本中提取JSON字符串

        支持以下格式：
            1. 纯JSON
            2. Markdown代码块包裹的JSON（```json ... ```）
            3. 混合文本中的JSON对象

        Args:
            text: 待提取文本

        Returns:
            提取到的JSON字符串，未找到则返回None
        """
        # 尝试提取Markdown代码块中的JSON
        import re

        code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()

        # 尝试直接解析整个文本
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped

        # 尝试查找文本中的JSON对象
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)

        return None
