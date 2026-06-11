"""Appium执行器 - 移动端App执行引擎"""
from __future__ import annotations
import asyncio
import logging
import base64
from typing import Any, Optional

from uiai.core.locator import Locator, LocatorType
from uiai.core.platform import Platform
from uiai.executor.base import BaseExecutor
from uiai.config import AppiumConfig

logger = logging.getLogger(__name__)


class AppiumExecutor(BaseExecutor):
    """Appium执行器

    支持Android/iOS原生App、混合App、移动H5。
    定位策略：Accessibility ID优先 + OCR/图像兜底。
    """

    platform = Platform.ANDROID

    def __init__(self, config: AppiumConfig | None = None, platform: Platform = Platform.ANDROID):
        self.config = config or AppiumConfig()
        self.platform = platform
        self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            raise RuntimeError("Executor not started. Call start() first.")
        return self._driver

    async def start(self, **kwargs) -> None:
        """启动Appium会话"""
        try:
            from appium import webdriver as appium_webdriver
        except ImportError:
            raise ImportError(
                "appium-python-client is required for mobile testing. "
                "Install it with: pip install appium-python-client"
            )

        caps = {
            "platformName": self.config.platform_name,
            "automationName": self.config.automation_name,
            "deviceName": self.config.device_name,
            "noReset": self.config.no_reset,
        }
        if self.config.app:
            caps["app"] = self.config.app
        if self.config.app_package:
            caps["appPackage"] = self.config.app_package
        if self.config.app_activity:
            caps["appActivity"] = self.config.app_activity
        caps.update(self.config.capabilities)

        # Appium WebDriver 是同步的，用 to_thread 避免阻塞事件循环
        self._driver = await asyncio.to_thread(
            appium_webdriver.Remote,
            command_executor=self.config.server_url,
            desired_capabilities=caps,
        )
        logger.info(f"Appium session started: {self.config.platform_name}")

    async def stop(self) -> None:
        if self._driver:
            await asyncio.to_thread(self._driver.quit)
            self._driver = None
            logger.info("Appium session stopped")

    def _resolve_locator(self, locator: Locator):
        """解析定位器为Appium定位策略"""
        chain = locator.build_chain()
        for loc_type, loc_value, options in chain:
            strategy = self._to_appium_strategy(loc_type, loc_value, options)
            if strategy:
                try:
                    elements = self._driver.find_elements(*strategy)
                    if elements:
                        return elements[0]
                except Exception:
                    continue
        # 降级链全部失败，返回主策略
        primary = chain[0]
        strategy = self._to_appium_strategy(primary[0], primary[1], primary[2])
        if strategy:
            return self._driver.find_element(*strategy)
        raise ValueError(f"Cannot resolve locator: {locator.description}")

    def _to_appium_strategy(self, loc_type: LocatorType, value: str, options: dict):
        """将统一LocatorType转为Appium定位策略元组"""
        from appium.webdriver.common.appiumby import AppiumBy
        mapping = {
            LocatorType.ACCESSIBILITY_ID: (AppiumBy.ACCESSIBILITY_ID, value),
            LocatorType.XPATH: (AppiumBy.XPATH, value),
            LocatorType.CSS: (AppiumBy.CSS_SELECTOR, value),
            LocatorType.TEST_ID: (AppiumBy.ID, value),
            LocatorType.ROLE: (AppiumBy.ACCESSIBILITY_ID, value),
            LocatorType.TEXT: (AppiumBy.XPATH, f"//*[@text='{value}']"),
            LocatorType.LABEL: (AppiumBy.ACCESSIBILITY_ID, value),
        }
        return mapping.get(loc_type)

    async def navigate(self, url: str) -> None:
        await asyncio.to_thread(self.driver.get, url)

    async def click(self, locator: Locator) -> None:
        element = await asyncio.to_thread(self._resolve_locator, locator)
        await asyncio.to_thread(element.click)
        logger.debug(f"Clicked: {locator.description}")

    async def type_text(self, locator: Locator, text: str, clear: bool = True) -> None:
        element = await asyncio.to_thread(self._resolve_locator, locator)
        if clear:
            await asyncio.to_thread(element.clear)
        await asyncio.to_thread(element.send_keys, text)

    async def fill(self, locator: Locator, value: str) -> None:
        await self.type_text(locator, value, clear=True)

    async def select_option(self, locator: Locator, value: str | list[str]) -> None:
        raise NotImplementedError("select_option not supported in Appium")

    async def check(self, locator: Locator) -> None:
        element = await asyncio.to_thread(self._resolve_locator, locator)
        selected = await asyncio.to_thread(element.is_selected)
        if not selected:
            await asyncio.to_thread(element.click)

    async def uncheck(self, locator: Locator) -> None:
        element = await asyncio.to_thread(self._resolve_locator, locator)
        selected = await asyncio.to_thread(element.is_selected)
        if selected:
            await asyncio.to_thread(element.click)

    async def hover(self, locator: Locator) -> None:
        raise NotImplementedError("hover not supported in Appium")

    async def press_key(self, key: str) -> None:
        """按键 - 使用Android keycode"""
        android_keycodes = {
            "Enter": 66, "Tab": 61, "Escape": 111, "Backspace": 67,
            "Delete": 112, "Home": 3, "Back": 4,
        }
        keycode = android_keycodes.get(key)
        if keycode:
            await asyncio.to_thread(self.driver.press_keycode, keycode)
        else:
            element = await asyncio.to_thread(lambda: self.driver.switch_to.active_element)
            await asyncio.to_thread(element.send_keys, key)

    async def wait_for(self, locator: Locator, timeout: int | None = None) -> None:
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        strategy = self._to_appium_strategy(locator.primary_type, locator.primary_value, locator.options)
        if strategy:
            await asyncio.to_thread(
                lambda: WebDriverWait(self.driver, (timeout or 30000) / 1000).until(
                    EC.presence_of_element_located(strategy)
                )
            )

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> bytes:
        png_base64 = await asyncio.to_thread(self.driver.get_screenshot_as_base64)
        data = base64.b64decode(png_base64)
        if path:
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        return data

    async def get_accessibility_tree(self) -> dict:
        """获取App端控件树（通过page_source）"""
        source = await asyncio.to_thread(lambda: self.driver.page_source)
        return {"source": source}

    async def get_text(self, locator: Locator) -> str:
        element = await asyncio.to_thread(self._resolve_locator, locator)
        return await asyncio.to_thread(lambda: element.text)

    async def is_visible(self, locator: Locator) -> bool:
        try:
            element = await asyncio.to_thread(self._resolve_locator, locator)
            return await asyncio.to_thread(element.is_displayed)
        except Exception:
            return False

    async def evaluate(self, expression: str) -> Any:
        raise NotImplementedError("evaluate not supported in Appium")

    async def get_url(self) -> str:
        return await asyncio.to_thread(lambda: self.driver.current_url)

    async def get_title(self) -> str:
        return await asyncio.to_thread(lambda: self.driver.title)
