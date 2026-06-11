"""Planner Agent - 分析需求，生成测试计划（增强版：RAG上下文 + 对话管理）"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from uiai.agent.base import BaseAgent, AgentOutput, AgentRole
from uiai.agent.llm import BaseLLMClient, LLMMessage
from uiai.agent.context import ContextManager

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """你是一个专业的测试规划师（Planner Agent），隶属于UIAI自动化测试框架。

## 你的职责
根据用户需求，生成详细的、可执行的测试计划。

## 输出格式要求（Markdown）

# {应用名称} - 测试计划

## 应用概述
简要描述应用的核心功能和测试范围。

## 测试场景

### 1. {场景名称}
**优先级：** P0/P1/P2/P3
**前置条件：** ...
**步骤：**
1. 操作描述（使用语义化定位器）
2. ...
**预期结果：**
- ...

### 2. {场景名称}
...

## 边界条件与异常场景
- 场景1: ...
- 场景2: ...

## 定位器策略建议
- 优先使用 getByRole / getByTestId
- 避免使用 XPath
- 为动态内容提供文本匹配降级策略

## 注意事项
- 每个场景应独立可执行
- 考虑网络异常、超时、弹窗等干扰因素
- 包含正向和反向测试场景
"""


class PlannerAgent(BaseAgent):
    """规划Agent（增强版）

    输入：自然语言需求 / PRD文档
    输出：Markdown格式的测试计划

    增强：
    - RAG上下文：自动注入相关业务规则
    - 对话管理：支持多轮对话细化需求
    - 上下文窗口控制：在token预算内组装消息
    """

    def __init__(self, llm_client: BaseLLMClient | None = None, context_manager: ContextManager | None = None):
        super().__init__(name="PlannerAgent", role=AgentRole.PLANNER, llm_client=llm_client)
        self.context = context_manager or ContextManager()

    async def run(self, input_data: Any, **kwargs) -> AgentOutput:
        """生成测试计划"""
        if not self.llm_client:
            return AgentOutput(role=self.role, success=False, message="LLM client not configured")

        requirement = str(input_data)
        context = kwargs.get("context", "")
        output_dir = Path(kwargs.get("output_dir", "./test_plans"))

        # 记录用户输入
        self.context.add_turn("user", requirement)

        # 构建上下文消息（含RAG）
        messages_list = self.context.build_context_messages(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_query=requirement + (f"\n\n额外上下文：\n{context}" if context else ""),
            include_history=True,
            include_rag=True,
        )

        # 转为LLMMessage格式
        messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages_list]

        try:
            plan_content = await self.llm_client.chat(messages)

            # 记录AI输出
            self.context.add_turn("assistant", plan_content)

            # 保存测试计划
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            plan_path = output_dir / f"test_plan_{timestamp}.md"
            plan_path.write_text(plan_content, encoding="utf-8")

            logger.info(f"Test plan generated: {plan_path}")

            return AgentOutput(
                role=self.role,
                success=True,
                data=plan_content,
                message=f"Test plan generated: {plan_path}",
                artifacts={"plan": str(plan_path)},
                requires_approval=True,
                approval_data=plan_content,
            )
        except Exception as e:
            logger.error(f"Planner failed: {e}")
            return AgentOutput(role=self.role, success=False, message=f"Failed to generate test plan: {e}")
