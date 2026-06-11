"""网络拦截器 - 请求/响应拦截、Mock、资源屏蔽"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from playwright.async_api import Route, Request, Response

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """资源类型"""
    DOCUMENT = "document"
    STYLESHEET = "stylesheet"
    IMAGE = "image"
    MEDIA = "media"
    FONT = "font"
    SCRIPT = "script"
    TEXTTRACK = "texttrack"
    XHR = "xhr"
    FETCH = "fetch"
    EVENTSOURCE = "eventsource"
    WEBSOCKET = "websocket"
    MANIFEST = "manifest"
    OTHER = "other"


@dataclass
class NetworkLog:
    """网络请求日志"""
    url: str
    method: str
    resource_type: str
    status: int | None = None
    request_headers: dict = field(default_factory=dict)
    response_headers: dict | None = None
    body: str | None = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: float = 0.0


@dataclass
class MockResponse:
    """Mock响应配置"""
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: str | dict = ""
    content_type: str = "application/json"

    def to_response_json(self) -> dict:
        body = self.body
        if isinstance(body, dict):
            import json
            body = json.dumps(body)
        return {
            "status": self.status,
            "headers": {**{"Content-Type": self.content_type}, **self.headers},
            "body": body,
        }


class NetworkInterceptor:
    """网络拦截器

    功能：
    1. 拦截并记录请求/响应
    2. Mock API响应
    3. 屏蔽指定资源类型
    4. 修改请求头
    5. 请求重写
    """

    def __init__(self):
        self._logs: list[NetworkLog] = []
        self._mocks: dict[str, MockResponse] = {}  # url_pattern -> MockResponse
        self._blocked_types: set[ResourceType] = set()
        self._header_modifiers: dict[str, str] = {}
        self._request_hooks: list[Callable] = []
        self._response_hooks: list[Callable] = []
        self._max_logs: int = 1000

    def mock(self, url_pattern: str, response: MockResponse) -> NetworkInterceptor:
        """Mock指定URL的响应"""
        self._mocks[url_pattern] = response
        logger.info(f"Mock registered: {url_pattern} -> {response.status}")
        return self

    def block(self, *resource_types: ResourceType) -> NetworkInterceptor:
        """屏蔽指定资源类型"""
        for rt in resource_types:
            self._blocked_types.add(rt)
        logger.info(f"Blocked resource types: {[rt.value for rt in resource_types]}")
        return self

    def set_header(self, name: str, value: str) -> NetworkInterceptor:
        """修改所有请求头"""
        self._header_modifiers[name] = value
        return self

    def on_request(self, hook: Callable) -> NetworkInterceptor:
        """注册请求钩子"""
        self._request_hooks.append(hook)
        return self

    def on_response(self, hook: Callable) -> NetworkInterceptor:
        """注册响应钩子"""
        self._response_hooks.append(hook)
        return self

    async def handle_route(self, route: Route) -> None:
        """Playwright route handler"""
        request = route.request
        url = request.url
        resource_type = request.resource_type

        # 检查是否屏蔽
        try:
            rt = ResourceType(resource_type)
        except ValueError:
            rt = ResourceType.OTHER

        if rt in self._blocked_types:
            await route.abort()
            self._add_log(url, request.method, resource_type, status=0, error="blocked")
            return

        # 检查是否Mock
        for pattern, mock_resp in self._mocks.items():
            if pattern in url:
                await route.fulfill(**mock_resp.to_response_json())
                self._add_log(url, request.method, resource_type, status=mock_resp.status)
                return

        # 调用请求钩子
        for hook in self._request_hooks:
            try:
                result = hook(request)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Request hook error: {e}")

        # 修改请求头后继续
        headers = {**request.headers, **self._header_modifiers}
        try:
            await route.continue_(headers=headers)
        except Exception:
            await route.continue_()

    def _add_log(self, url: str, method: str, resource_type: str, **kwargs) -> None:
        """添加网络日志"""
        import time
        log = NetworkLog(
            url=url, method=method, resource_type=resource_type,
            timestamp=time.time(), **kwargs
        )
        self._logs.append(log)
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

    def get_logs(self, url_pattern: str | None = None, method: str | None = None,
                 resource_type: str | None = None) -> list[NetworkLog]:
        """查询网络日志"""
        logs = self._logs
        if url_pattern:
            logs = [l for l in logs if url_pattern in l.url]
        if method:
            logs = [l for l in logs if l.method == method]
        if resource_type:
            logs = [l for l in logs if l.resource_type == resource_type]
        return logs

    def get_failed_requests(self) -> list[NetworkLog]:
        """获取失败的请求"""
        return [l for l in self._logs if l.error or (l.status and l.status >= 400)]

    def clear(self) -> None:
        """清除所有日志和配置"""
        self._logs.clear()
        self._mocks.clear()
        self._blocked_types.clear()
        self._header_modifiers.clear()

    @property
    def total_requests(self) -> int:
        return len(self._logs)
