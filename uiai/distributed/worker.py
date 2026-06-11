"""Worker节点 - 执行测试任务的独立进程/容器"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from uiai.config import UIAIConfig
from uiai.core.result import TestResult, SuiteResult
from uiai.core.test_case import TestCase
from uiai.orchestrator.orchestrator import TestOrchestrator

logger = logging.getLogger(__name__)


class WorkerStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class WorkerInfo:
    """Worker节点信息"""
    worker_id: str
    hostname: str
    ip: str
    status: WorkerStatus = WorkerStatus.IDLE
    max_concurrent: int = 1
    current_tasks: int = 0
    total_completed: int = 0
    total_failed: int = 0
    last_heartbeat: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    capabilities: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "hostname": self.hostname,
            "ip": self.ip,
            "status": self.status.value,
            "max_concurrent": self.max_concurrent,
            "current_tasks": self.current_tasks,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
            "last_heartbeat": self.last_heartbeat,
            "started_at": self.started_at,
            "capabilities": self.capabilities,
        }


class Worker:
    """Worker节点

    独立进程或容器，负责：
    1. 从Master获取测试任务
    2. 执行测试并收集结果
    3. 上报心跳和状态
    4. 上报测试结果

    可部署为：
    - 本地多进程
    - Docker容器
    - K8s Pod
    """

    def __init__(self, config: UIAIConfig | None = None, worker_id: str | None = None,
                 master_url: str = "http://localhost:8090"):
        self.config = config or UIAIConfig()
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.master_url = master_url
        self._status = WorkerStatus.IDLE
        self._orchestrator: TestOrchestrator | None = None
        self._heartbeat_interval = 10  # 秒
        self._running = False
        self._results_queue: list[TestResult] = []

        self.info = WorkerInfo(
            worker_id=self.worker_id,
            hostname=socket.gethostname(),
            ip=self._get_local_ip(),
            max_concurrent=self.config.parallel_workers,
            capabilities={
                "platforms": ["web"],
                "browsers": ["chromium", "firefox", "webkit"],
            },
        )

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    async def start(self) -> None:
        """启动Worker"""
        self._running = True
        self._orchestrator = TestOrchestrator(self.config)
        self.info.status = WorkerStatus.IDLE
        self.info.last_heartbeat = time.time()

        # 注册到Master
        await self._register()

        logger.info(f"Worker {self.worker_id} started on {self.info.hostname}")

        # 启动心跳和任务循环
        await asyncio.gather(
            self._heartbeat_loop(),
            self._task_loop(),
        )

    async def stop(self) -> None:
        """停止Worker"""
        self._running = False
        self.info.status = WorkerStatus.OFFLINE
        await self._deregister()
        logger.info(f"Worker {self.worker_id} stopped")

    async def _register(self) -> None:
        """注册到Master"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.master_url}/api/workers/register",
                    json=self.info.to_dict(),
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"Registered to master: {self.master_url}")
                    else:
                        logger.warning(f"Failed to register: {resp.status}")
        except Exception as e:
            logger.warning(f"Cannot connect to master: {e}. Running in standalone mode.")

    async def _deregister(self) -> None:
        """从Master注销"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.master_url}/api/workers/deregister",
                    json={"worker_id": self.worker_id},
                ) as resp:
                    pass
        except Exception:
            pass

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while self._running:
            self.info.last_heartbeat = time.time()
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.master_url}/api/workers/heartbeat",
                        json=self.info.to_dict(),
                    ) as resp:
                        pass
            except Exception:
                pass
            await asyncio.sleep(self._heartbeat_interval)

    async def _task_loop(self) -> None:
        """任务获取循环"""
        while self._running:
            if self.info.current_tasks >= self.info.max_concurrent:
                await asyncio.sleep(1)
                continue

            # 从Master获取任务
            task = await self._fetch_task()
            if task:
                asyncio.create_task(self._execute_task(task))
            else:
                await asyncio.sleep(2)

    async def _fetch_task(self) -> dict | None:
        """从Master获取待执行任务"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.master_url}/api/tasks/assign",
                    json={"worker_id": self.worker_id},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("task")
        except Exception:
            pass
        return None

    async def _execute_task(self, task: dict) -> None:
        """执行测试任务"""
        self.info.current_tasks += 1
        self.info.status = WorkerStatus.RUNNING

        try:
            test_case = TestCase(
                id=task.get("test_id", "unknown"),
                name=task.get("test_name", "unknown"),
            )
            # 简化：从任务数据构建TestCase
            for step_data in task.get("steps", []):
                from uiai.core.test_case import TestStep
                from uiai.core.locator import Locator, LocatorType
                locator = None
                if step_data.get("locator"):
                    loc_data = step_data["locator"]
                    locator = Locator(primary_type=LocatorType(loc_data["type"]), primary_value=loc_data["value"])
                test_case.add_step(
                    name=step_data.get("name", ""),
                    action=step_data.get("action", ""),
                    locator=locator,
                    value=step_data.get("value"),
                )

            result = await self._orchestrator.run_test(test_case)
            self.info.total_completed += 1

            # 上报结果
            await self._report_result(result, task)

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            self.info.total_failed += 1
        finally:
            self.info.current_tasks -= 1
            if self.info.current_tasks == 0:
                self.info.status = WorkerStatus.IDLE

    async def _report_result(self, result: TestResult, task: dict) -> None:
        """上报测试结果到Master"""
        import dataclasses
        try:
            import aiohttp
            result_data = dataclasses.asdict(result)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.master_url}/api/results/report",
                    json={
                        "worker_id": self.worker_id,
                        "task_id": task.get("task_id"),
                        "result": result_data,
                    },
                ) as resp:
                    pass
        except Exception as e:
            logger.warning(f"Failed to report result: {e}")


class WorkerStandalone:
    """独立模式Worker（不依赖Master，本地多进程执行）"""

    def __init__(self, config: UIAIConfig | None = None, num_workers: int = 2):
        self.config = config or UIAIConfig()
        self.num_workers = num_workers
        self._workers: list[Worker] = []

    async def run_suite(self, test_cases: list[TestCase]) -> SuiteResult:
        """并行执行测试套件"""
        from uiai.core.result import TestStatus
        suite_result = SuiteResult(suite_name="distributed")

        # 将测试用例分配到Worker
        tasks = []
        for i, tc in enumerate(test_cases):
            worker_idx = i % self.num_workers
            orchestrator = TestOrchestrator(self.config)
            tasks.append((orchestrator, tc))

        # 并行执行
        results = await asyncio.gather(
            *[orch.run_test(tc) for orch, tc in tasks],
            return_exceptions=True,
        )

        for r in results:
            if isinstance(r, Exception):
                suite_result.results.append(TestResult(
                    test_id="error", test_name="error",
                    status=TestStatus.ERROR, error=str(r),
                ))
            else:
                suite_result.results.append(r)

        suite_result.end_time = datetime.now()
        return suite_result
