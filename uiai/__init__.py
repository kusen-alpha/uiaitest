"""UIAI - UI AI Automation Testing Framework

自研代码Agent中控 + 开源技术底座的混合分层自动化测试框架
支持Web/App多平台，支持测试用例执行、断言、报告、自愈等全流程
"""

__version__ = "0.1.0"

# 核心抽象
from uiai.core.platform import Platform, BrowserType, ExecutionMode
from uiai.core.locator import Locator, LocatorType
from uiai.core.result import TestResult, SuiteResult, TestStatus, StepResult, StepStatus
from uiai.core.test_case import TestCase, TestStep, TestCaseType, Priority

# 配置
from uiai.config import UIAIConfig, BrowserConfig, AppiumConfig, LLMConfig, HealingConfig, ReportConfig

# 执行器
from uiai.executor.base import BaseExecutor
from uiai.executor.factory import ExecutorFactory

# 断言
from uiai.assertion.engine import AssertionEngine, AssertionResult, AssertionType, SoftAssertionCollector

# Agent
from uiai.agent.base import BaseAgent, AgentRole, AgentState, AgentOutput
from uiai.agent.llm import BaseLLMClient, create_llm_client
from uiai.agent.context import ContextManager

# 编排
from uiai.orchestrator.orchestrator import TestOrchestrator

# 报告
from uiai.report.generator import ReportGenerator

# 自愈
from uiai.healing.healer import HealingManager, HealingRecord, HealingMetrics, HealingStrategy, HealingStatus

# 视觉
from uiai.visual.comparator import VisualComparator
from uiai.visual.snapshot import AccessibilitySnapshot
from uiai.visual.visual_agent import VisualAgent

# Page Object Model
from uiai.core.page_object import BasePage

# 数据驱动
from uiai.core.data_driver import DataDriver, DataVariant

# Fixture体系
from uiai.core.fixtures import FixtureManager, FixtureScope

# Hook事件
from uiai.core.hooks import HookManager, HookType

# 环境管理
from uiai.core.environment import EnvironmentManager, Environment

# 数据工厂
from uiai.core.data_factory import DataFactory

# 分布式执行
from uiai.distributed.worker import Worker, WorkerStandalone, WorkerStatus
from uiai.distributed.master import MasterNode
from uiai.distributed.docker_pool import DockerBrowserPool

# 监控告警
from uiai.monitoring.flaky_detector import FlakyDetector, FlakyRecord
from uiai.monitoring.alert import AlertManager, Alert, AlertType, AlertLevel

# Dashboard
from uiai.dashboard.server import DashboardServer

# 插件体系
from uiai.plugins.manager import PluginManager, BasePlugin, PluginHook

# 性能测试
from uiai.performance.lighthouse import LighthouseRunner, PerformanceResult
