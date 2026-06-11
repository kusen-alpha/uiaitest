"""Fixture体系 - 测试前置/后置条件管理"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class FixtureScope(Enum):
    """Fixture作用域"""
    SESSION = "session"     # 整个测试会话
    SUITE = "suite"         # 测试套件
    TEST = "test"           # 单个测试


@dataclass
class Fixture:
    """测试Fixture"""
    name: str
    setup: Callable
    teardown: Callable | None = None
    scope: FixtureScope = FixtureScope.TEST
    _cache: Any = None
    _is_setup: bool = False

    async def execute_setup(self) -> Any:
        """执行setup"""
        if self._is_setup:
            return self._cache
        if asyncio.iscoroutinefunction(self.setup):
            self._cache = await self.setup()
        else:
            self._cache = self.setup()
        self._is_setup = True
        return self._cache

    async def execute_teardown(self) -> None:
        """执行teardown"""
        if not self._is_setup or not self.teardown:
            return
        try:
            if asyncio.iscoroutinefunction(self.teardown):
                await self.teardown(self._cache)
            else:
                self.teardown(self._cache)
        except Exception as e:
            logger.warning(f"Fixture teardown error ({self.name}): {e}")
        finally:
            self._cache = None
            self._is_setup = False


class FixtureManager:
    """Fixture管理器

    管理测试Fixture的注册、执行和清理。
    支持Session/Suite/Test三种作用域。
    """

    def __init__(self):
        self._fixtures: dict[str, Fixture] = {}
        self._session_cache: dict[str, Any] = {}
        self._suite_cache: dict[str, Any] = {}

    def register(self, name: str, setup: Callable, teardown: Callable | None = None,
                 scope: FixtureScope = FixtureScope.TEST) -> None:
        """注册Fixture"""
        self._fixtures[name] = Fixture(name=name, setup=setup, teardown=teardown, scope=scope)
        logger.debug(f"Fixture registered: {name} (scope={scope.value})")

    def fixture(self, name: str | None = None, scope: FixtureScope = FixtureScope.TEST):
        """装饰器方式注册Fixture

        @manager.fixture(scope=FixtureScope.SESSION)
        async def browser():
            executor = PlaywrightExecutor()
            await executor.start()
            yield executor
            await executor.stop()
        """
        def decorator(func):
            fixture_name = name or func.__name__
            # 支持yield语法的fixture
            setup_fn, teardown_fn = self._parse_yield_fixture(func)
            self.register(fixture_name, setup_fn, teardown_fn, scope)
            return func
        return decorator

    def _parse_yield_fixture(self, func):
        """解析yield语法的fixture"""
        import inspect
        if not inspect.isgeneratorfunction(func) and not inspect.isasyncgenfunction(func):
            return func, None

        async def setup():
            if inspect.isasyncgenfunction(func):
                gen = func()
                return await gen.__anext__()
            else:
                gen = func()
                return next(gen)

        async def teardown(value):
            pass  # yield fixture的teardown较复杂，简化处理

        return setup, teardown

    async def get(self, name: str) -> Any:
        """获取Fixture值"""
        if name not in self._fixtures:
            raise KeyError(f"Fixture not found: {name}")

        fixture = self._fixtures[name]

        # 检查缓存
        if fixture.scope == FixtureScope.SESSION and name in self._session_cache:
            return self._session_cache[name]
        if fixture.scope == FixtureScope.SUITE and name in self._suite_cache:
            return self._suite_cache[name]

        # 执行setup
        value = await fixture.execute_setup()

        # 缓存
        if fixture.scope == FixtureScope.SESSION:
            self._session_cache[name] = value
        elif fixture.scope == FixtureScope.SUITE:
            self._suite_cache[name] = value

        return value

    async def setup_suite(self) -> None:
        """执行Suite级别的setup"""
        for name, fixture in self._fixtures.items():
            if fixture.scope == FixtureScope.SUITE and not fixture._is_setup:
                await self.get(name)

    async def teardown_suite(self) -> None:
        """执行Suite级别的teardown"""
        for name, fixture in self._fixtures.items():
            if fixture.scope == FixtureScope.SUITE and fixture._is_setup:
                await fixture.execute_teardown()
        self._suite_cache.clear()

    async def teardown_session(self) -> None:
        """执行Session级别的teardown"""
        for name, fixture in self._fixtures.items():
            if fixture.scope in (FixtureScope.SESSION, FixtureScope.SUITE) and fixture._is_setup:
                await fixture.execute_teardown()
        self._session_cache.clear()
        self._suite_cache.clear()
