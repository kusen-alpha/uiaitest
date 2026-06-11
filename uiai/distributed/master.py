"""Master节点 - 任务调度、Worker管理、结果聚合"""
from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from uiai.core.result import SuiteResult, TestResult, TestStatus
from uiai.distributed.worker import WorkerInfo, WorkerStatus

logger = logging.getLogger(__name__)


@dataclass
class DistributedTask:
    """分布式任务"""
    task_id: str
    test_id: str
    test_name: str
    steps: list[dict] = field(default_factory=list)
    assigned_worker: str | None = None
    status: str = "pending"  # pending/running/completed/failed
    result: dict | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class MasterNode:
    """Master节点

    核心职责：
    1. 管理Worker注册/心跳/注销
    2. 任务队列管理和分发
    3. 结果聚合和报告生成
    4. 故障检测和任务重分配
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8090,
                 heartbeat_timeout: int = 30):
        self.host = host
        self.port = port
        self.heartbeat_timeout = heartbeat_timeout
        self._workers: dict[str, WorkerInfo] = {}
        self._task_queue: list[DistributedTask] = []
        self._completed_tasks: list[DistributedTask] = []
        self._results: list[TestResult] = []
        self._task_counter = 0
        self._running = False

    async def start(self) -> None:
        """启动Master服务"""
        self._running = True

        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("aiohttp is required for Master node")

        app = web.Application()
        app.router.add_post("/api/workers/register", self._handle_register)
        app.router.add_post("/api/workers/deregister", self._handle_deregister)
        app.router.add_post("/api/workers/heartbeat", self._handle_heartbeat)
        app.router.add_post("/api/tasks/submit", self._handle_submit_task)
        app.router.add_post("/api/tasks/assign", self._handle_assign_task)
        app.router.add_post("/api/results/report", self._handle_report_result)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_get("/api/workers", self._handle_list_workers)
        app.router.add_get("/api/results", self._handle_list_results)

        # 启动故障检测
        asyncio.create_task(self._fault_detection_loop())

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"Master node started on {self.host}:{self.port}")

        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

    async def stop(self) -> None:
        self._running = False

    # --- Worker管理 ---

    async def _handle_register(self, request) -> Any:
        data = await request.json()
        worker = WorkerInfo(
            worker_id=data["worker_id"],
            hostname=data["hostname"],
            ip=data["ip"],
            max_concurrent=data.get("max_concurrent", 1),
            capabilities=data.get("capabilities", {}),
        )
        self._workers[worker.worker_id] = worker
        logger.info(f"Worker registered: {worker.worker_id} ({worker.hostname})")
        from aiohttp import web
        return web.json_response({"status": "ok"})

    async def _handle_deregister(self, request) -> Any:
        data = await request.json()
        worker_id = data.get("worker_id")
        if worker_id in self._workers:
            del self._workers[worker_id]
            logger.info(f"Worker deregistered: {worker_id}")
        from aiohttp import web
        return web.json_response({"status": "ok"})

    async def _handle_heartbeat(self, request) -> Any:
        data = await request.json()
        worker_id = data.get("worker_id")
        if worker_id in self._workers:
            self._workers[worker_id].last_heartbeat = time.time()
            self._workers[worker_id].current_tasks = data.get("current_tasks", 0)
            self._workers[worker_id].status = WorkerStatus(data.get("status", "idle"))
        from aiohttp import web
        return web.json_response({"status": "ok"})

    # --- 任务管理 ---

    async def _handle_submit_task(self, request) -> Any:
        data = await request.json()
        self._task_counter += 1
        task = DistributedTask(
            task_id=f"task-{self._task_counter}",
            test_id=data.get("test_id", ""),
            test_name=data.get("test_name", ""),
            steps=data.get("steps", []),
        )
        self._task_queue.append(task)
        from aiohttp import web
        return web.json_response({"task_id": task.task_id, "status": "queued"})

    async def _handle_assign_task(self, request) -> Any:
        data = await request.json()
        worker_id = data.get("worker_id")

        # 找到待执行的任务
        pending = [t for t in self._task_queue if t.status == "pending"]
        if not pending:
            from aiohttp import web
            return web.json_response({"task": None})

        task = pending[0]
        task.assigned_worker = worker_id
        task.status = "running"

        from aiohttp import web
        return web.json_response({"task": {
            "task_id": task.task_id,
            "test_id": task.test_id,
            "test_name": task.test_name,
            "steps": task.steps,
        }})

    async def _handle_report_result(self, request) -> Any:
        data = await request.json()
        worker_id = data.get("worker_id")
        task_id = data.get("task_id")
        result_data = data.get("result", {})

        # 更新任务状态
        for task in self._task_queue:
            if task.task_id == task_id:
                task.status = "completed"
                task.result = result_data
                self._completed_tasks.append(task)
                self._task_queue.remove(task)
                break

        logger.info(f"Result reported: {task_id} from {worker_id}")
        from aiohttp import web
        return web.json_response({"status": "ok"})

    # --- 状态查询 ---

    async def _handle_status(self, request) -> Any:
        from aiohttp import web
        return web.json_response({
            "workers": len(self._workers),
            "active_workers": sum(1 for w in self._workers.values() if w.status != WorkerStatus.OFFLINE),
            "pending_tasks": sum(1 for t in self._task_queue if t.status == "pending"),
            "running_tasks": sum(1 for t in self._task_queue if t.status == "running"),
            "completed_tasks": len(self._completed_tasks),
        })

    async def _handle_list_workers(self, request) -> Any:
        from aiohttp import web
        return web.json_response({
            "workers": [w.to_dict() for w in self._workers.values()]
        })

    async def _handle_list_results(self, request) -> Any:
        from aiohttp import web
        return web.json_response({
            "results": [t.result for t in self._completed_tasks if t.result]
        })

    # --- 故障检测 ---

    async def _fault_detection_loop(self) -> None:
        """定期检测Worker故障，重分配超时任务"""
        while self._running:
            now = time.time()
            # 检测心跳超时
            for worker_id, worker in list(self._workers.items()):
                if now - worker.last_heartbeat > self.heartbeat_timeout:
                    if worker.status != WorkerStatus.OFFLINE:
                        logger.warning(f"Worker {worker_id} heartbeat timeout")
                        worker.status = WorkerStatus.OFFLINE
                        # 重分配该Worker的任务
                        await self._reassign_worker_tasks(worker_id)

            await asyncio.sleep(5)

    async def _reassign_worker_tasks(self, worker_id: str) -> None:
        """重分配故障Worker的任务"""
        for task in self._task_queue:
            if task.assigned_worker == worker_id and task.status == "running":
                task.assigned_worker = None
                task.status = "pending"
                logger.info(f"Task {task.task_id} reassigned from failed worker {worker_id}")
