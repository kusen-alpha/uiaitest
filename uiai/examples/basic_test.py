"""UIAI 基础测试示例"""
import asyncio
from uiai.core.locator import Locator
from uiai.core.test_case import TestCase, TestStep, Priority
from uiai.core.platform import Platform
from uiai.config import UIAIConfig
from uiai.executor.factory import ExecutorFactory
from uiai.assertion.engine import AssertionEngine
from uiai.orchestrator.orchestrator import TestOrchestrator
from uiai.report.generator import ReportGenerator


async def basic_web_test():
    """基础Web测试示例"""
    # 1. 配置
    config = UIAIConfig(
        base_url="https://demo.playwright.dev/todomvc",
    )
    config.browser.headless = True

    # 2. 创建测试用例
    test = TestCase(
        id="todo-001",
        name="TodoMVC - 添加待办事项",
        priority=Priority.SMOKE,
    )
    test.add_step("导航到TodoMVC", "navigate", value=config.base_url)
    test.add_step("输入待办事项", "type_text", locator=Locator.by_placeholder("What needs to be done?"), value="Buy groceries")
    test.add_step("按回车确认", "press_key", value="Enter")
    test.add_step("验证待办已添加", "assert_visible", locator=Locator.by_text("Buy groceries"))

    # 3. 执行测试
    orchestrator = TestOrchestrator(config)
    result = await orchestrator.run_test(test)

    # 4. 生成报告
    from uiai.core.result import SuiteResult
    from datetime import datetime
    suite = SuiteResult(suite_name="todo-demo")
    suite.results.append(result)
    suite.end_time = datetime.now()

    report_gen = ReportGenerator("./reports")
    report_gen.generate_json_report(suite)
    report_gen.generate_html_report(suite)
    report_gen.generate_console_report(suite)

    return result


async def ai_plan_test():
    """AI生成测试计划示例"""
    config = UIAIConfig()
    # 配置LLM（根据实际环境修改）
    # config.llm.provider = "openai"
    # config.llm.api_key = "your-api-key"
    # config.llm.model = "gpt-4o"

    orchestrator = TestOrchestrator(config)

    # 生成测试计划
    result = await orchestrator.generate_test_plan(
        "测试TodoMVC应用的添加、完成、删除待办事项功能",
        url="https://demo.playwright.dev/todomvc",
    )

    if result.success:
        print(f"测试计划已生成: {result.artifacts.get('plan')}")
    else:
        print(f"生成失败: {result.message}")


if __name__ == "__main__":
    print("=== 基础Web测试 ===")
    asyncio.run(basic_web_test())

    # 取消注释以测试AI生成（需要配置LLM API Key）
    # print("\n=== AI生成测试计划 ===")
    # asyncio.run(ai_plan_test())
