"""任务队列 - 管理测试任务的调度和分发"""
from __future__ import annotations
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """测试任务"""
    task_id: str
    name: str
    target: Any              # 测试目标（URL/TestCase/文件路径等）
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    callback: Callable | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskQueue:
    """任务队列

    支持优先级排序、并发控制、任务回调。
    """

    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent
        self._queue: list[Task] = []
        self._running: dict[str, Task] = {}
        self._completed: list[Task] = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._task_counter = 0

    def submit(self, name: str, target: Any, priority: TaskPriority = TaskPriority.MEDIUM,
               callback: Callable | None = None, **metadata) -> Task:
        """提交任务"""
        self._task_counter += 1
        task = Task(
            task_id=f"task-{self._task_counter}",
            name=name,
            target=target,
            priority=priority,
            callback=callback,
            metadata=metadata,
        )
        self._queue.append(task)
        # 按优先级排序
        self._queue.sort(key=lambda t: t.priority.value)
        logger.debug(f"Task submitted: {task.task_id} ({name}), priority={priority.value}")
        return task

    async def get_next(self) -> Task | None:
        """获取下一个待执行任务"""
        async with self._lock:
            for task in self._queue:
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.RUNNING
                    self._running[task.task_id] = task
                    return task
        return None

    async def complete_task(self, task_id: str, result: Any = None, error: str | None = None) -> None:
        """标记任务完成"""
        async with self._lock:
            if task_id in self._running:
                task = self._running.pop(task_id)
                task.status = TaskStatus.FAILED if error else TaskStatus.COMPLETED
                task.result = result
                task.error = error
                self._completed.append(task)
                # 从队列移除
                self._queue = [t for t in self._queue if t.task_id != task_id]
                # 执行回调
                if task.callback:
                    try:
                        task.callback(task)
                    except Exception as e:
                        logger.warning(f"Task callback error: {e}")

    def cancel_task(self, task_id: str) -> None:
        """取消任务"""
        for task in self._queue:
            if task.task_id == task_id and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                break

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self._queue if t.status == TaskStatus.PENDING)

    @property
    def running_count(self) -> int:
        return len(self._running)

    @property
    def completed_count(self) -> int:
        return len(self._completed)
