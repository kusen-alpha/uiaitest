"""Pytest插件 - 将uiai集成到pytest测试框架"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from uiai.config import UIAIConfig
from uiai.core.platform import Platform
from uiai.executor.base import BaseExecutor
from uiai.executor.factory import ExecutorFactory
from uiai.assertion.engine import AssertionEngine
from uiai.orchestrator.orchestrator import TestOrchestrator
from uiai.report.generator import ReportGenerator

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    """添加uiai命令行选项"""
    group = parser.getgroup("uiai", "UIAI testing framework")
    group.addoption("--uiai-config", action="store", default=None, help="UIAI配置文件路径")
    group.addoption("--uiai-browser", action="store", default="chromium", help="浏览器类型")
    group.addoption("--uiai-headed", action="store_true", default=False, help="有头模式")
    group.addoption("--uiai-base-url", action="store", default="", help="基础URL")
    group.addoption("--uiai-headless", action="store_true", default=True, help="无头模式")
    group.addoption("--uiai-slow-mo", action="store", default=0, type=float, help="慢放速度(ms)")
    group.addoption("--uiai-report-dir", action="store", default="./reports", help="报告目录")


@pytest.fixture(scope="session")
def uiai_config(request):
    """Session级别的UIAI配置"""
    config_path = request.config.getoption("--uiai-config")
    if config_path:
        config = UIAIConfig.from_yaml(config_path)
    else:
        config = UIAIConfig()

    # 命令行参数覆盖
    config.browser.browser_type = request.config.getoption("--uiai-browser")
    config.browser.headless = not request.config.getoption("--uiai-headed")
    config.browser.slow_mo = request.config.getoption("--uiai-slow-mo")
    if request.config.getoption("--uiai-base-url"):
        config.base_url = request.config.getoption("--uiai-base-url")

    return config


@pytest.fixture(scope="session")
def uiai_orchestrator(uiai_config):
    """Session级别的Orchestrator"""
    return TestOrchestrator(uiai_config)


@pytest.fixture(scope="session")
def uiai_report_generator(uiai_config, request):
    """Session级别的报告生成器"""
    report_dir = request.config.getoption("--uiai-report-dir")
    return ReportGenerator(report_dir)


@pytest.fixture
async def executor(uiai_config):
    """测试级别的执行器（每个测试独立）"""
    executor = ExecutorFactory.create(Platform.WEB, uiai_config)
    await executor.start()
    yield executor
    await executor.stop()


@pytest.fixture
def assertion_engine(executor):
    """测试级别的断言引擎"""
    return AssertionEngine(executor)


@pytest.fixture
def page_object_base(executor):
    """Page Object基类工厂"""
    from uiai.core.page_object import BasePage
    return BasePage(executor)
