"""Page Object Model - 基础页面对象模式"""
from __future__ import annotations
import logging
from typing import Any

from uiai.core.locator import Locator
from uiai.executor.base import BaseExecutor
from uiai.assertion.engine import AssertionEngine

logger = logging.getLogger(__name__)


class BasePage:
    """页面对象基类

    所有页面对象继承此类，封装页面元素和操作。
    遵循Page Object模式，将页面元素定位和操作封装在页面对象中。

    用法:
        class LoginPage(BasePage):
            username_input = Locator.by_placeholder("用户名")
            password_input = Locator.by_placeholder("密码")
            login_button = Locator.by_role("button", name="登录")

            async def login(self, username: str, password: str):
                await self.type_text(self.username_input, username)
                await self.type_text(self.password_input, password)
                await self.click(self.login_button)
    """

    def __init__(self, executor: BaseExecutor):
        self._executor = executor
        self._assertion = AssertionEngine(executor)

    @property
    def executor(self) -> BaseExecutor:
        return self._executor

    @property
    def assertion(self) -> AssertionEngine:
        return self._assertion

    # --- 通用页面操作 ---

    async def navigate(self, url: str) -> None:
        await self._executor.navigate(url)

    async def click(self, locator: Locator) -> None:
        await self._executor.click(locator)

    async def type_text(self, locator: Locator, text: str, clear: bool = True) -> None:
        await self._executor.type_text(locator, text, clear=clear)

    async def fill(self, locator: Locator, value: str) -> None:
        await self._executor.fill(locator, value)

    async def select_option(self, locator: Locator, value: str | list[str]) -> None:
        await self._executor.select_option(locator, value)

    async def check(self, locator: Locator) -> None:
        await self._executor.check(locator)

    async def uncheck(self, locator: Locator) -> None:
        await self._executor.uncheck(locator)

    async def hover(self, locator: Locator) -> None:
        await self._executor.hover(locator)

    async def wait_for(self, locator: Locator, timeout: int | None = None) -> None:
        await self._executor.wait_for(locator, timeout=timeout)

    async def get_text(self, locator: Locator) -> str:
        return await self._executor.get_text(locator)

    async def is_visible(self, locator: Locator) -> bool:
        return await self._executor.is_visible(locator)

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> bytes:
        return await self._executor.screenshot(path=path, full_page=full_page)

    # --- 通用断言 ---

    async def should_be_visible(self, locator: Locator, message: str = "") -> None:
        result = await self._assertion.assert_visible(locator, message)
        assert result.passed, result.message

    async def should_have_text(self, locator: Locator, expected: str, message: str = "") -> None:
        result = await self._assertion.assert_text_equals(locator, expected, message)
        assert result.passed, result.message

    async def should_contain_text(self, locator: Locator, expected: str, message: str = "") -> None:
        result = await self._assertion.assert_text_contains(locator, expected, message)
        assert result.passed, result.message

    async def should_have_url(self, expected: str, message: str = "") -> None:
        result = await self._assertion.assert_url_equals(expected, message)
        assert result.passed, result.message

    async def should_have_title(self, expected: str, message: str = "") -> None:
        result = await self._assertion.assert_title_contains(expected, message)
        assert result.passed, result.message

    # --- 页面信息 ---

    async def get_url(self) -> str:
        return await self._executor.get_url()

    async def get_title(self) -> str:
        return await self._executor.get_title()

    async def wait_for_load(self, state: str = "load") -> None:
        """等待页面加载完成 (domcontentloaded/load/networkidle)"""
        if hasattr(self._executor, "wait_for_load_state"):
            await self._executor.wait_for_load_state(state)
