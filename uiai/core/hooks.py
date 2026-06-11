"""Hook事件体系 - 测试生命周期钩子"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HookType(Enum):
    """钩子类型"""
    BEFORE_ALL = "before_all"
    AFTER_ALL = "after_all"
    BEFORE_SUITE = "before_suite"
    AFTER_SUITE = "after_suite"
    BEFORE_TEST = "before_test"
    AFTER_TEST = "after_test"
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    ON_ERROR = "on_error"
    ON_HEAL = "on_heal"


@dataclass
class HookContext:
    """Hook上下文"""
    hook_type: HookType
    test_id: str | None = None
    test_name: str | None = None
    step_name: str | None = None
    error: Exception | None = None
    data: dict[str, Any] | None = None

    def __init__(self, hook_type: HookType, **kwargs):
        self.hook_type = hook_type
        self.test_id = kwargs.get("test_id")
        self.test_name = kwargs.get("test_name")
        self.step_name = kwargs.get("step_name")
        self.error = kwargs.get("error")
        self.data = kwargs


class HookManager:
    """Hook管理器

    管理测试生命周期中的钩子函数。
    支持同步和异步钩子。
    """

    def __init__(self):
        self._hooks: dict[HookType, list[Callable]] = {ht: [] for ht in HookType}

    def register(self, hook_type: HookType, func: Callable) -> None:
        """注册钩子"""
        self._hooks[hook_type].append(func)
        logger.debug(f"Hook registered: {hook_type.value} -> {func.__name__}")

    def on(self, hook_type: HookType):
        """装饰器方式注册钩子

        @hook_manager.on(HookType.BEFORE_TEST)
        async def before_test(ctx):
            print(f"Starting: {ctx.test_name}")
        """
        def decorator(func):
            self.register(hook_type, func)
            return func
        return decorator

    async def emit(self, hook_type: HookType, **kwargs) -> None:
        """触发钩子"""
        ctx = HookContext(hook_type, **kwargs)
        for func in self._hooks.get(hook_type, []):
            try:
                if asyncio.iscoroutinefunction(func):
                    await func(ctx)
                else:
                    func(ctx)
            except Exception as e:
                logger.warning(f"Hook error ({hook_type.value}, {func.__name__}): {e}")

    def clear(self, hook_type: HookType | None = None) -> None:
        """清除钩子"""
        if hook_type:
            self._hooks[hook_type] = []
        else:
            self._hooks = {ht: [] for ht in HookType}
