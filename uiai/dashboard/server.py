"""Dashboard API服务器 - 测试管理+实时状态+历史查询"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DashboardServer:
    """Dashboard API服务器

    提供RESTful API：
    - 测试套件管理（CRUD）
    - 测试执行（触发/取消/重跑）
    - 实时状态（WebSocket推送）
    - 历史结果查询
    - 自愈记录查询/审批
    - Flaky测试列表
    - 趋势数据
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080, data_dir: str = "./dashboard_data"):
        self.host = host
        self.port = port
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._suites: dict[str, dict] = {}
        self._results: list[dict] = []
        self._running = False

    async def start(self) -> None:
        """启动Dashboard服务"""
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("aiohttp is required for Dashboard")

        app = web.Application(client_max_size=10 * 1024 * 1024)

        # CORS中间件
        @web.middleware
        async def cors_middleware(request, handler):
            resp = await handler(request)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp

        app = web.Application(middlewares=[cors_middleware])

        # API路由
        app.router.add_get("/api/health", self._health)
        app.router.add_get("/api/suites", self._list_suites)
        app.router.add_post("/api/suites", self._create_suite)
        app.router.add_get("/api/suites/{suite_id}", self._get_suite)
        app.router.add_post("/api/suites/{suite_id}/run", self._run_suite)
        app.router.add_get("/api/results", self._list_results)
        app.router.add_get("/api/results/{result_id}", self._get_result)
        app.router.add_get("/api/flaky", self._list_flaky)
        app.router.add_get("/api/healing/pending", self._list_pending_healing)
        app.router.add_post("/api/healing/{record_id}/approve", self._approve_healing)
        app.router.add_post("/api/healing/{record_id}/reject", self._reject_healing)
        app.router.add_get("/api/trend", self._get_trend)
        app.router.add_get("/api/stats", self._get_stats)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"Dashboard started on http://{self.host}:{self.port}")
        self._running = True
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

    async def _health(self, request) -> Any:
        from aiohttp import web
        return web.json_response({"status": "ok", "version": "0.1.0", "timestamp": datetime.now().isoformat()})

    async def _list_suites(self, request) -> Any:
        from aiohttp import web
        return web.json_response({"suites": list(self._suites.values())})

    async def _create_suite(self, request) -> Any:
        data = await request.json()
        suite_id = f"suite-{len(self._suites) + 1}"
        suite = {"id": suite_id, "created_at": datetime.now().isoformat(), **data}
        self._suites[suite_id] = suite
        from aiohttp import web
        return web.json_response(suite, status=201)

    async def _get_suite(self, request) -> Any:
        suite_id = request.match_info["suite_id"]
        from aiohttp import web
        if suite_id in self._suites:
            return web.json_response(self._suites[suite_id])
        return web.json_response({"error": "not found"}, status=404)

    async def _run_suite(self, request) -> Any:
        suite_id = request.match_info["suite_id"]
        from aiohttp import web
        return web.json_response({"message": f"Suite {suite_id} execution started", "status": "running"})

    async def _list_results(self, request) -> Any:
        from aiohttp import web
        limit = int(request.query.get("limit", "50"))
        return web.json_response({"results": self._results[-limit:]})

    async def _get_result(self, request) -> Any:
        from aiohttp import web
        return web.json_response({"error": "not found"}, status=404)

    async def _list_flaky(self, request) -> Any:
        from aiohttp import web
        return web.json_response({"flaky_tests": []})

    async def _list_pending_healing(self, request) -> Any:
        from aiohttp import web
        return web.json_response({"pending": []})

    async def _approve_healing(self, request) -> Any:
        from aiohttp import web
        return web.json_response({"status": "approved"})

    async def _reject_healing(self, request) -> Any:
        from aiohttp import web
        return web.json_response({"status": "rejected"})

    async def _get_trend(self, request) -> Any:
        from aiohttp import web
        trend_file = self.data_dir / "trend_data.json"
        if trend_file.exists():
            data = json.loads(trend_file.read_text(encoding="utf-8"))
            return web.json_response({"trend": data})
        return web.json_response({"trend": []})

    async def _get_stats(self, request) -> Any:
        from aiohttp import web
        return web.json_response({
            "total_suites": len(self._suites),
            "total_results": len(self._results),
        })
