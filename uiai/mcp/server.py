"""UIAI MCP Server - 对外提供MCP协议接口"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any

from uiai.config import UIAIConfig

logger = logging.getLogger(__name__)

# MCP工具定义
MCP_TOOLS = [
    {
        "name": "uiai_navigate",
        "description": "导航到指定URL",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "目标URL"}},
            "required": ["url"],
        },
    },
    {
        "name": "uiai_click",
        "description": "点击元素",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locator_type": {"type": "string", "enum": ["role", "test_id", "text", "css", "xpath"], "description": "定位器类型"},
                "locator_value": {"type": "string", "description": "定位器值"},
            },
            "required": ["locator_type", "locator_value"],
        },
    },
    {
        "name": "uiai_type",
        "description": "输入文本",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locator_type": {"type": "string", "enum": ["role", "test_id", "text", "css", "xpath"]},
                "locator_value": {"type": "string"},
                "text": {"type": "string", "description": "输入文本"},
            },
            "required": ["locator_type", "locator_value", "text"],
        },
    },
    {
        "name": "uiai_snapshot",
        "description": "获取页面辅助功能树快照",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "uiai_screenshot",
        "description": "截取页面截图",
        "inputSchema": {
            "type": "object",
            "properties": {"full_page": {"type": "boolean", "description": "是否全页截图", "default": False}},
        },
    },
    {
        "name": "uiai_assert_visible",
        "description": "断言元素可见",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locator_type": {"type": "string", "enum": ["role", "test_id", "text", "css", "xpath"]},
                "locator_value": {"type": "string"},
            },
            "required": ["locator_type", "locator_value"],
        },
    },
    {
        "name": "uiai_assert_text",
        "description": "断言元素文本",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locator_type": {"type": "string", "enum": ["role", "test_id", "text", "css", "xpath"]},
                "locator_value": {"type": "string"},
                "expected": {"type": "string", "description": "期望文本"},
            },
            "required": ["locator_type", "locator_value", "expected"],
        },
    },
    {
        "name": "uiai_generate_plan",
        "description": "AI生成测试计划",
        "inputSchema": {
            "type": "object",
            "properties": {"requirement": {"type": "string", "description": "测试需求描述"}},
            "required": ["requirement"],
        },
    },
    {
        "name": "uiai_explore",
        "description": "AI探索性测试",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标URL"},
                "max_pages": {"type": "integer", "description": "最大页面数", "default": 20},
            },
            "required": ["url"],
        },
    },
]


class UIAIMCPServer:
    """UIAI MCP Server实现

    提供标准MCP协议接口，支持AI客户端（Claude Code/Cursor等）调用。
    注意：此Server仅用于本地开发辅助，不适用于生产CI环境。
    """

    def __init__(self, config: UIAIConfig):
        self.config = config
        self._executor = None

    async def _get_executor(self):
        if self._executor is None:
            from uiai.executor.factory import ExecutorFactory
            from uiai.core.platform import Platform
            self._executor = ExecutorFactory.create(Platform.WEB, self.config)
            await self._executor.start()
        return self._executor

    async def _get_locator(self, locator_type: str, locator_value: str):
        from uiai.core.locator import Locator
        mapping = {
            "role": Locator.by_role,
            "test_id": Locator.by_test_id,
            "text": Locator.by_text,
            "css": Locator.by_css,
            "xpath": Locator.by_xpath,
        }
        factory = mapping.get(locator_type)
        if not factory:
            raise ValueError(f"Unknown locator type: {locator_type}")
        return factory(locator_value)

    async def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """处理MCP工具调用"""
        try:
            if tool_name == "uiai_navigate":
                executor = await self._get_executor()
                await executor.navigate(arguments["url"])
                return {"content": [{"type": "text", "text": f"Navigated to {arguments['url']}"}]}

            elif tool_name == "uiai_click":
                executor = await self._get_executor()
                locator = await self._get_locator(arguments["locator_type"], arguments["locator_value"])
                await executor.click(locator)
                return {"content": [{"type": "text", "text": f"Clicked: {arguments['locator_value']}"}]}

            elif tool_name == "uiai_type":
                executor = await self._get_executor()
                locator = await self._get_locator(arguments["locator_type"], arguments["locator_value"])
                await executor.type_text(locator, arguments["text"])
                return {"content": [{"type": "text", "text": f"Typed '{arguments['text']}'"}]}

            elif tool_name == "uiai_snapshot":
                executor = await self._get_executor()
                tree = await executor.get_accessibility_tree()
                from uiai.visual.snapshot import AccessibilitySnapshot
                snapshot = AccessibilitySnapshot(tree)
                return {"content": [{"type": "text", "text": snapshot.to_text()}]}

            elif tool_name == "uiai_screenshot":
                executor = await self._get_executor()
                screenshot = await executor.screenshot(full_page=arguments.get("full_page", False))
                import base64
                b64 = base64.b64encode(screenshot).decode()
                return {"content": [{"type": "image", "data": b64, "mimeType": "image/png"}]}

            elif tool_name == "uiai_assert_visible":
                executor = await self._get_executor()
                locator = await self._get_locator(arguments["locator_type"], arguments["locator_value"])
                from uiai.assertion.engine import AssertionEngine
                engine = AssertionEngine(executor)
                result = await engine.assert_visible(locator)
                return {"content": [{"type": "text", "text": f"Visible: {result.passed} - {result.message}"}]}

            elif tool_name == "uiai_assert_text":
                executor = await self._get_executor()
                locator = await self._get_locator(arguments["locator_type"], arguments["locator_value"])
                from uiai.assertion.engine import AssertionEngine
                engine = AssertionEngine(executor)
                result = await engine.assert_text_equals(locator, arguments["expected"])
                return {"content": [{"type": "text", "text": f"Text match: {result.passed} - {result.message}"}]}

            elif tool_name == "uiai_generate_plan":
                from uiai.orchestrator.orchestrator import TestOrchestrator
                orchestrator = TestOrchestrator(self.config)
                output = await orchestrator.generate_test_plan(arguments["requirement"])
                return {"content": [{"type": "text", "text": output.data or output.message}]}

            elif tool_name == "uiai_explore":
                from uiai.orchestrator.orchestrator import TestOrchestrator
                orchestrator = TestOrchestrator(self.config)
                output = await orchestrator.explore(arguments["url"], max_pages=arguments.get("max_pages", 20))
                return {"content": [{"type": "text", "text": output.data or output.message}]}

            else:
                return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True}

        except Exception as e:
            logger.error(f"MCP tool call error: {e}")
            return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}

    async def cleanup(self):
        if self._executor:
            await self._executor.stop()
            self._executor = None


async def start_mcp_server(config: UIAIConfig, host: str = "0.0.0.0", port: int = 8080) -> None:
    """启动MCP服务器（stdio模式或HTTP模式）"""
    server = UIAIMCPServer(config)

    try:
        # 尝试使用mcp库的stdio模式
        from mcp.server import Server
        from mcp.server.stdio import stdio_server

        mcp_server = Server("uiai")

        @mcp_server.list_tools()
        async def list_tools():
            return MCP_TOOLS

        @mcp_server.call_tool()
        async def call_tool(name, arguments):
            result = await server.handle_tool_call(name, arguments)
            return result.get("content", [])

        async with stdio_server() as (read_stream, write_stream):
            await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())

    except ImportError:
        # 回退到简单HTTP模式
        import aiohttp.web as web

        async def handle_request(request):
            data = await request.json()
            tool_name = data.get("tool")
            arguments = data.get("arguments", {})
            result = await server.handle_tool_call(tool_name, arguments)
            return web.json_response(result)

        async def handle_list_tools(request):
            return web.json_response({"tools": MCP_TOOLS})

        app = web.Application()
        app.router.add_post("/tools/call", handle_request)
        app.router.add_get("/tools", handle_list_tools)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"UIAI MCP Server (HTTP) running on {host}:{port}")

        # 保持运行
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await server.cleanup()
            await runner.cleanup()
