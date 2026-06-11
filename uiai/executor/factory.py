"""执行器工厂 - 根据平台自动路由创建执行器"""
from __future__ import annotations
import logging
from typing import Any

from uiai.core.platform import Platform
from uiai.executor.base import BaseExecutor
from uiai.config import UIAIConfig, BrowserConfig, AppiumConfig

logger = logging.getLogger(__name__)


class ExecutorFactory:
    """执行器工厂

    根据目标平台自动创建对应的执行器实例。
    支持扩展注册自定义执行器。
    """

    _registry: dict[Platform, type[BaseExecutor]] = {}

    @classmethod
    def register(cls, platform: Platform, executor_class: type[BaseExecutor]) -> None:
        """注册自定义执行器"""
        cls._registry[platform] = executor_class
        logger.debug(f"Registered executor for {platform.value}: {executor_class.__name__}")

    @classmethod
    def create(cls, platform: Platform, config: UIAIConfig | None = None, **kwargs) -> BaseExecutor:
        """创建执行器实例

        Args:
            platform: 目标平台
            config: 全局配置
            **kwargs: 额外参数

        Returns:
            对应平台的执行器实例
        """
        config = config or UIAIConfig()

        # 优先使用注册的自定义执行器
        if platform in cls._registry:
            return cls._registry[platform](**kwargs)

        # 默认执行器映射
        if platform in (Platform.WEB, Platform.H5, Platform.MINI_PROGRAM, Platform.DESKTOP):
            from uiai.executor.playwright_executor import PlaywrightExecutor
            return PlaywrightExecutor(config=config.browser)

        elif platform in (Platform.ANDROID, Platform.IOS):
            from uiai.executor.appium_executor import AppiumExecutor
            appium_config = config.appium
            if platform == Platform.IOS:
                appium_config.platform_name = "iOS"
                appium_config.automation_name = "XCUITest"
            return AppiumExecutor(config=appium_config, platform=platform)

        else:
            raise ValueError(f"Unsupported platform: {platform}")

    @classmethod
    def create_web(cls, config: BrowserConfig | None = None, **kwargs) -> BaseExecutor:
        """快捷方法：创建Web执行器"""
        from uiai.executor.playwright_executor import PlaywrightExecutor
        return PlaywrightExecutor(config=config or BrowserConfig())

    @classmethod
    def create_app(cls, config: AppiumConfig | None = None, platform: Platform = Platform.ANDROID) -> BaseExecutor:
        """快捷方法：创建App执行器"""
        from uiai.executor.appium_executor import AppiumExecutor
        return AppiumExecutor(config=config or AppiumConfig(), platform=platform)
