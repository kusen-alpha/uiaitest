"""事件总线 - 基于发布/订阅模式的异步事件系统

提供全局事件总线，支持同步/异步处理器、优先级调度、过滤器、
错误隔离和事件历史记录。用于 Agent、Watchdog、Executor 等模块间的解耦通信。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ── 事件类型定义 ──────────────────────────────────────────────


class AgentEvent(str, Enum):
    """Agent 事件类型"""

    STEP_START = "agent:step_start"
    STEP_COMPLETE = "agent:step_complete"
    STEP_FAILED = "agent:step_failed"
    PLAN_UPDATE = "agent:plan_update"
    HEALING_TRIGGERED = "agent:healing_triggered"


class WatchdogEvent(str, Enum):
    """Watchdog 事件类型"""

    POPUP_DETECTED = "watchdog:popup_detected"
    CAPTCHA_DETECTED = "watchdog:captcha_detected"
    CRASH_DETECTED = "watchdog:crash_detected"
    SECURITY_VIOLATION = "watchdog:security_violation"
    NETWORK_ERROR = "watchdog:network_error"
    DOM_CHANGED = "watchdog:dom_changed"
    DOWNLOAD_COMPLETE = "watchdog:download_complete"
    VISUAL_ANOMALY = "watchdog:visual_anomaly"
    STORAGE_CHANGED = "watchdog:storage_changed"


class ExecutionEvent(str, Enum):
    """执行器事件类型"""

    ACTION_START = "execution:action_start"
    ACTION_COMPLETE = "execution:action_complete"
    ACTION_FAILED = "execution:action_failed"
    NAVIGATION = "execution:navigation"
    CHECKPOINT_SAVE = "execution:checkpoint_save"
    CHECKPOINT_RESTORE = "execution:checkpoint_restore"


# ── 核心数据结构 ──────────────────────────────────────────────


class Priority(int, Enum):
    """处理器优先级（数值越小越先执行）"""

    HIGH = 0
    NORMAL = 50
    LOW = 100


@dataclass(frozen=True)
class Event:
    """事件对象

    Attributes:
        event_type: 事件类型标识
        source: 事件来源模块
        data: 事件携带数据
        timestamp: 事件产生时间
        event_id: 事件唯一标识
    """

    event_type: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


# ── 处理器包装 ────────────────────────────────────────────────

# 处理器回调类型：同步函数或异步协程函数
HandlerCallback = Callable[[Event], None] | Callable[[Event], Coroutine[Any, Any, None]]


@dataclass
class _HandlerEntry:
    """内部处理器条目

    将回调函数与其优先级、过滤条件和唯一标识封装在一起，
    以支持排序、过滤和取消订阅。
    """

    callback: HandlerCallback
    priority: Priority = Priority.NORMAL
    event_type_filter: str | None = None
    source_filter: str | None = None
    handler_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def matches(self, event: Event) -> bool:
        """判断该处理器是否对给定事件感兴趣"""
        if self.event_type_filter is not None and event.event_type != self.event_type_filter:
            return False
        if self.source_filter is not None and event.source != self.source_filter:
            return False
        return True


# ── EventBus ──────────────────────────────────────────────────


class EventBus:
    """事件总线

    基于发布/订阅模式的全局事件调度中心，支持：

    - 同步与异步处理器混合注册
    - 优先级调度（HIGH → NORMAL → LOW）
    - 按 event_type / source 过滤
    - 处理器错误隔离（单个处理器异常不影响其他处理器）
    - 可配置的事件历史记录
    - 线程安全的异步实现

    使用示例::

        bus = EventBus()

        # 订阅
        hid = bus.subscribe(
            callback=on_popup,
            event_type=WatchdogEvent.POPUP_DETECTED,
            priority=Priority.HIGH,
        )

        # 发布
        await bus.publish(Event(
            event_type=WatchdogEvent.POPUP_DETECTED,
            source="watchdog",
            data={"text": "确认弹窗"},
        ))

        # 取消订阅
        bus.unsubscribe(hid)
    """

    def __init__(self, *, history_size: int = 0) -> None:
        """初始化事件总线

        Args:
            history_size: 事件历史记录最大条数，0 表示不记录。
        """
        self._handlers: list[_HandlerEntry] = []
        self._history: deque[Event] | None = None
        self._history_size = history_size
        if history_size > 0:
            self._history = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    # ── 订阅 ──────────────────────────────────────────────

    def subscribe(
        self,
        callback: HandlerCallback,
        *,
        priority: Priority = Priority.NORMAL,
        event_type: str | None = None,
        source: str | None = None,
    ) -> str:
        """注册事件处理器

        Args:
            callback: 处理器回调函数，接受 Event 参数，支持同步和异步。
            priority: 处理器优先级，数值越小越先执行。
            event_type: 仅监听此事件类型，None 表示不过滤。
            source: 仅监听此来源，None 表示不过滤。

        Returns:
            handler_id: 处理器唯一标识，用于取消订阅。
        """
        entry = _HandlerEntry(
            callback=callback,
            priority=priority,
            event_type_filter=event_type,
            source_filter=source,
        )
        self._handlers.append(entry)
        # 按优先级排序，保证 HIGH 先执行
        self._handlers.sort(key=lambda h: h.priority.value)
        logger.debug(
            "处理器已注册: id=%s priority=%s event_type=%s source=%s callback=%s",
            entry.handler_id,
            priority.name,
            event_type,
            source,
            getattr(callback, "__name__", repr(callback)),
        )
        return entry.handler_id

    def on(
        self,
        *,
        priority: Priority = Priority.NORMAL,
        event_type: str | None = None,
        source: str | None = None,
    ):
        """装饰器方式注册处理器

        用法::

            @bus.on(event_type=WatchdogEvent.POPUP_DETECTED, priority=Priority.HIGH)
            async def handle_popup(event: Event):
                ...
        """

        def decorator(callback: HandlerCallback) -> HandlerCallback:
            self.subscribe(callback, priority=priority, event_type=event_type, source=source)
            return callback

        return decorator

    # ── 取消订阅 ──────────────────────────────────────────

    def unsubscribe(self, handler_id: str) -> bool:
        """取消订阅

        Args:
            handler_id: subscribe 返回的处理器标识。

        Returns:
            是否成功移除（False 表示 handler_id 不存在）。
        """
        for i, entry in enumerate(self._handlers):
            if entry.handler_id == handler_id:
                self._handlers.pop(i)
                logger.debug("处理器已移除: id=%s", handler_id)
                return True
        logger.warning("取消订阅失败，handler_id 不存在: %s", handler_id)
        return False

    # ── 发布 ──────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
        """发布事件

        按优先级顺序调用所有匹配的处理器。
        单个处理器的异常会被捕获并记录，不会影响后续处理器。
        同步处理器在事件循环中直接调用，异步处理器使用 await。

        Args:
            event: 要发布的事件对象。
        """
        # 记录历史
        if self._history is not None:
            self._history.append(event)

        matched = [h for h in self._handlers if h.matches(event)]
        if not matched:
            logger.debug("事件无匹配处理器: type=%s source=%s", event.event_type, event.source)
            return

        logger.debug(
            "事件发布: type=%s source=%s 匹配处理器=%d",
            event.event_type,
            event.source,
            len(matched),
        )

        for entry in matched:
            try:
                if asyncio.iscoroutinefunction(entry.callback):
                    await entry.callback(event)
                else:
                    entry.callback(event)
            except Exception:
                logger.exception(
                    "处理器执行异常: handler_id=%s callback=%s event_type=%s",
                    entry.handler_id,
                    getattr(entry.callback, "__name__", repr(entry.callback)),
                    event.event_type,
                )

    def publish_sync(self, event: Event) -> None:
        """同步方式发布事件

        尝试在已有事件循环中调度 publish；若无运行中的事件循环，
        则新建一个。适用于从同步代码中触发事件的场景。

        Args:
            event: 要发布的事件对象。
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            asyncio.run(self.publish(event))

    # ── 查询 ──────────────────────────────────────────────

    @property
    def history(self) -> list[Event]:
        """获取事件历史记录的快照"""
        if self._history is None:
            return []
        return list(self._history)

    def clear_history(self) -> None:
        """清空事件历史记录"""
        if self._history is not None:
            self._history.clear()

    @property
    def handler_count(self) -> int:
        """当前已注册的处理器数量"""
        return len(self._handlers)

    def clear_handlers(self) -> None:
        """清空所有处理器"""
        self._handlers.clear()
        logger.debug("所有处理器已清空")

    # ── 上下文管理 ────────────────────────────────────────

    async def __aenter__(self) -> EventBus:
        return self

    async def __aexit__(self, *exc) -> None:
        self.clear_handlers()
        self.clear_history()


# ── 全局单例 ──────────────────────────────────────────────────

_global_bus: EventBus | None = None


def get_event_bus(*, history_size: int = 100) -> EventBus:
    """获取全局事件总线单例

    首次调用时创建，后续调用返回同一实例。
    history_size 仅在首次创建时生效。

    Args:
        history_size: 事件历史记录最大条数。

    Returns:
        全局 EventBus 实例。
    """
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus(history_size=history_size)
    return _global_bus
