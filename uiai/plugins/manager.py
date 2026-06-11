"""插件管理器 - 第三方扩展架构"""
from __future__ import annotations
import importlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class PluginHook(Enum):
    """插件钩子点"""
    BEFORE_START = "before_start"
    AFTER_START = "after_start"
    BEFORE_TEST = "before_test"
    AFTER_TEST = "after_test"
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    ON_ERROR = "on_error"
    ON_HEAL = "on_heal"
    ON_REPORT = "on_report"
    BEFORE_STOP = "before_stop"


@dataclass
class PluginInfo:
    """插件信息"""
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    hooks: list[PluginHook] = field(default_factory=list)
    enabled: bool = True


class BasePlugin:
    """插件基类

    所有第三方插件继承此类，实现需要的钩子方法。

    用法:
        class ScreenshotPlugin(BasePlugin):
            name = "screenshot"
            version = "1.0.0"

            async def on_after_step(self, context):
                await context.executor.screenshot(path=f"step_{context.step_name}.png")
    """

    name: str = "unnamed"
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    _enabled: bool = True

    def on_before_start(self, context: Any) -> Any: pass
    def on_after_start(self, context: Any) -> Any: pass
    def on_before_test(self, context: Any) -> Any: pass
    def on_after_test(self, context: Any) -> Any: pass
    def on_before_step(self, context: Any) -> Any: pass
    def on_after_step(self, context: Any) -> Any: pass
    def on_error(self, context: Any) -> Any: pass
    def on_heal(self, context: Any) -> Any: pass
    def on_report(self, context: Any) -> Any: pass
    def on_before_stop(self, context: Any) -> Any: pass

    @property
    def info(self) -> PluginInfo:
        hooks = []
        for hook in PluginHook:
            method_name = f"on_{hook.value}"
            if hasattr(self, method_name) and getattr(self, method_name).__func__ is not getattr(BasePlugin, method_name):
                hooks.append(hook)
        return PluginInfo(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            hooks=hooks,
            enabled=self._enabled,
        )


class PluginManager:
    """插件管理器

    管理插件的注册、加载、执行。
    支持从Python包动态加载插件。
    """

    def __init__(self):
        self._plugins: dict[str, BasePlugin] = {}
        self._hook_map: dict[PluginHook, list[BasePlugin]] = {h: [] for h in PluginHook}

    def register(self, plugin: BasePlugin) -> None:
        """注册插件"""
        self._plugins[plugin.name] = plugin
        info = plugin.info
        for hook in info.hooks:
            self._hook_map[hook].append(plugin)
        logger.info(f"Plugin registered: {plugin.name} v{plugin.version} (hooks: {[h.value for h in info.hooks]})")

    def unregister(self, name: str) -> None:
        """注销插件"""
        if name in self._plugins:
            plugin = self._plugins.pop(name)
            for hook_list in self._hook_map.values():
                if plugin in hook_list:
                    hook_list.remove(plugin)

    def load_plugin(self, module_path: str) -> None:
        """从Python模块路径加载插件"""
        try:
            module = importlib.import_module(module_path)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin):
                    plugin = attr()
                    self.register(plugin)
        except Exception as e:
            logger.error(f"Failed to load plugin from {module_path}: {e}")

    async def emit(self, hook: PluginHook, context: Any = None) -> None:
        """触发插件钩子"""
        import asyncio
        for plugin in self._hook_map.get(hook, []):
            if not plugin._enabled:
                continue
            try:
                method = getattr(plugin, f"on_{hook.value}")
                result = method(context)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Plugin {plugin.name} hook {hook.value} error: {e}")

    def list_plugins(self) -> list[PluginInfo]:
        """列出所有插件"""
        return [p.info for p in self._plugins.values()]

    def enable(self, name: str) -> None:
        if name in self._plugins:
            self._plugins[name]._enabled = True

    def disable(self, name: str) -> None:
        if name in self._plugins:
            self._plugins[name]._enabled = False
