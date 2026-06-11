"""Playwright执行器 - Web/H5平台执行引擎，进程内直调Playwright SDK

生产级增强功能：
1. Popup/Dialog自动处理
2. 网络拦截与Mock
3. 多标签/窗口管理
4. Iframe支持
5. Cookie管理
6. 认证状态持久化
7. 文件下载
8. 控制台日志捕获
9. 页面事件监听
10. 高级等待策略
11. 设备模拟
12. 截图增强
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Page, Locator as PwLocator,
    FrameLocator, Download, Dialog, ConsoleMessage, FileChooser,
)

from uiai.core.locator import Locator, LocatorType
from uiai.core.platform import Platform, BrowserType
from uiai.executor.base import BaseExecutor
from uiai.executor.network import NetworkInterceptor, ResourceType, MockResponse, NetworkLog
from uiai.config import BrowserConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类与枚举
# ---------------------------------------------------------------------------

class DialogStrategy(Enum):
    """对话框处理策略"""
    ACCEPT = "accept"
    DISMISS = "dismiss"
    IGNORE = "ignore"


@dataclass
class ConsoleMessageLog:
    """控制台消息记录"""
    type: str          # log / warn / error / info
    text: str
    url: str | None = None
    line_number: int | None = None
    timestamp: float = 0.0


@dataclass
class PageEventLog:
    """页面事件记录"""
    event: str         # error / crash / load / domcontentloaded / close
    detail: str = ""
    url: str = ""
    timestamp: float = 0.0


@dataclass
class DownloadInfo:
    """下载文件信息"""
    filename: str
    url: str
    suggested_filename: str
    save_path: str | None = None
    size: int | None = None
    finished: bool = False


@dataclass
class EmulationConfig:
    """设备模拟配置"""
    viewport: dict[str, int] | None = None
    locale: str | None = None
    timezone_id: str | None = None
    geolocation: dict[str, float] | None = None
    permissions: list[str] = field(default_factory=list)
    color_scheme: str | None = None      # light / dark / no-preference
    device_scale_factor: float | None = None
    has_touch: bool | None = None
    is_mobile: bool | None = None
    user_agent: str | None = None


# ---------------------------------------------------------------------------
# PlaywrightExecutor
# ---------------------------------------------------------------------------

class PlaywrightExecutor(BaseExecutor):
    """Playwright执行器

    进程内直调Playwright SDK，无MCP中间层，消除RPC开销。
    支持Chromium/Firefox/WebKit跨浏览器。
    """

    platform = Platform.WEB

    def __init__(self, config: BrowserConfig | None = None):
        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

        # ---- 增强功能状态 ----
        # 1. Dialog
        self._dialog_strategy: DialogStrategy = DialogStrategy.ACCEPT
        self._dialog_prompt_text: str | None = None
        self._dialog_handler_registered: bool = False

        # 2. Network
        self._network_interceptor: NetworkInterceptor | None = None
        self._route_registered: bool = False

        # 3. Multi-tab
        self._pages: dict[str, Page] = {}   # page_id -> Page
        self._active_page_id: str | None = None

        # 4. Iframe
        self._current_frame: FrameLocator | None = None

        # 5. Cookie (无额外状态，直接操作context)

        # 7. Download
        self._downloads: list[DownloadInfo] = []
        self._download_handler_registered: bool = False

        # 8. Console
        self._console_messages: list[ConsoleMessageLog] = []
        self._console_handler_registered: bool = False

        # 9. Page events
        self._page_events: list[PageEventLog] = []
        self._page_event_handlers_registered: bool = False
        self._on_page_error: Callable | None = None
        self._on_page_crash: Callable | None = None
        self._on_page_load: Callable | None = None

        # 11. Emulation
        self._emulation: EmulationConfig | None = None

    # -----------------------------------------------------------------------
    # 属性
    # -----------------------------------------------------------------------

    @property
    def page(self) -> Page:
        """获取当前Page实例"""
        if self._page is None:
            raise RuntimeError("Executor not started. Call start() first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """获取当前BrowserContext实例"""
        if self._context is None:
            raise RuntimeError("Executor not started. Call start() first.")
        return self._context

    @property
    def browser(self) -> Browser:
        """获取当前Browser实例"""
        if self._browser is None:
            raise RuntimeError("Executor not started. Call start() first.")
        return self._browser

    @property
    def network(self) -> NetworkInterceptor:
        """获取网络拦截器实例"""
        if self._network_interceptor is None:
            self._network_interceptor = NetworkInterceptor()
        return self._network_interceptor

    # -----------------------------------------------------------------------
    # 启动 / 停止
    # -----------------------------------------------------------------------

    async def start(self, **kwargs) -> None:
        """启动浏览器"""
        self._playwright = await async_playwright().start()

        browser_type = self.config.browser_type
        launch_method = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }.get(browser_type, self._playwright.chromium)

        self._browser = await launch_method.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo * 1000 if self.config.slow_mo else None,
        )

        context_kwargs = {
            "viewport": self.config.viewport,
            "ignore_https_errors": self.config.ignore_https_errors,
        }
        if self.config.record_video:
            context_kwargs["record_video_dir"] = "./reports/videos"

        # 应用设备模拟
        if self._emulation:
            context_kwargs.update(self._build_emulation_kwargs())

        # 如果有存储状态文件，加载
        storage_state = kwargs.get("storage_state")
        if storage_state:
            context_kwargs["storage_state"] = storage_state

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(30000)

        # 注册页面追踪
        self._register_page(self._page)

        # 注册增强功能
        self._setup_dialog_handler()
        self._setup_console_handler()
        self._setup_page_event_handlers()
        self._setup_download_handler()
        await self._setup_network_interception()

        logger.info(f"Playwright started: {browser_type}, headless={self.config.headless}")

    async def stop(self) -> None:
        """关闭浏览器"""
        # 清理网络拦截
        if self._network_interceptor:
            self._network_interceptor.clear()
            self._network_interceptor = None
            self._route_registered = False

        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._pages.clear()
        self._active_page_id = None
        self._current_frame = None
        self._console_messages.clear()
        self._page_events.clear()
        self._downloads.clear()
        self._dialog_handler_registered = False
        self._console_handler_registered = False
        self._page_event_handlers_registered = False
        self._download_handler_registered = False

        logger.info("Playwright stopped")

    # -----------------------------------------------------------------------
    # 内部工具方法
    # -----------------------------------------------------------------------

    def _register_page(self, page: Page) -> None:
        """注册页面到多标签管理"""
        page_id = str(id(page))
        self._pages[page_id] = page
        self._active_page_id = page_id
        # 监听页面关闭事件，自动清理
        page.on("close", lambda: self._unregister_page(page_id))

    def _unregister_page(self, page_id: str) -> None:
        """从多标签管理中移除页面"""
        self._pages.pop(page_id, None)
        if self._active_page_id == page_id:
            # 切换到剩余的最后一个页面
            if self._pages:
                self._active_page_id = next(iter(self._pages))
                self._page = self._pages[self._active_page_id]
            else:
                self._active_page_id = None

    def _build_emulation_kwargs(self) -> dict:
        """根据EmulationConfig构建context参数"""
        kwargs = {}
        if not self._emulation:
            return kwargs
        em = self._emulation
        if em.viewport:
            kwargs["viewport"] = em.viewport
        if em.locale:
            kwargs["locale"] = em.locale
        if em.timezone_id:
            kwargs["timezone_id"] = em.timezone_id
        if em.geolocation:
            kwargs["geolocation"] = em.geolocation
        if em.permissions:
            kwargs["permissions"] = em.permissions
        if em.color_scheme:
            kwargs["color_scheme"] = em.color_scheme
        if em.device_scale_factor is not None:
            kwargs["device_scale_factor"] = em.device_scale_factor
        if em.has_touch is not None:
            kwargs["has_touch"] = em.has_touch
        if em.is_mobile is not None:
            kwargs["is_mobile"] = em.is_mobile
        if em.user_agent:
            kwargs["user_agent"] = em.user_agent
        return kwargs

    # -----------------------------------------------------------------------
    # 1. Popup/Dialog 处理
    # -----------------------------------------------------------------------

    def set_dialog_strategy(self, strategy: DialogStrategy = DialogStrategy.ACCEPT,
                            prompt_text: str | None = None) -> None:
        """设置对话框自动处理策略

        Args:
            strategy: accept(确认) / dismiss(取消) / ignore(不自动处理)
            prompt_text: prompt对话框输入的文本
        """
        self._dialog_strategy = strategy
        self._dialog_prompt_text = prompt_text
        logger.debug(f"Dialog strategy set to: {strategy.value}")

    def _setup_dialog_handler(self) -> None:
        """注册对话框自动处理"""
        if self._dialog_handler_registered:
            return

        async def _on_dialog(dialog: Dialog) -> None:
            logger.info(f"Dialog detected: type={dialog.type}, message={dialog.message}")
            if self._dialog_strategy == DialogStrategy.ACCEPT:
                if dialog.type == "prompt" and self._dialog_prompt_text is not None:
                    await dialog.accept(self._dialog_prompt_text)
                else:
                    await dialog.accept()
            elif self._dialog_strategy == DialogStrategy.DISMISS:
                await dialog.dismiss()
            else:
                logger.warning(f"Dialog ignored (strategy=ignore): {dialog.type}")

        self._page.on("dialog", _on_dialog)
        self._dialog_handler_registered = True

    async def handle_dialog(self, accept: bool = True, prompt_text: str | None = None) -> None:
        """处理对话框（兼容BaseExecutor接口）"""
        self.set_dialog_strategy(
            DialogStrategy.ACCEPT if accept else DialogStrategy.DISMISS,
            prompt_text=prompt_text,
        )
        self._setup_dialog_handler()

    # -----------------------------------------------------------------------
    # 2. 网络拦截
    # -----------------------------------------------------------------------

    async def _setup_network_interception(self) -> None:
        """设置网络拦截"""
        if self._route_registered or not self._network_interceptor:
            return
        await self._page.route("**/*", self._network_interceptor.handle_route)
        self._route_registered = True
        logger.info("Network interception enabled")

    async def enable_network_interception(self) -> NetworkInterceptor:
        """启用网络拦截，返回拦截器实例供配置"""
        interceptor = self.network  # 触发懒初始化
        if not self._route_registered and self._page:
            await self._page.route("**/*", interceptor.handle_route)
            self._route_registered = True
        return interceptor

    async def mock_api(self, url_pattern: str, status: int = 200,
                       body: str | dict = "", content_type: str = "application/json",
                       headers: dict | None = None) -> NetworkInterceptor:
        """快捷Mock API响应"""
        interceptor = await self.enable_network_interception()
        mock_resp = MockResponse(
            status=status, body=body, content_type=content_type,
            headers=headers or {},
        )
        interceptor.mock(url_pattern, mock_resp)
        return interceptor

    async def block_resources(self, *resource_types: ResourceType) -> NetworkInterceptor:
        """快捷屏蔽资源类型"""
        interceptor = await self.enable_network_interception()
        interceptor.block(*resource_types)
        return interceptor

    async def get_network_requests(self) -> list[dict]:
        """获取网络请求列表（兼容BaseExecutor接口）"""
        if not self._network_interceptor:
            return []
        return [
            {"url": l.url, "method": l.method, "resource_type": l.resource_type,
             "status": l.status, "error": l.error}
            for l in self._network_interceptor.get_logs()
        ]

    async def get_network_logs(self, url_pattern: str | None = None,
                               method: str | None = None,
                               resource_type: str | None = None) -> list[NetworkLog]:
        """查询网络日志"""
        if not self._network_interceptor:
            return []
        return self._network_interceptor.get_logs(url_pattern, method, resource_type)

    async def get_failed_requests(self) -> list[NetworkLog]:
        """获取失败的请求"""
        if not self._network_interceptor:
            return []
        return self._network_interceptor.get_failed_requests()

    # -----------------------------------------------------------------------
    # 3. 多标签/窗口管理
    # -----------------------------------------------------------------------

    async def open_tab(self, url: str | None = None) -> Page:
        """打开新标签页

        Args:
            url: 可选，新标签页打开的URL

        Returns:
            新创建的Page实例
        """
        new_page = await self._context.new_page()
        self._register_page(new_page)
        self._page = new_page
        if url:
            await new_page.goto(url, wait_until="domcontentloaded")
        logger.info(f"New tab opened: {url or 'blank'}")
        return new_page

    async def close_tab(self, page: Page | None = None) -> None:
        """关闭标签页

        Args:
            page: 要关闭的Page，None则关闭当前页面
        """
        target = page or self._page
        if target is None:
            return
        page_id = str(id(target))
        await target.close()
        self._pages.pop(page_id, None)
        if self._active_page_id == page_id:
            if self._pages:
                self._active_page_id = next(iter(self._pages))
                self._page = self._pages[self._active_page_id]
            else:
                self._active_page_id = None
                self._page = None
        logger.info("Tab closed")

    async def switch_tab(self, index: int | None = None, page_id: str | None = None) -> Page:
        """切换标签页

        Args:
            index: 标签页索引（按创建顺序）
            page_id: 标签页ID（优先于index）

        Returns:
            切换后的Page实例
        """
        if page_id and page_id in self._pages:
            self._page = self._pages[page_id]
            self._active_page_id = page_id
        elif index is not None:
            keys = list(self._pages.keys())
            if 0 <= index < len(keys):
                pid = keys[index]
                self._page = self._pages[pid]
                self._active_page_id = pid
            else:
                raise IndexError(f"Tab index {index} out of range (total: {len(keys)})")
        else:
            raise ValueError("Must provide either index or page_id")

        # 退出iframe上下文
        self._current_frame = None
        logger.debug(f"Switched to tab: {self._active_page_id}")
        return self._page

    async def get_all_pages(self) -> list[Page]:
        """获取所有标签页"""
        return list(self._pages.values())

    async def get_all_page_urls(self) -> list[str]:
        """获取所有标签页的URL"""
        urls = []
        for p in self._pages.values():
            try:
                urls.append(p.url)
            except Exception:
                urls.append("")
        return urls

    async def get_tab_count(self) -> int:
        """获取标签页数量"""
        return len(self._pages)

    # -----------------------------------------------------------------------
    # 4. Iframe 支持
    # -----------------------------------------------------------------------

    async def enter_iframe(self, locator: Locator | str) -> FrameLocator:
        """进入iframe上下文

        Args:
            locator: iframe的定位器，或CSS选择器字符串

        Returns:
            FrameLocator实例
        """
        if isinstance(locator, str):
            frame = self.page.frame_locator(locator)
        else:
            pw_loc = await self._resolve_locator(locator)
            # 从Playwright Locator获取FrameLocator
            frame = pw_loc.content_frame
            if frame is None:
                # 降级：用CSS选择器
                frame = self.page.frame_locator(f"iframe[src*='{locator.primary_value}']")

        self._current_frame = frame
        logger.debug(f"Entered iframe: {locator if isinstance(locator, str) else locator.description}")
        return frame

    async def exit_iframe(self) -> None:
        """退出iframe，回到主页面上下文"""
        self._current_frame = None
        logger.debug("Exited iframe, back to main page context")

    async def is_in_iframe(self) -> bool:
        """当前是否在iframe上下文中"""
        return self._current_frame is not None

    def _get_active_locator_root(self):
        """获取当前活跃的定位器根（page或frame）"""
        if self._current_frame:
            return self._current_frame
        return self.page

    # -----------------------------------------------------------------------
    # 5. Cookie 管理
    # -----------------------------------------------------------------------

    async def get_cookies(self, urls: str | list[str] | None = None) -> list[dict]:
        """获取Cookie

        Args:
            urls: 可选，筛选指定URL的Cookie

        Returns:
            Cookie列表
        """
        if urls:
            return await self._context.cookies(urls)
        return await self._context.cookies()

    async def set_cookie(self, cookies: list[dict]) -> None:
        """设置Cookie

        Args:
            cookies: Cookie列表，每个dict包含name/value/domain等字段
        """
        await self._context.add_cookies(cookies)
        logger.debug(f"Set {len(cookies)} cookie(s)")

    async def set_cookie_simple(self, name: str, value: str,
                                domain: str = "", path: str = "/") -> None:
        """快捷设置单个Cookie"""
        cookie = {"name": name, "value": value, "path": path}
        if domain:
            cookie["domain"] = domain
        await self._context.add_cookies([cookie])

    async def delete_cookie(self, name: str, domain: str | None = None) -> None:
        """删除指定Cookie"""
        await self._context.clear_cookies(name=name, domain=domain)
        logger.debug(f"Deleted cookie: {name}")

    async def clear_cookies(self) -> None:
        """清除所有Cookie"""
        await self._context.clear_cookies()
        logger.debug("All cookies cleared")

    # -----------------------------------------------------------------------
    # 6. 认证状态持久化
    # -----------------------------------------------------------------------

    async def save_storage_state(self, path: str) -> None:
        """保存存储状态（Cookie + localStorage）用于登录持久化

        Args:
            path: 保存路径，如 "auth/admin.json"
        """
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=path)
        logger.info(f"Storage state saved to: {path}")

    async def load_storage_state(self, path: str) -> None:
        """加载存储状态（需要重启context才能生效）

        通常在start()时通过 storage_state 参数传入。
        此方法提供运行时重新创建context的方式。

        Args:
            path: 存储状态文件路径
        """
        if not Path(path).exists():
            raise FileNotFoundError(f"Storage state file not found: {path}")

        # 保存当前页面URL
        current_url = self._page.url if self._page else ""

        # 关闭旧context
        if self._context:
            await self._context.close()

        # 创建新context并加载状态
        context_kwargs = {
            "viewport": self.config.viewport,
            "ignore_https_errors": self.config.ignore_https_errors,
            "storage_state": path,
        }
        if self._emulation:
            context_kwargs.update(self._build_emulation_kwargs())

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(30000)

        # 重新注册增强功能
        self._dialog_handler_registered = False
        self._console_handler_registered = False
        self._page_event_handlers_registered = False
        self._download_handler_registered = False
        self._route_registered = False
        self._pages.clear()

        self._register_page(self._page)
        self._setup_dialog_handler()
        self._setup_console_handler()
        self._setup_page_event_handlers()
        self._setup_download_handler()
        await self._setup_network_interception()

        # 恢复页面
        if current_url:
            await self._page.goto(current_url, wait_until="domcontentloaded")

        logger.info(f"Storage state loaded from: {path}")

    # -----------------------------------------------------------------------
    # 7. 文件下载
    # -----------------------------------------------------------------------

    def _setup_download_handler(self) -> None:
        """注册下载事件处理"""
        if self._download_handler_registered:
            return

        async def _on_download(download: Download) -> None:
            info = DownloadInfo(
                filename=download.suggested_filename or "unknown",
                url=download.url,
                suggested_filename=download.suggested_filename or "unknown",
            )
            self._downloads.append(info)
            logger.info(f"Download started: {info.suggested_filename} from {info.url}")

        self._page.on("download", _on_download)
        self._download_handler_registered = True

    async def download_file(self, locator: Locator, save_path: str,
                            timeout: int | None = None) -> DownloadInfo:
        """点击元素触发下载并保存文件

        Args:
            locator: 触发下载的元素定位器
            save_path: 保存路径
            timeout: 下载超时(ms)

        Returns:
            DownloadInfo
        """
        pw_loc = await self._resolve_locator(locator)

        async with self._page.expect_download(timeout=timeout) as download_info:
            await pw_loc.click()

        download = await download_info.value
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(save_path)

        info = DownloadInfo(
            filename=download.suggested_filename or "unknown",
            url=download.url,
            suggested_filename=download.suggested_filename or "unknown",
            save_path=save_path,
            finished=True,
        )
        # 更新已有记录或追加
        for i, d in enumerate(self._downloads):
            if d.url == download.url and not d.finished:
                self._downloads[i] = info
                break
        else:
            self._downloads.append(info)

        logger.info(f"File downloaded: {info.suggested_filename} -> {save_path}")
        return info

    async def get_downloads(self) -> list[DownloadInfo]:
        """获取所有下载记录"""
        return list(self._downloads)

    async def clear_downloads(self) -> None:
        """清除下载记录"""
        self._downloads.clear()

    # -----------------------------------------------------------------------
    # 8. 控制台日志捕获
    # -----------------------------------------------------------------------

    def _setup_console_handler(self) -> None:
        """注册控制台消息监听"""
        if self._console_handler_registered:
            return

        def _on_console(msg: ConsoleMessage) -> None:
            log = ConsoleMessageLog(
                type=msg.type,
                text=msg.text,
                url=msg.location.get("url"),
                line_number=msg.location.get("lineNumber"),
                timestamp=time.time(),
            )
            self._console_messages.append(log)
            # 限制最大数量
            if len(self._console_messages) > 2000:
                self._console_messages = self._console_messages[-2000:]

        self._page.on("console", _on_console)
        self._console_handler_registered = True

    async def get_console_messages(self, msg_type: str | None = None) -> list[ConsoleMessageLog]:
        """获取控制台消息

        Args:
            msg_type: 可选，筛选类型 log/warn/error/info

        Returns:
            控制台消息列表
        """
        if msg_type:
            return [m for m in self._console_messages if m.type == msg_type]
        return list(self._console_messages)

    async def get_console_errors(self) -> list[ConsoleMessageLog]:
        """快捷获取控制台错误"""
        return await self.get_console_messages(msg_type="error")

    async def clear_console_messages(self) -> None:
        """清除控制台消息"""
        self._console_messages.clear()

    # -----------------------------------------------------------------------
    # 9. 页面事件监听
    # -----------------------------------------------------------------------

    def _setup_page_event_handlers(self) -> None:
        """注册页面事件监听"""
        if self._page_event_handlers_registered:
            return

        def _on_page_error(error: Exception) -> None:
            log = PageEventLog(
                event="error", detail=str(error),
                url=self._page.url if self._page else "", timestamp=time.time(),
            )
            self._page_events.append(log)
            logger.warning(f"Page error: {error}")
            if self._on_page_error:
                try:
                    self._on_page_error(error)
                except Exception:
                    pass

        def _on_page_crash() -> None:
            log = PageEventLog(
                event="crash", detail="Page crashed",
                url=self._page.url if self._page else "", timestamp=time.time(),
            )
            self._page_events.append(log)
            logger.error("Page crashed!")
            if self._on_page_crash:
                try:
                    self._on_page_crash()
                except Exception:
                    pass

        def _on_load() -> None:
            log = PageEventLog(
                event="load", detail="Page loaded",
                url=self._page.url if self._page else "", timestamp=time.time(),
            )
            self._page_events.append(log)
            if self._on_page_load:
                try:
                    self._on_page_load()
                except Exception:
                    pass

        self._page.on("pageerror", _on_page_error)
        self._page.on("crash", _on_page_crash)
        self._page.on("load", _on_load)

        self._page_event_handlers_registered = True

    def on_page_error(self, handler: Callable[[Exception], None]) -> None:
        """注册页面错误回调"""
        self._on_page_error = handler

    def on_page_crash(self, handler: Callable[[], None]) -> None:
        """注册页面崩溃回调"""
        self._on_page_crash = handler

    def on_page_load(self, handler: Callable[[], None]) -> None:
        """注册页面加载完成回调"""
        self._on_page_load = handler

    async def get_page_events(self, event_type: str | None = None) -> list[PageEventLog]:
        """获取页面事件记录

        Args:
            event_type: 可选，筛选事件类型 error/crash/load

        Returns:
            页面事件列表
        """
        if event_type:
            return [e for e in self._page_events if e.event == event_type]
        return list(self._page_events)

    async def clear_page_events(self) -> None:
        """清除页面事件记录"""
        self._page_events.clear()

    # -----------------------------------------------------------------------
    # 10. 高级等待策略
    # -----------------------------------------------------------------------

    async def wait_for_load_state(self, state: str = "load", timeout: int | None = None) -> None:
        """等待页面加载状态

        Args:
            state: load / domcontentloaded / networkidle
            timeout: 超时(ms)
        """
        await self.page.wait_for_load_state(state, timeout=timeout)
        logger.debug(f"Page reached state: {state}")

    async def wait_for_url(self, url: str | None = None, pattern: str | None = None,
                           timeout: int | None = None) -> None:
        """等待URL变化

        Args:
            url: 精确匹配URL
            pattern: URL正则模式
            timeout: 超时(ms)
        """
        if pattern:
            await self.page.wait_for_url(pattern, timeout=timeout)
        elif url:
            await self.page.wait_for_url(url, timeout=timeout)
        else:
            raise ValueError("Must provide either url or pattern")
        logger.debug(f"URL matched: {url or pattern}")

    async def wait_for_response(self, url_pattern: str,
                                timeout: int | None = None) -> dict:
        """等待指定URL的响应

        Args:
            url_pattern: URL匹配模式（支持glob）
            timeout: 超时(ms)

        Returns:
            响应信息 dict，包含 url, status, headers, body
        """
        async with self.page.expect_response(url_pattern, timeout=timeout) as resp_info:
            pass
        response = await resp_info.value
        body = None
        try:
            body = await response.text()
        except Exception:
            pass
        result = {
            "url": response.url,
            "status": response.status,
            "headers": response.headers,
            "body": body,
        }
        logger.debug(f"Response captured: {response.url} [{response.status}]")
        return result

    async def wait_for_function(self, expression: str,
                                timeout: int | None = None) -> Any:
        """等待JavaScript表达式返回真值

        Args:
            expression: JavaScript表达式
            timeout: 超时(ms)
        """
        return await self.page.wait_for_function(expression, timeout=timeout)

    # -----------------------------------------------------------------------
    # 11. 设备模拟
    # -----------------------------------------------------------------------

    def set_emulation(self, emulation: EmulationConfig) -> None:
        """设置设备模拟配置（需在start()之前调用）

        Args:
            emulation: 模拟配置
        """
        self._emulation = emulation
        logger.debug(f"Emulation configured: locale={emulation.locale}, "
                      f"tz={emulation.timezone_id}, viewport={emulation.viewport}")

    async def emulate_device(self, device_name: str) -> None:
        """使用Playwright内置设备描述进行模拟（需在start()之前调用）

        Args:
            device_name: 设备名称，如 "iPhone 13", "Pixel 5"
        """
        if not self._playwright:
            # 需要先启动playwright获取设备列表
            pw = await async_playwright().start()
            device = pw.devices.get(device_name)
            await pw.stop()
        else:
            device = self._playwright.devices.get(device_name)

        if not device:
            raise ValueError(f"Unknown device: {device_name}. "
                             f"Available: {list(self._playwright.devices.keys()) if self._playwright else 'start first'}")

        self._emulation = EmulationConfig(
            viewport=device.get("viewport"),
            locale=device.get("locale"),
            timezone_id=device.get("timezoneId"),
            geolocation=device.get("geolocation"),
            permissions=device.get("permissions", []),
            color_scheme=device.get("colorScheme"),
            device_scale_factor=device.get("deviceScaleFactor"),
            has_touch=device.get("hasTouch"),
            is_mobile=device.get("isMobile"),
            user_agent=device.get("userAgent"),
        )
        logger.info(f"Device emulation set: {device_name}")

    async def grant_permissions(self, permissions: list[str],
                                origin: str | None = None) -> None:
        """运行时授予浏览器权限

        Args:
            permissions: 权限列表，如 ["geolocation", "notifications"]
            origin: 可选，指定origin
        """
        kwargs = {"permissions": permissions}
        if origin:
            kwargs["origin"] = origin
        await self._context.grant_permissions(**kwargs)
        logger.debug(f"Permissions granted: {permissions}")

    async def set_geolocation(self, latitude: float, longitude: float) -> None:
        """运行时设置地理位置"""
        await self._context.set_geolocation({"latitude": latitude, "longitude": longitude})
        logger.debug(f"Geolocation set: ({latitude}, {longitude})")

    # -----------------------------------------------------------------------
    # 12. 截图增强
    # -----------------------------------------------------------------------

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> bytes:
        """整页截图"""
        kwargs = {"full_page": full_page}
        if path:
            kwargs["path"] = path
        return await self.page.screenshot(**kwargs)

    async def screenshot_element(self, locator: Locator, path: str | None = None) -> bytes:
        """元素截图

        Args:
            locator: 元素定位器
            path: 保存路径

        Returns:
            截图bytes
        """
        pw_loc = await self._resolve_locator(locator)
        kwargs = {}
        if path:
            kwargs["path"] = path
        return await pw_loc.screenshot(**kwargs)

    async def screenshot_clip(self, clip: dict[str, int], path: str | None = None) -> bytes:
        """区域截图

        Args:
            clip: 裁剪区域 {"x": 0, "y": 0, "width": 100, "height": 100}
            path: 保存路径

        Returns:
            截图bytes
        """
        kwargs = {"clip": clip}
        if path:
            kwargs["path"] = path
        return await self.page.screenshot(**kwargs)

    async def screenshot_with_mask(self, path: str | None = None,
                                   full_page: bool = False,
                                   mask: list[Locator] | None = None,
                                   mask_color: str = "#FF00FF") -> bytes:
        """带遮罩的截图（隐藏敏感元素）

        Args:
            path: 保存路径
            full_page: 是否全页
            mask: 需要遮罩的元素定位器列表
            mask_color: 遮罩颜色

        Returns:
            截图bytes
        """
        kwargs = {"full_page": full_page}
        if path:
            kwargs["path"] = path
        if mask:
            pw_locators = []
            for loc in mask:
                pw_locators.append(await self._resolve_locator(loc))
            kwargs["mask"] = pw_locators
            kwargs["mask_color"] = mask_color
        return await self.page.screenshot(**kwargs)

    # -----------------------------------------------------------------------
    # 定位器解析（增强：支持iframe上下文）
    # -----------------------------------------------------------------------

    async def _resolve_locator(self, locator: Locator) -> PwLocator:
        """将统一Locator解析为Playwright Locator

        按降级链依次尝试，返回第一个匹配的元素。
        支持iframe上下文。
        """
        root = self._get_active_locator_root()
        chain = locator.build_chain()

        for loc_type, loc_value, options in chain:
            try:
                pw_locator = self._create_pw_locator(root, loc_type, loc_value, options)
                if await pw_locator.count() > 0:
                    return pw_locator
            except Exception:
                continue

        # 降级链全部失败，返回主定位器（让后续操作抛出明确错误）
        primary = chain[0]
        return self._create_pw_locator(root, primary[0], primary[1], primary[2])

    def _create_pw_locator(self, root, loc_type: LocatorType, value: str, options: dict) -> PwLocator:
        """根据定位器类型创建Playwright Locator

        Args:
            root: Page 或 FrameLocator
        """
        if loc_type == LocatorType.ROLE:
            return root.get_by_role(value, **options)
        elif loc_type == LocatorType.TEST_ID:
            return root.get_by_test_id(value)
        elif loc_type == LocatorType.LABEL:
            return root.get_by_label(value)
        elif loc_type == LocatorType.PLACEHOLDER:
            return root.get_by_placeholder(value)
        elif loc_type == LocatorType.TEXT:
            return root.get_by_text(value, **options)
        elif loc_type == LocatorType.ALT_TEXT:
            return root.get_by_alt_text(value)
        elif loc_type == LocatorType.TITLE:
            return root.get_by_title(value)
        elif loc_type == LocatorType.CSS:
            return root.locator(value)
        elif loc_type == LocatorType.XPATH:
            return root.locator(f"xpath={value}")
        else:
            return root.locator(value)

    # -----------------------------------------------------------------------
    # 基础操作（保持原有接口）
    # -----------------------------------------------------------------------

    async def navigate(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded")
        # 退出iframe上下文
        self._current_frame = None
        logger.debug(f"Navigated to: {url}")

    async def click(self, locator: Locator) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.click()
        logger.debug(f"Clicked: {locator.description}")

    async def type_text(self, locator: Locator, text: str, clear: bool = True) -> None:
        pw_loc = await self._resolve_locator(locator)
        if clear:
            await pw_loc.fill("")
        await pw_loc.type(text)
        logger.debug(f"Typed '{text}' into: {locator.description}")

    async def fill(self, locator: Locator, value: str) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.fill(value)
        logger.debug(f"Filled '{value}' into: {locator.description}")

    async def select_option(self, locator: Locator, value: str | list[str]) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.select_option(value)

    async def check(self, locator: Locator) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.check()

    async def uncheck(self, locator: Locator) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.uncheck()

    async def hover(self, locator: Locator) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.hover()

    async def press_key(self, key: str) -> None:
        await self.page.keyboard.press(key)

    async def wait_for(self, locator: Locator, timeout: int | None = None) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.wait_for(state="visible", timeout=timeout)

    async def get_accessibility_tree(self) -> dict:
        """获取辅助功能树快照"""
        snapshot = await self.page.accessibility.snapshot()
        return snapshot or {}

    async def get_text(self, locator: Locator) -> str:
        pw_loc = await self._resolve_locator(locator)
        return await pw_loc.text_content() or ""

    async def is_visible(self, locator: Locator) -> bool:
        try:
            pw_loc = await self._resolve_locator(locator)
            return await pw_loc.is_visible()
        except Exception:
            return False

    async def evaluate(self, expression: str) -> Any:
        return await self.page.evaluate(expression)

    async def get_url(self) -> str:
        return self.page.url

    async def get_title(self) -> str:
        return await self.page.title()

    async def go_back(self) -> None:
        await self.page.go_back()

    async def go_forward(self) -> None:
        await self.page.go_forward()

    async def reload(self) -> None:
        await self.page.reload()

    async def upload_file(self, locator: Locator, file_path: str) -> None:
        pw_loc = await self._resolve_locator(locator)
        await pw_loc.set_input_files(file_path)

    async def drag(self, source: Locator, target: Locator) -> None:
        pw_source = await self._resolve_locator(source)
        pw_target = await self._resolve_locator(target)
        await pw_source.drag_to(pw_target)

    async def start_tracing(self, screenshots: bool = True, snapshots: bool = True) -> None:
        """开始记录Trace"""
        if self._context:
            await self._context.tracing.start(screenshots=screenshots, snapshots=snapshots)

    async def stop_tracing(self, path: str) -> None:
        """停止记录Trace并保存"""
        if self._context:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            await self._context.tracing.stop(path=path)

    # -----------------------------------------------------------------------
    # 便捷方法
    # -----------------------------------------------------------------------

    async def close(self) -> None:
        """关闭当前页面/标签"""
        if self._page and len(self._pages) > 1:
            await self.close_tab(self._page)
        else:
            await self.stop()

    async def get_page_info(self) -> dict:
        """获取当前页面综合信息"""
        return {
            "url": await self.get_url(),
            "title": await self.get_title(),
            "viewport": self.page.viewport_size,
            "tab_count": len(self._pages),
            "in_iframe": self._current_frame is not None,
            "dialog_strategy": self._dialog_strategy.value,
            "network_interception": self._network_interceptor is not None,
            "console_messages": len(self._console_messages),
            "page_events": len(self._page_events),
            "downloads": len(self._downloads),
        }
