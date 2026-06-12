"""编排调度中控 - 统一管理Agent协作、任务调度、资源分配

架构设计核心：
- 六Agent协作：PlannerAgent / ExecutorAgent / JudgeAgent / HealerAgent / ExplorerAgent / CodeRecorder
- 四层运行模式：R1_SCRIPT / R2_AGENT / R3_LOCAL_DEV
- 感知模式引擎：A11Y_SNAPSHOT / DOM_SERIALIZE / VISUAL_SCREENSHOT / HYBRID
- Watchdog守卫系统：9种守卫自动监控
- 三层缓存系统：PlanCache / LocateCache / FeatureCache
- 多模型意图路由：LOCATE→VL / PLAN→LLM / EXTRACT→轻量
- 知识沉淀系统：需求级 / 产品级 / 经验级
- Skill/Capability系统：技能注册 + 能力分组
- 检查点机制：崩溃恢复 + 状态回滚
- 安全保障：敏感数据脱敏 + FallbackLLM
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from uiai.config import UIAIConfig
from uiai.core.platform import Platform, PerceptionMode, RunTier
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
from uiai.core.eventbus import EventBus, Event, AgentEvent, WatchdogEvent, ExecutionEvent, get_event_bus
from uiai.core.perception import PerceptionEngine
from uiai.core.cache import CacheManager
from uiai.core.watchdog import (
    WatchdogManager, PopupWatchdog, CaptchaWatchdog, CrashWatchdog,
    SecurityWatchdog, NetworkWatchdog, StorageWatchdog, DownloadWatchdog,
    DomWatchdog, VisualAnomalyWatchdog,
)
from uiai.core.knowledge import KnowledgeManager
from uiai.core.skill import SkillRegistry
from uiai.core.capability import CapabilityManager, Capability, CapabilityConfig
from uiai.core.checkpoint import CheckpointManager
from uiai.core.security import SensitiveDataProtector, FallbackLLM
from uiai.agent.loop_detector import LoopDetector, LoopDetectorConfig
from uiai.agent.intent_router import IntentRouter, IntentType
from uiai.agent.message_compactor import MessageCompactor, CompactionConfig

logger = logging.getLogger(__name__)


class TestOrchestrator:
    """测试编排调度中控

    核心职责：
    1. 管理六Agent注册和协作
    2. 调度测试执行（R1脚本 / R2 Agent / R3本地开发）
    3. 管理浏览器资源池
    4. 失败时触发四层降级自愈
    5. Watchdog守卫自动监控
    6. 三层缓存加速执行
    7. 知识沉淀与经验积累
    8. 收集结果，生成报告
    """

    def __init__(self, config: UIAIConfig | None = None):
        self.config = config or UIAIConfig()

        # === 基础设施 ===
        self.event_bus: EventBus = get_event_bus()
        self.agent_registry = AgentRegistry()
        self.browser_pool = BrowserPool(
            max_size=self.config.parallel_workers,
            config=self.config.browser,
        )
        self.task_queue = TaskQueue(max_concurrent=self.config.parallel_workers)

        # === AI基础设施 ===
        self._llm_client: BaseLLMClient | None = None
        self._intent_router = IntentRouter()
        self._intent_router.set_default_models()
        self._message_compactor = MessageCompactor(CompactionConfig())

        # === 感知引擎 ===
        self._perception_engine: PerceptionEngine | None = None

        # === 缓存系统 ===
        self._cache_manager = CacheManager()

        # === Watchdog守卫 ===
        self._watchdog_manager = WatchdogManager(self.event_bus)

        # === 知识沉淀 ===
        self._knowledge_manager = KnowledgeManager()

        # === Skill/Capability ===
        self._skill_registry = SkillRegistry()
        self._skill_registry.register_defaults()
        self._capability_manager = CapabilityManager()

        # === 安全保障 ===
        self._sensitive_protector = SensitiveDataProtector()
        self._fallback_llm: FallbackLLM | None = None

        # === 检查点 ===
        self._checkpoint_manager: CheckpointManager | None = None

        # === 循环检测 ===
        self._loop_detector = LoopDetector()

        # === 审计日志 ===
        self._audit_log: list[dict] = []

        # === 运行状态 ===
        self._initialized = False

    @property
    def llm_client(self) -> BaseLLMClient | None:
        """获取LLM客户端（支持FallbackLLM）"""
        if self._llm_client is None and self.config.llm.api_key:
            primary = create_llm_client(self.config.llm)
            # 如果配置了备用模型，创建FallbackLLM
            if self.config.llm.fallback_model:
                from uiai.config import LLMConfig
                fallback_config = LLMConfig(
                    provider=self.config.llm.provider,
                    model=self.config.llm.fallback_model,
                    api_key=self.config.llm.api_key,
                    base_url=self.config.llm.base_url,
                )
                fallback = create_llm_client(fallback_config)
                self._fallback_llm = FallbackLLM(primary, fallback)
                self._llm_client = self._fallback_llm
            else:
                self._llm_client = primary
        return self._llm_client

    async def initialize(self) -> None:
        """初始化所有子系统"""
        if self._initialized:
            return

        # 启动Watchdog守卫
        self._watchdog_manager.register(PopupWatchdog())
        self._watchdog_manager.register(CaptchaWatchdog())
        self._watchdog_manager.register(CrashWatchdog())
        self._watchdog_manager.register(SecurityWatchdog(
            allowed_domains=self.config.browser.allowed_domains,
            prohibited_domains=self.config.browser.prohibited_domains,
        ))
        self._watchdog_manager.register(NetworkWatchdog())
        self._watchdog_manager.register(StorageWatchdog())
        self._watchdog_manager.register(DownloadWatchdog())
        self._watchdog_manager.register(DomWatchdog())
        self._watchdog_manager.register(VisualAnomalyWatchdog())
        await self._watchdog_manager.start_all()

        # 加载缓存
        self._cache_manager.load_from_disk()

        # 加载知识库
        self._knowledge_manager.load_from_disk()

        self._initialized = True
        self._log_audit("initialize", {"status": "success"})

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
        """确保六Agent已注册"""
        if not self.agent_registry.get_by_role(AgentRole.PLANNER):
            from uiai.agent.planner import PlannerAgent
            self.register_agent(PlannerAgent(llm_client=self.llm_client))

        if not self.agent_registry.get_by_role(AgentRole.GENERATOR):
            from uiai.agent.generator import GeneratorAgent
            self.register_agent(GeneratorAgent(llm_client=self.llm_client))

        if not self.agent_registry.get_by_role(AgentRole.HEALER):
            from uiai.agent.healer import HealerAgent
            self.register_agent(HealerAgent(llm_client=self.llm_client))

    def _ensure_executor_agent(self, executor: BaseExecutor) -> 'ExecutorAgent':
        """确保ExecutorAgent已注册并绑定执行器"""
        from uiai.agent.executor import ExecutorAgent
        agents = self.agent_registry.get_by_role(AgentRole.EXECUTOR)
        if agents:
            return agents[0]

        # 创建感知引擎
        perception = PerceptionEngine(executor, vl_client=self.llm_client)

        # 创建ExecutorAgent
        agent = ExecutorAgent(
            executor=executor,
            llm_client=self.llm_client,
            perception_engine=perception,
            loop_detector=self._loop_detector,
            cache_manager=self._cache_manager,
        )
        self.register_agent(agent)
        return agent

    # --- 测试执行（R1脚本模式）---

    async def run_test(self, test_case: TestCase, executor: BaseExecutor | None = None) -> TestResult:
        """执行单个测试用例（R1脚本模式）

        Args:
            test_case: 测试用例
            executor: 执行器（不传则自动创建）
        """
        await self.initialize()
        self._log_audit("run_test", {"test_id": test_case.id, "name": test_case.name, "tier": "R1_SCRIPT"})

        own_executor = executor is None
        if own_executor:
            executor = ExecutorFactory.create(Platform.WEB, self.config)
            await executor.start()

        # 初始化检查点管理器
        self._checkpoint_manager = CheckpointManager(executor)

        result = TestResult(
            test_id=test_case.id,
            test_name=test_case.name,
            status=TestStatus.PASSED,
        )

        try:
            for i, step in enumerate(test_case.steps):
                # 自动检查点（每5步）
                if self._checkpoint_manager:
                    await self._checkpoint_manager.auto_checkpoint(i, interval=5)

                step_result = await self._execute_step(executor, step)
                result.steps.append(step_result)

                if step_result.status.value == "failed":
                    result.status = TestStatus.FAILED
                    result.error = step_result.error

                    # 发布事件
                    await self.event_bus.publish(Event(
                        event_type=AgentEvent.STEP_FAILED,
                        source="orchestrator",
                        data={"step": step.name, "error": step_result.error},
                    ))

                    # 触发四层降级自愈
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

                # 发布步骤完成事件
                await self.event_bus.publish(Event(
                    event_type=AgentEvent.STEP_COMPLETE,
                    source="orchestrator",
                    data={"step": step.name, "index": i},
                ))

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error = str(e)

            # 发布崩溃事件
            await self.event_bus.publish(Event(
                event_type=WatchdogEvent.CRASH_DETECTED,
                source="orchestrator",
                data={"error": str(e), "test_id": test_case.id},
            ))

            # 尝试检查点恢复
            if self._checkpoint_manager:
                latest = self._checkpoint_manager.get_latest()
                if latest:
                    logger.info(f"尝试恢复到检查点: {latest.id}")
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
        """四层降级自愈

        D1: 选择器降级（Locator fallback chain）
        D2: DOM邻近搜索（A11y Tree搜索相似元素）
        D3: 视觉定位兜底（VL模型定位）
        D4: AI修复建议（需人工审核）
        """
        from uiai.healing.healer import HealingManager
        healer = HealingManager(self.config.healing, llm_client=self.llm_client)
        return await healer.try_heal(executor, step, step_result.error or "")

    # --- R2 Agent模式执行 ---

    async def run_agent_test(self, task: str, executor: BaseExecutor | None = None,
                             perception_mode: PerceptionMode = PerceptionMode.HYBRID,
                             max_steps: int = 50, initial_actions: list[dict] | None = None) -> TestResult:
        """R2 Agent模式执行 — Agent自主循环感知-决策-执行

        Args:
            task: 自然语言任务描述
            executor: 执行器
            perception_mode: 感知模式
            max_steps: 最大执行步数
            initial_actions: 确定性预步骤
        """
        await self.initialize()
        self._log_audit("run_agent_test", {"task": task[:100], "tier": "R2_AGENT", "perception": perception_mode.value})

        own_executor = executor is None
        if own_executor:
            executor = ExecutorFactory.create(Platform.WEB, self.config)
            await executor.start()

        # 重置循环检测器
        self._loop_detector.reset()

        # 初始化检查点
        self._checkpoint_manager = CheckpointManager(executor)

        # 检查缓存
        cached_plan = await self._cache_manager.check_plan_cache(task, "")
        if cached_plan:
            logger.info(f"命中Plan缓存，共{len(cached_plan)}步")

        # 获取知识上下文
        knowledge_context = await self._knowledge_manager.build_context(task, max_tokens=2000)

        # 创建ExecutorAgent
        from uiai.agent.executor import ExecutorAgent, FlashMode
        perception = PerceptionEngine(executor, vl_client=self.llm_client, default_mode=perception_mode)

        agent = ExecutorAgent(
            executor=executor,
            llm_client=self.llm_client,
            perception_engine=perception,
            loop_detector=self._loop_detector,
            cache_manager=self._cache_manager,
            flash_mode=FlashMode.STANDARD,
            max_steps=max_steps,
            initial_actions=initial_actions,
        )

        # 创建CodeRecorder
        from uiai.agent.code_recorder import CodeRecorder
        code_recorder = CodeRecorder()

        result = TestResult(
            test_id=f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_name=task[:50],
            status=TestStatus.PASSED,
        )

        try:
            # 发布Agent开始事件
            await self.event_bus.publish(Event(
                event_type=AgentEvent.STEP_START,
                source="orchestrator",
                data={"task": task, "mode": "R2_AGENT"},
            ))

            # 执行Agent循环
            history = await agent.run(task, knowledge_context=knowledge_context)

            # 记录CodeRecorder
            if history.is_successful():
                result.status = TestStatus.PASSED
            else:
                result.status = TestStatus.FAILED
                result.error = "; ".join(history.errors())

            # 生成代码
            code = code_recorder.generate_code(class_name="AgentRecordedTest")
            if code:
                result.healing_records.append({"generated_code": code})

            # JudgeAgent评估
            if self.llm_client:
                from uiai.agent.judge import JudgeAgent
                judge = JudgeAgent(llm_client=self.llm_client)
                judgement = await judge.run(task, history)
                if not judgement.verdict:
                    result.status = TestStatus.FAILED
                    result.error = f"Judge评估失败: {judgement.failure_reason}"

                # 沉淀经验
                if judgement.verdict:
                    await self._knowledge_manager.add_experience(
                        domain="agent_test",
                        title=f"成功: {task[:50]}",
                        content=f"任务: {task}\n步数: {history.number_of_steps()}\n耗时: {history.total_duration_seconds():.1f}s",
                        source="agent_learned",
                    )

            # 缓存成功的Plan
            if history.is_successful():
                steps_data = [{"step": i} for i in range(history.number_of_steps())]
                await self._cache_manager.set_plan(task, steps_data, "")

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error = str(e)
            logger.error(f"Agent执行异常: {e}")
        finally:
            result.duration_ms = int(history.total_duration_seconds() * 1000) if 'history' in dir() else 0
            if own_executor:
                await executor.stop()

        return result

    # --- 测试套件执行 ---

    async def run_suite(self, test_cases: list[TestCase], platform: Platform = Platform.WEB) -> SuiteResult:
        """执行测试套件"""
        await self.initialize()
        suite_result = SuiteResult(suite_name="default")

        for tc in test_cases:
            result = await self.run_test(tc)
            suite_result.results.append(result)

        suite_result.end_time = datetime.now()
        self._log_audit("run_suite", suite_result.to_dict())

        # 保存缓存和知识
        self._cache_manager.save_to_disk()
        self._knowledge_manager.save_to_disk()

        return suite_result

    # --- AI能力入口 ---

    async def generate_test_plan(self, requirement: str, **kwargs) -> AgentOutput:
        """生成测试计划（PlannerAgent）"""
        await self.initialize()
        self._ensure_agents()

        # 获取知识上下文
        knowledge_context = await self._knowledge_manager.build_context(requirement, max_tokens=2000)

        planner = self.agent_registry.get_first_by_role(AgentRole.PLANNER)
        if planner:
            return await planner.execute(requirement, knowledge_context=knowledge_context, **kwargs)
        return AgentOutput(role=AgentRole.PLANNER, success=False, message="Planner not available")

    async def generate_test_code(self, plan: str, **kwargs) -> AgentOutput:
        """生成测试代码（GeneratorAgent）"""
        await self.initialize()
        self._ensure_agents()
        generator = self.agent_registry.get_first_by_role(AgentRole.GENERATOR)
        if generator:
            return await generator.execute(plan, **kwargs)
        return AgentOutput(role=AgentRole.GENERATOR, success=False, message="Generator not available")

    async def heal_test(self, test_result: TestResult, **kwargs) -> AgentOutput:
        """自愈失败测试（HealerAgent）"""
        await self.initialize()
        self._ensure_agents()
        healer = self.agent_registry.get_first_by_role(AgentRole.HEALER)
        if healer:
            return await healer.execute(test_result, **kwargs)
        return AgentOutput(role=AgentRole.HEALER, success=False, message="Healer not available")

    async def explore(self, url: str, **kwargs) -> AgentOutput:
        """AI探索性测试（ExplorerAgent）"""
        await self.initialize()
        from uiai.agent.explorer import ExplorerAgent
        executor = ExecutorFactory.create(Platform.WEB, self.config)
        explorer = ExplorerAgent(llm_client=self.llm_client, executor=executor)
        return await explorer.execute(url, **kwargs)

    # --- 感知与缓存接口 ---

    async def perceive_page(self, executor: BaseExecutor,
                            mode: PerceptionMode = PerceptionMode.HYBRID) -> 'PerceptionResult':
        """感知页面状态"""
        perception = PerceptionEngine(executor, vl_client=self.llm_client, default_mode=mode)
        return await perception.perceive(mode)

    async def get_cached_plan(self, task: str) -> list[dict] | None:
        """获取缓存的任务计划"""
        return await self._cache_manager.check_plan_cache(task, "")

    async def get_cached_locate(self, description: str) -> dict | None:
        """获取缓存的元素定位"""
        return await self._cache_manager.check_locate_cache(description)

    # --- 知识管理接口 ---

    async def add_knowledge(self, level: str, domain: str, title: str, content: str,
                            tags: list[str] | None = None) -> None:
        """添加知识条目"""
        from uiai.core.knowledge import KnowledgeLevel
        level_map = {
            "requirement": KnowledgeLevel.REQUIREMENT,
            "product": KnowledgeLevel.PRODUCT,
            "experience": KnowledgeLevel.EXPERIENCE,
        }
        kl = level_map.get(level, KnowledgeLevel.EXPERIENCE)
        await self._knowledge_manager.add_entry(kl, domain, title, content, tags)

    async def search_knowledge(self, query: str, top_k: int = 5) -> list:
        """搜索知识库"""
        return await self._knowledge_manager.search(query, top_k=top_k)

    # --- Capability控制 ---

    def enable_capability(self, cap: Capability) -> None:
        """启用能力"""
        self._capability_manager.enable(cap)

    def disable_capability(self, cap: Capability) -> None:
        """禁用能力"""
        self._capability_manager.disable(cap)

    def apply_preset(self, preset: str) -> None:
        """应用能力预设"""
        config = self._capability_manager.create_preset(preset)
        self._capability_manager = CapabilityManager(config)

    # --- 生命周期 ---

    async def shutdown(self) -> None:
        """关闭所有资源"""
        # 停止Watchdog
        await self._watchdog_manager.stop_all()

        # 保存缓存和知识
        self._cache_manager.save_to_disk()
        self._knowledge_manager.save_to_disk()

        # 关闭浏览器池
        await self.browser_pool.close_all()

        # 权重衰减
        await self._knowledge_manager.decay_weights()

        self._log_audit("shutdown", {"total_audit_entries": len(self._audit_log)})
