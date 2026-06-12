"""UIAI - AI驱动的UI自动化测试框架

自研代码Agent中控 + 开源技术底座的混合分层自动化测试框架
支持Web/App多平台，支持测试用例执行、断言、报告、自愈等全流程

架构核心：
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

__version__ = "1.0.0"

# === 核心抽象 ===
from uiai.core.platform import Platform, BrowserType, ExecutionMode, PerceptionMode, RunTier
from uiai.core.locator import Locator, LocatorType
from uiai.core.result import TestResult, SuiteResult, TestStatus, StepResult, StepStatus
from uiai.core.test_case import TestCase, TestStep, TestCaseType, Priority

# === 配置 ===
from uiai.config import UIAIConfig, BrowserConfig, AppiumConfig, LLMConfig, HealingConfig, ReportConfig, ConfigProxy

# === 执行器 ===
from uiai.executor.base import BaseExecutor
from uiai.executor.factory import ExecutorFactory

# === 断言 ===
from uiai.assertion.engine import AssertionEngine, AssertionResult, AssertionType, SoftAssertionCollector

# === Agent体系 ===
from uiai.agent.base import BaseAgent, AgentRole, AgentState, AgentOutput
from uiai.agent.llm import BaseLLMClient, create_llm_client
from uiai.agent.loop_detector import LoopDetector, LoopDetectorConfig
from uiai.agent.intent_router import IntentRouter, IntentType, ModelConfig
from uiai.agent.message_compactor import MessageCompactor, CompactionConfig, CompactionStrategy
from uiai.agent.code_recorder import CodeRecorder

# === 感知引擎 ===
from uiai.core.perception import PerceptionEngine, PerceptionResult

# === 事件总线 ===
from uiai.core.eventbus import EventBus, Event, get_event_bus, AgentEvent, WatchdogEvent, ExecutionEvent

# === Watchdog守卫系统 ===
from uiai.core.watchdog import (
    BaseWatchdog, WatchdogManager,
    PopupWatchdog, CaptchaWatchdog, CrashWatchdog,
    SecurityWatchdog, NetworkWatchdog, StorageWatchdog,
    DownloadWatchdog, DomWatchdog, VisualAnomalyWatchdog,
)

# === 三层缓存系统 ===
from uiai.core.cache import CacheManager, CacheEntry

# === 知识沉淀系统 ===
from uiai.core.knowledge import KnowledgeManager, KnowledgeEntry, KnowledgeLevel

# === Skill/Capability系统 ===
from uiai.core.skill import SkillRegistry, Skill, InputPrimitive
from uiai.core.capability import CapabilityManager, Capability, CapabilityConfig

# === 检查点机制 ===
from uiai.core.checkpoint import CheckpointManager, Checkpoint

# === 安全保障 ===
from uiai.core.security import SensitiveDataProtector, SensitiveDataConfig, FallbackLLM

# === 可靠性保障 ===
from uiai.core.resilience import (
    ActionTimeout, TimeoutConfig,
    CircuitBreaker, CircuitBreakerConfig, CircuitState,
    ContextBudget, BudgetConfig,
    UIAIError, TransientError, PersistentError, InfrastructureError, BusinessError,
    ErrorCategory, classify_error,
)

# === 两阶段深度定位 ===
from uiai.core.deep_locator import DeepLocator, LocateRegion, LocateResult

# === Agent协作 ===
from uiai.agent.collaboration import (
    AgentMessage, CollaborationMode, AgentCollabor,
    HumanCollaboration, ApprovalResult, HumanInput,
)

# === 提示词模板 ===
from uiai.agent.prompt_template import PromptTemplateManager, PromptMode, SystemPrompt

# === 编排调度 ===
from uiai.orchestrator.orchestrator import TestOrchestrator

# === 报告 ===
from uiai.report.generator import ReportGenerator

# === 自愈 ===
from uiai.healing.healer import HealingManager, HealingRecord, HealingMetrics, HealingStrategy, HealingStatus

# === 视觉 ===
from uiai.visual.comparator import VisualComparator

# === Page Object Model ===
from uiai.core.page_object import BasePage

# === 数据驱动 ===
from uiai.core.data_driver import DataDriver, DataVariant

# === Fixture体系 ===
from uiai.core.fixtures import FixtureManager, FixtureScope

# === Hook事件 ===
from uiai.core.hooks import HookManager, HookType

# === 环境管理 ===
from uiai.core.environment import EnvironmentManager, Environment

# === 数据工厂 ===
from uiai.core.data_factory import DataFactory

# === 分布式执行 ===
from uiai.distributed.worker import Worker, WorkerStandalone, WorkerStatus
from uiai.distributed.master import MasterNode
from uiai.distributed.docker_pool import DockerBrowserPool

# === 监控告警 ===
from uiai.monitoring.flaky_detector import FlakyDetector, FlakyRecord, FlakyMark
from uiai.monitoring.alert import AlertManager, Alert, AlertType, AlertLevel

# === 插件体系 ===
from uiai.plugins.manager import PluginManager, BasePlugin, PluginHook
from uiai.plugins.builtin import TraceRecorder, KnowledgeSync, MetricsExporter

# === 性能测试 ===
from uiai.performance.lighthouse import LighthouseRunner, PerformanceResult
