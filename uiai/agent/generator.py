"""Generator Agent - 将测试计划转为可执行测试代码（增强版）"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from uiai.agent.base import BaseAgent, AgentOutput, AgentRole
from uiai.agent.llm import BaseLLMClient, LLMMessage
from uiai.agent.context import ContextManager

logger = logging.getLogger(__name__)

GENERATOR_SYSTEM_PROMPT = """你是一个专业的测试代码生成器（Generator Agent），隶属于UIAI自动化测试框架。

## 代码规范

1. 使用 uiai 框架的 Locator 和 Executor API
2. 优先使用语义化定位器：
   - Locator.by_role("button", name="登录")  # 最优先
   - Locator.by_test_id("submit-btn")         # 次优先
   - Locator.by_label("用户名")               # 表单元素
   - Locator.by_placeholder("请输入...")      # 输入框
   - Locator.by_text("欢迎")                  # 文本验证
   - Locator.by_css(".submit")                # 仅在以上不可用时
   - Locator.by_xpath("//...")                # 最后手段
3. 每个测试场景一个独立的 async 函数
4. 使用 AssertionEngine 进行断言
5. 添加中文注释说明每个步骤
6. 使用 try/finally 确保资源释放
7. 考虑等待策略和超时处理

## 代码模板

```python
import asyncio
from uiai.core.locator import Locator
from uiai.core.test_case import TestCase, TestStep, Priority
from uiai.executor.factory import ExecutorFactory
from uiai.assertion.engine import AssertionEngine
from uiai.config import UIAIConfig

async def test_scenario_name():
    config = UIAIConfig(base_url="TARGET_URL")
    executor = ExecutorFactory.create_web(config.browser)
    assertion = AssertionEngine(executor)

    try:
        await executor.start()
        await executor.navigate(config.base_url)

        # 步骤1: 操作描述
        await executor.click(Locator.by_role("button", name="登录"))

        # 步骤2: 输入数据
        await executor.type_text(Locator.by_label("用户名"), "test@example.com")

        # 断言
        result = await assertion.assert_visible(Locator.by_text("欢迎"))
        assert result.passed, result.message

    finally:
        await executor.stop()

if __name__ == "__main__":
    asyncio.run(test_scenario_name())
```

## Page Object模式（推荐）

```python
from uiai.core.page_object import BasePage
from uiai.core.locator import Locator

class LoginPage(BasePage):
    username_input = Locator.by_placeholder("用户名")
    password_input = Locator.by_placeholder("密码")
    login_button = Locator.by_role("button", name="登录")
    error_message = Locator.by_role("alert")

    async def login(self, username: str, password: str) -> None:
        await self.type_text(self.username_input, username)
        await self.type_text(self.password_input, password)
        await self.click(self.login_button)

    async def should_show_error(self) -> None:
        await self.should_be_visible(self.error_message)
```
"""


class GeneratorAgent(BaseAgent):
    """代码生成Agent（增强版）

    输入：Markdown测试计划
    输出：可执行的Python测试代码

    增强：
    - RAG上下文：注入业务规则和平台文档
    - 对话管理：支持多轮对话修改代码
    - 更完善的代码模板和规范
    """

    def __init__(self, llm_client: BaseLLMClient | None = None, context_manager: ContextManager | None = None):
        super().__init__(name="GeneratorAgent", role=AgentRole.GENERATOR, llm_client=llm_client)
        self.context = context_manager or ContextManager()

    async def run(self, input_data: Any, **kwargs) -> AgentOutput:
        """生成测试代码"""
        if not self.llm_client:
            return AgentOutput(role=self.role, success=False, message="LLM client not configured")

        plan_content = str(input_data)
        base_url = kwargs.get("base_url", "http://localhost:3000")
        output_dir = Path(kwargs.get("output_dir", "./generated_tests"))

        # 记录用户输入
        self.context.add_turn("user", f"请根据以下测试计划生成Python测试代码：\n\n{plan_content}")

        # 构建上下文消息
        user_query = f"""请将以下测试计划转为可执行的Python测试代码：

目标应用URL: {base_url}

测试计划：
{plan_content}

请生成完整的、可直接运行的测试代码。优先使用Page Object模式。"""

        messages_list = self.context.build_context_messages(
            system_prompt=GENERATOR_SYSTEM_PROMPT,
            user_query=user_query,
            include_history=True,
            include_rag=True,
        )

        messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages_list]

        try:
            code_content = await self.llm_client.chat(messages)
            code = self._extract_code(code_content)

            # 记录AI输出
            self.context.add_turn("assistant", code)

            # 保存测试代码
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            code_path = output_dir / f"test_generated_{timestamp}.py"
            code_path.write_text(code, encoding="utf-8")

            logger.info(f"Test code generated: {code_path}")

            return AgentOutput(
                role=self.role,
                success=True,
                data=code,
                message=f"Test code generated: {code_path}",
                artifacts={"code": str(code_path)},
                requires_approval=True,
                approval_data=code,
            )
        except Exception as e:
            logger.error(f"Generator failed: {e}")
            return AgentOutput(role=self.role, success=False, message=f"Failed to generate test code: {e}")

    def _extract_code(self, content: str) -> str:
        """从LLM输出中提取代码块"""
        if "```python" in content:
            start = content.index("```python") + len("```python")
            end = content.index("```", start)
            return content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            return content[start:end].strip()
        return content
