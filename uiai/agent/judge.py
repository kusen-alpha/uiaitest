"""JudgeAgent — 独立评估Agent，用独立LLM评估执行结果"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from uiai.agent.base import AgentOutput, AgentRole, AgentState, BaseAgent
from uiai.agent.llm import BaseLLMClient, LLMMessage

if TYPE_CHECKING:
    from uiai.agent.executor import AgentHistory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class JudgementResult:
    """评判结果

    Attributes:
        reasoning: 评判理由，详细说明为何做出此判断
        verdict: 是否成功完成用户任务
        failure_reason: 失败原因（verdict 为 False 时填写）
        impossible_task: 任务是否不可能完成（如目标网站不可达、功能不存在）
        reached_captcha: 是否遇到验证码阻碍
    """

    reasoning: Optional[str] = None
    verdict: bool = False
    failure_reason: Optional[str] = None
    impossible_task: bool = False
    reached_captcha: bool = False


# ---------------------------------------------------------------------------
# 评判提示模板
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = """\
你是一个独立的UI自动化任务评判Agent。你的职责是客观评估执行Agent是否成功完成了用户任务。

你必须严格按照以下JSON格式输出：
{
  "reasoning": "详细的评判理由（分析执行历史、最终页面状态、是否达成目标）",
  "verdict": true或false,
  "failure_reason": "如果verdict为false，说明失败的具体原因",
  "impossible_task": false,
  "reached_captcha": false
}

评判标准：
1. 用户的原始任务是否被完整完成
2. 最终页面状态是否符合预期
3. 执行过程中是否存在未解决的错误
4. 是否因为外部原因（验证码、网站不可达等）导致无法完成

注意：
- 你必须独立、客观地评判，不受执行Agent自我评估的影响
- 如果任务部分完成，verdict 应为 false，并在 failure_reason 中说明未完成部分
- impossible_task 仅在任务本身不可行时设为 true（如网站不存在该功能）
- reached_captcha 仅在遇到验证码阻碍时设为 true
"""

_JUDGE_USER_PROMPT_TEMPLATE = """\
## 用户任务
{task}

## 执行历史摘要
{history_summary}

请根据以上信息，客观评判任务是否成功完成。"""


# ---------------------------------------------------------------------------
# JudgeAgent
# ---------------------------------------------------------------------------


class JudgeAgent(BaseAgent):
    """独立评估Agent

    使用独立的LLM实例评估ExecutorAgent的执行结果，
    避免自我评估偏差。支持增量重试：仅对评判失败的部分重新评估。
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        max_retries: int = 2,
    ) -> None:
        """初始化JudgeAgent

        Args:
            llm_client: 独立的LLM客户端实例，应与执行Agent使用不同的模型或配置
            max_retries: 最大重试次数，默认2次
        """
        super().__init__(
            name="JudgeAgent",
            role=AgentRole.JUDGE,
            llm_client=llm_client,
        )
        self._max_retries = max_retries

    async def run(
        self, task: str, execution_history: AgentHistory, **kwargs: Any
    ) -> JudgementResult:
        """评估执行结果

        Args:
            task: 用户原始任务描述
            execution_history: ExecutorAgent的执行历史
            **kwargs: 扩展参数，支持 screenshots (list[bytes]) 传入截图

        Returns:
            JudgementResult 评判结果
        """
        self.state = AgentState.RUNNING

        try:
            # 生成执行历史摘要
            history_summary = self._summarize_history(execution_history)

            # 收集截图
            screenshots: list[bytes] = kwargs.get("screenshots", [])
            if not screenshots:
                screenshots = self._collect_screenshots(execution_history)

            # 评估（带重试）
            result = await self._evaluate_with_retries(task, history_summary, screenshots)

            self.state = AgentState.COMPLETED
            return result

        except Exception as exc:
            self.state = AgentState.FAILED
            logger.exception("JudgeAgent 评估异常: %s", exc)
            return JudgementResult(
                reasoning=f"评估过程异常: {exc}",
                verdict=False,
                failure_reason=f"评估异常: {exc}",
            )

    async def _evaluate_with_retries(
        self,
        task: str,
        history_summary: str,
        screenshots: list[bytes],
    ) -> JudgementResult:
        """带增量重试的评估

        如果首次评估的 verdict 为 false 且 failure_reason 不明确，
        则进行增量重试，仅重新评估不确定的部分。

        Args:
            task: 用户任务描述
            history_summary: 执行历史摘要
            screenshots: 截图列表

        Returns:
            最终评判结果
        """
        result = await self._evaluate(task, history_summary, screenshots)

        for retry_num in range(1, self._max_retries + 1):
            # 仅在结果不确定时重试
            if not result.verdict and self._is_inconclusive(result):
                logger.info("评判结果不确定，进行第 %d 次重试", retry_num)

                # 增量提示：聚焦于失败原因
                incremental_summary = self._build_incremental_summary(
                    history_summary, result
                )
                retry_result = await self._evaluate(
                    task, incremental_summary, screenshots
                )

                # 合并结果：如果重试后 verdict 变为 true，采用重试结果
                if retry_result.verdict:
                    result = retry_result
                    break

                # 否则保留更详细的失败原因
                if retry_result.failure_reason and (
                    not result.failure_reason
                    or len(retry_result.failure_reason) > len(result.failure_reason)
                ):
                    result = retry_result
            else:
                break

        return result

    async def _evaluate(
        self,
        task: str,
        history_summary: str,
        screenshots: list[bytes],
    ) -> JudgementResult:
        """执行一次评估

        Args:
            task: 用户任务描述
            history_summary: 执行历史摘要
            screenshots: 截图列表

        Returns:
            评判结果
        """
        judge_prompt = self._build_judge_prompt(task, history_summary)

        messages = [
            LLMMessage(role="system", content=_JUDGE_SYSTEM_PROMPT),
            LLMMessage(role="user", content=judge_prompt),
        ]

        # 如果有截图，使用多模态对话
        if screenshots:
            raw_output = await self.llm_client.chat_with_images(
                messages, screenshots
            )
        else:
            raw_output = await self.llm_client.chat(messages)

        return self._parse_judgement(raw_output)

    def _build_judge_prompt(self, task: str, history_summary: str) -> str:
        """构建评判提示

        Args:
            task: 用户任务描述
            history_summary: 执行历史摘要

        Returns:
            评判提示字符串
        """
        return _JUDGE_USER_PROMPT_TEMPLATE.format(
            task=task,
            history_summary=history_summary,
        )

    def _parse_judgement(self, raw_output: str) -> JudgementResult:
        """解析LLM评判输出为JudgementResult

        Args:
            raw_output: LLM原始输出

        Returns:
            解析后的评判结果
        """
        json_str = self._extract_json(raw_output)

        if json_str is None:
            logger.warning("无法从评判输出中提取JSON: %s", raw_output[:200])
            return JudgementResult(
                reasoning="评判输出解析失败",
                verdict=False,
                failure_reason="无法解析评判结果",
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.warning("评判JSON解析失败: %s", exc)
            return JudgementResult(
                reasoning=f"JSON解析失败: {exc}",
                verdict=False,
                failure_reason="评判结果格式错误",
            )

        return JudgementResult(
            reasoning=data.get("reasoning"),
            verdict=bool(data.get("verdict", False)),
            failure_reason=data.get("failure_reason"),
            impossible_task=bool(data.get("impossible_task", False)),
            reached_captcha=bool(data.get("reached_captcha", False)),
        )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_history(history: AgentHistory) -> str:
        """将执行历史摘要为文本

        包含：总步骤数、总耗时、每步的目标和结果、最终状态。

        Args:
            history: 执行历史

        Returns:
            历史摘要文本
        """
        parts: list[str] = []

        parts.append(f"总步骤数: {history.number_of_steps()}")
        parts.append(f"总耗时: {history.total_duration_seconds():.1f}秒")
        parts.append(f"最终状态: {'成功' if history.is_successful() else '未完成'}")

        # 逐步摘要
        for step in history.steps:
            step_parts: list[str] = [f"步骤 {step.step_number}"]

            if step.agent_output:
                if step.agent_output.next_goal:
                    step_parts.append(f"目标: {step.agent_output.next_goal}")
                if step.agent_output.evaluation_previous_goal:
                    step_parts.append(f"评估: {step.agent_output.evaluation_previous_goal}")

            # 动作结果
            for i, ar in enumerate(step.action_results):
                status = "✓" if ar.success else "✗"
                desc = ar.extracted_content or ar.error or ""
                step_parts.append(f"  动作{i + 1}: {status} {desc}")

            parts.append("\n".join(step_parts))

        # 错误汇总
        errors = history.errors()
        if errors:
            parts.append(f"\n错误汇总:\n" + "\n".join(f"- {e}" for e in errors))

        return "\n\n".join(parts)

    @staticmethod
    def _collect_screenshots(history: AgentHistory) -> list[bytes]:
        """从执行历史中收集截图

        优先收集最后几步的截图，避免发送过多图片。

        Args:
            history: 执行历史

        Returns:
            截图二进制数据列表
        """
        screenshots: list[bytes] = []
        # 收集最后3步的截图
        recent_steps = history.steps[-3:] if len(history.steps) > 3 else history.steps

        for step in recent_steps:
            if step.perception and step.perception.screenshot:
                screenshots.append(step.perception.screenshot)

        return screenshots

    @staticmethod
    def _is_inconclusive(result: JudgementResult) -> bool:
        """判断评判结果是否不确定

        不确定的情况：
            1. 缺少评判理由
            2. 失败原因为空或过于笼统
            3. 未标记为不可能任务或验证码，但也未成功

        Args:
            result: 评判结果

        Returns:
            是否不确定
        """
        if not result.reasoning or len(result.reasoning) < 10:
            return True
        if not result.verdict and not result.failure_reason:
            return True
        if (
            not result.verdict
            and not result.impossible_task
            and not result.reached_captcha
            and result.failure_reason
            and len(result.failure_reason) < 10
        ):
            return True
        return False

    @staticmethod
    def _build_incremental_summary(
        history_summary: str, previous_result: JudgementResult
    ) -> str:
        """构建增量评估摘要

        在重试时，聚焦于上次评判中不确定的部分。

        Args:
            history_summary: 原始历史摘要
            previous_result: 上次评判结果

        Returns:
            增量摘要文本
        """
        parts: list[str] = []

        parts.append(history_summary)
        parts.append(
            "\n--- 上次评判（需要重新确认）---\n"
            f"评判理由: {previous_result.reasoning or '无'}\n"
            f"判定: {'成功' if previous_result.verdict else '失败'}\n"
            f"失败原因: {previous_result.failure_reason or '无'}\n"
            f"不可能任务: {'是' if previous_result.impossible_task else '否'}\n"
            f"遇到验证码: {'是' if previous_result.reached_captcha else '否'}"
        )
        parts.append(
            "\n请重新仔细评估，特别关注：\n"
            "1. 任务是否确实未完成？是否有部分完成？\n"
            "2. 失败的具体原因是什么？\n"
            "3. 是否存在外部阻碍（验证码、网站不可达等）？"
        )

        return "\n\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从文本中提取JSON字符串

        Args:
            text: 待提取文本

        Returns:
            提取到的JSON字符串，未找到则返回None
        """
        # 尝试提取Markdown代码块中的JSON
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
