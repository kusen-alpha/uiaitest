"""编排调度中控 - 统一管理Agent协作、任务调度、资源分配"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from uiai.config import UIAIConfig
from uiai.core.platform import Platform
from uiai.core.result import SuiteResult, TestResult, TestStatus, StepStatus
from uiai.core.test_case import TestCase, TestStep
from uiai.executor.base import BaseExecutor
from uiai.executor.factory import ExecutorFactory
from uiai.assertion.engine import AssertionEngine
from uiai.agent.base import BaseAgent, AgentRole, AgentOutput
from uiai.agent.llm import BaseLLMClient, create_llm_client
from uiai.orchestrator.agent_registry import AgentRegistry
from uiai.orchestrator.browser_pool import BrowserPool
from uiai.orchestrator.task_queue import TaskQueue, Task, TaskPriority

logger = logging.getLogger(__name__)


class TestOrchestrator:
    """测试编排调度中控

    核心职责：
    1. 管理Agent注册和协作
    2. 调度测试执行（确定性脚本 + AI辅助）
    3. 管理浏览器资源池
    4. 失败时触发AI自愈
    5. 收集结果，生成报告
    """

    def __init__(self, config: UIAIConfig | None = None):
        self.config = config or UIAIConfig()
        self.agent_registry = AgentRegistry()
        self.browser_pool = BrowserPool(
            max_size=self.config.parallel_workers,
            config=self.config.browser,
        )
        self.task_queue = TaskQueue(max_concurrent=self.config.parallel_workers)
        self._llm_client: BaseLLMClient | None = None
        self._audit_log: list[dict] = []

    @property
    def llm_client(self) -> BaseLLMClient | None:
        if self._llm_client is None and self.config.llm.api_key:
            self._llm_client = create_llm_client(self.config.llm)
        return self._llm_client

    def _log_audit(self, action: str, details: dict) -> None:
        """记录审计日志"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
        }
        self._audit_log.append(entry)
        logger.debug(f"Audit: {action} - {details}")

    # --- Agent管理 ---

    def register_agent(self, agent: BaseAgent) -> None:
        """注册Agent"""
        self.agent_registry.register(agent)
        self._log_audit("register_agent", {"name": agent.name, "role": agent.role.value})

    def _ensure_agents(self) -> None:
        """确保必要的Agent已注册"""
        if not self.agent_registry.get_by_role(AgentRole.PLANNER):
            from uiai.agent.planner import PlannerAgent
            self.register_agent(PlannerAgent(llm_client=self.llm_client))

        if not self.agent_registry.get_by_role(AgentRole.GENERATOR):
            from uiai.agent.generator import GeneratorAgent
            self.register_agent(GeneratorAgent(llm_client=self.llm_client))

        if not self.agent_registry.get_by_role(AgentRole.HEALER):
            from uiai.agent.healer import HealerAgent
            self.register_agent(HealerAgent(llm_client=self.llm_client))

    # --- 测试执行 ---

    async def run_test(self, test_case: TestCase, executor: BaseExecutor | None = None) -> TestResult:
        """执行单个测试用例

        Args:
            test_case: 测试用例
            executor: 执行器（不传则自动创建）
        """
        self._log_audit("run_test", {"test_id": test_case.id, "name": test_case.name})

        own_executor = executor is None
        if own_executor:
            executor = ExecutorFactory.create(Platform.WEB, self.config)
            await executor.start()

        result = TestResult(
            test_id=test_case.id,
            test_name=test_case.name,
            status=TestStatus.PASSED,
        )

        try:
            for step in test_case.steps:
                step_result = await self._execute_step(executor, step)
                result.steps.append(step_result)

                if step_result.status.value == "failed":
                    result.status = TestStatus.FAILED
                    result.error = step_result.error

                    # 触发自愈
                    if self.config.healing.enabled:
                        healed = await self._try_heal(executor, step, step_result, result)
                        if healed:
                            step_result.status = StepStatus.HEALED
                            step_result.healing_applied = "auto_healed"
                            result.status = TestStatus.HEALED
                            result.healing_records.append({
                                "step": step.name,
                                "strategy": "auto_heal",
                            })
                    break

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error = str(e)
        finally:
            result.duration_ms = sum(s.duration_ms for s in result.steps)
            if own_executor:
                await executor.stop()

        return result

    async def _execute_step(self, executor: BaseExecutor, step: TestStep):
        """执行单个测试步骤"""
        from uiai.core.result import StepResult, StepStatus
        import time

        start = time.time()
        step_result = StepResult(name=step.name, status=StepStatus.PASSED)

        try:
            action = step.action.lower()
            if action == "navigate":
                await executor.navigate(step.value or "")
            elif action == "click":
                await executor.click(step.locator)
            elif action in ("type", "type_text"):
                await executor.type_text(step.locator, step.value or "")
            elif action == "fill":
                await executor.fill(step.locator, step.value or "")
            elif action == "select":
                await executor.select_option(step.locator, step.value or "")
            elif action == "check":
                await executor.check(step.locator)
            elif action == "uncheck":
                await executor.uncheck(step.locator)
            elif action == "hover":
                await executor.hover(step.locator)
            elif action == "press_key":
                await executor.press_key(step.value or "Enter")
            elif action == "wait":
                await executor.wait_for(step.locator, timeout=step.options.get("timeout"))
            elif action == "screenshot":
                path = step.options.get("path")
                await executor.screenshot(path=path)
            elif action == "assert_visible":
                assertion_engine = AssertionEngine(executor)
                assertion_result = await assertion_engine.assert_visible(step.locator)
                if not assertion_result.passed:
                    step_result.status = StepStatus.FAILED
                    step_result.error = assertion_result.message
            elif action == "assert_text":
                assertion_engine = AssertionEngine(executor)
                assertion_result = await assertion_engine.assert_text_equals(
                    step.locator, step.value or ""
                )
                if not assertion_result.passed:
                    step_result.status = StepStatus.FAILED
                    step_result.error = assertion_result.message
            elif action == "assert_url":
                assertion_engine = AssertionEngine(executor)
                assertion_result = await assertion_engine.assert_url_equals(step.value or "")
                if not assertion_result.passed:
                    step_result.status = StepStatus.FAILED
                    step_result.error = assertion_result.message
            else:
                step_result.status = StepStatus.FAILED
                step_result.error = f"Unknown action: {action}"

        except Exception as e:
            step_result.status = StepStatus.FAILED
            step_result.error = str(e)

        step_result.duration_ms = (time.time() - start) * 1000
        return step_result

    async def _try_heal(self, executor: BaseExecutor, step: TestStep, step_result, test_result: TestResult) -> bool:
        """尝试自愈"""
        from uiai.healing.healer import HealingManager
        healer = HealingManager(self.config.healing, llm_client=self.llm_client)
        return await healer.try_heal(executor, step, step_result.error or "")

    async def run_suite(self, test_cases: list[TestCase], platform: Platform = Platform.WEB) -> SuiteResult:
        """执行测试套件"""
        suite_result = SuiteResult(suite_name="default")

        for tc in test_cases:
            result = await self.run_test(tc)
            suite_result.results.append(result)

        suite_result.end_time = datetime.now()
        self._log_audit("run_suite", suite_result.to_dict())
        return suite_result

    # --- AI能力入口 ---

    async def generate_test_plan(self, requirement: str, **kwargs) -> AgentOutput:
        """生成测试计划"""
        self._ensure_agents()
        planner = self.agent_registry.get_first_by_role(AgentRole.PLANNER)
        if planner:
            return await planner.execute(requirement, **kwargs)
        return AgentOutput(role=AgentRole.PLANNER, success=False, message="Planner not available")

    async def generate_test_code(self, plan: str, **kwargs) -> AgentOutput:
        """生成测试代码"""
        self._ensure_agents()
        generator = self.agent_registry.get_first_by_role(AgentRole.GENERATOR)
        if generator:
            return await generator.execute(plan, **kwargs)
        return AgentOutput(role=AgentRole.GENERATOR, success=False, message="Generator not available")

    async def heal_test(self, test_result: TestResult, **kwargs) -> AgentOutput:
        """自愈失败测试"""
        self._ensure_agents()
        healer = self.agent_registry.get_first_by_role(AgentRole.HEALER)
        if healer:
            return await healer.execute(test_result, **kwargs)
        return AgentOutput(role=AgentRole.HEALER, success=False, message="Healer not available")

    async def explore(self, url: str, **kwargs) -> AgentOutput:
        """AI探索性测试"""
        from uiai.agent.explorer import ExplorerAgent
        executor = ExecutorFactory.create(Platform.WEB, self.config)
        explorer = ExplorerAgent(llm_client=self.llm_client, executor=executor)
        return await explorer.execute(url, **kwargs)

    # --- 生命周期 ---

    async def shutdown(self) -> None:
        """关闭所有资源"""
        await self.browser_pool.close_all()
        self._log_audit("shutdown", {"total_audit_entries": len(self._audit_log)})
