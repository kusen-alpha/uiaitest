"""Healer Agent - 检测失败，自动修复测试（增强版：RAG上下文 + 多模态分析）"""
from __future__ import annotations
import logging
from typing import Any

from uiai.agent.base import BaseAgent, AgentOutput, AgentRole
from uiai.agent.llm import BaseLLMClient, LLMMessage
from uiai.agent.context import ContextManager
from uiai.core.result import TestResult, TestStatus

logger = logging.getLogger(__name__)

HEALER_SYSTEM_PROMPT = """你是一个测试自愈专家（Healer Agent），隶属于UIAI自动化测试框架。

## 修复策略优先级

1. **选择器降级**：getByTestId → getByRole → getByText → getByCSS → getByXPath
   - 适用于：元素选择器失效，但元素本身存在

2. **DOM邻近搜索**：查找父子兄弟节点的等价元素
   - 适用于：元素被重构/移动，但语义未变

3. **视觉OCR兜底**：使用OCR或图像匹配定位
   - 适用于：DOM结构完全变化，但视觉上元素仍存在

4. **AI代码修复**：调整等待策略、修改断言阈值、重写步骤
   - 适用于：业务逻辑变更导致的测试失败

## 输出格式

### 修复策略
使用的策略名称和原因

### 修复说明
具体修改内容，包括：
- 原始代码片段
- 修复后代码片段
- 修改原因

### 修复代码（diff格式）
```diff
- old_code
+ new_code
```

### 置信度
高/中/低 + 理由

### 风险评估
- 是否可能掩盖真实Bug
- 是否需要人工验证

⚠️ 重要：你只提供建议，不自动应用修复。所有修复需要人工审核。
"""


class HealerAgent(BaseAgent):
    """自愈Agent（增强版）

    输入：失败的测试结果 + 错误信息
    输出：修复建议（需人工审核）

    增强：
    - RAG上下文：注入业务规则帮助理解失败原因
    - 多模态分析：支持截图+DOM联合分析
    - 对话管理：支持多轮对话细化修复方案
    """

    def __init__(self, llm_client: BaseLLMClient | None = None, context_manager: ContextManager | None = None):
        super().__init__(name="HealerAgent", role=AgentRole.HEALER, llm_client=llm_client)
        self.context = context_manager or ContextManager()

    async def run(self, input_data: Any, **kwargs) -> AgentOutput:
        """分析失败并生成修复建议"""
        if not self.llm_client:
            return AgentOutput(role=self.role, success=False, message="LLM client not configured")

        failure_context = self._build_failure_context(input_data, **kwargs)

        # 记录用户输入
        self.context.add_turn("user", failure_context[:2000])  # 截断避免过长

        # 构建上下文消息
        messages_list = self.context.build_context_messages(
            system_prompt=HEALER_SYSTEM_PROMPT,
            user_query=failure_context,
            include_history=True,
            include_rag=True,
        )

        messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages_list]

        # 如果有截图，使用多模态
        screenshot = kwargs.get("screenshot")
        if screenshot:
            try:
                healing_suggestion = await self.llm_client.chat_with_images(messages, [screenshot])
            except Exception:
                healing_suggestion = await self.llm_client.chat(messages)
        else:
            healing_suggestion = await self.llm_client.chat(messages)

        # 记录AI输出
        self.context.add_turn("assistant", healing_suggestion[:1000])

        return AgentOutput(
            role=self.role,
            success=True,
            data=healing_suggestion,
            message="Healing suggestion generated",
            requires_approval=True,
            approval_data=healing_suggestion,
        )

    def _build_failure_context(self, input_data: Any, **kwargs) -> str:
        """构建失败上下文描述"""
        context_parts = ["## 测试失败信息\n"]

        if isinstance(input_data, TestResult):
            context_parts.append(f"- 测试名称: {input_data.test_name}")
            context_parts.append(f"- 状态: {input_data.status.value}")
            context_parts.append(f"- 错误信息: {input_data.error}")
            if input_data.traceback:
                context_parts.append(f"- 堆栈:\n```\n{input_data.traceback}\n```")
            for step in input_data.steps:
                if step.status.value == "failed":
                    context_parts.append(f"- 失败步骤: {step.name} - {step.error}")
        else:
            context_parts.append(f"- 错误信息: {str(input_data)}")

        if source_code := kwargs.get("source_code"):
            context_parts.append(f"\n## 原始测试代码\n```python\n{source_code}\n```")

        if dom_snapshot := kwargs.get("dom_snapshot"):
            # 截断过长的DOM快照
            truncated = dom_snapshot[:3000] + "..." if len(dom_snapshot) > 3000 else dom_snapshot
            context_parts.append(f"\n## DOM快照\n{truncated}")

        if network_errors := kwargs.get("network_errors"):
            context_parts.append(f"\n## 网络错误\n{network_errors}")

        if console_errors := kwargs.get("console_errors"):
            context_parts.append(f"\n## 控制台错误\n{console_errors}")

        context_parts.append("\n请分析失败原因并给出修复建议。")
        return "\n".join(context_parts)
