"""执行器基类 - 统一Action抽象接口"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional

from uiai.core.locator import Locator
from uiai.core.platform import Platform


class BaseExecutor(ABC):
    """执行器基类 - 定义统一的操作接口

    所有平台执行器（Playwright/Appium/Maestro）都实现此接口，
    上层调度代码无需关心底层平台差异。
    """

    platform: Platform

    @abstractmethod
    async def start(self, **kwargs) -> None:
        """启动执行器（打开浏览器/连接设备）"""

    @abstractmethod
    async def stop(self) -> None:
        """停止执行器（关闭浏览器/断开设备）"""

    @abstractmethod
    async def navigate(self, url: str) -> None:
        """导航到指定URL"""

    @abstractmethod
    async def click(self, locator: Locator) -> None:
        """点击元素"""

    @abstractmethod
    async def type_text(self, locator: Locator, text: str, clear: bool = True) -> None:
        """输入文本"""

    @abstractmethod
    async def fill(self, locator: Locator, value: str) -> None:
        """填充表单字段"""

    @abstractmethod
    async def select_option(self, locator: Locator, value: str | list[str]) -> None:
        """选择下拉选项"""

    @abstractmethod
    async def check(self, locator: Locator) -> None:
        """勾选复选框"""

    @abstractmethod
    async def uncheck(self, locator: Locator) -> None:
        """取消勾选复选框"""

    @abstractmethod
    async def hover(self, locator: Locator) -> None:
        """悬停"""

    @abstractmethod
    async def press_key(self, key: str) -> None:
        """按键"""

    @abstractmethod
    async def wait_for(self, locator: Locator, timeout: int | None = None) -> None:
        """等待元素出现"""

    @abstractmethod
    async def screenshot(self, path: str | None = None, full_page: bool = False) -> bytes:
        """截图"""

    @abstractmethod
    async def get_accessibility_tree(self) -> dict:
        """获取辅助功能树（accessibility tree）"""

    @abstractmethod
    async def get_text(self, locator: Locator) -> str:
        """获取元素文本"""

    @abstractmethod
    async def is_visible(self, locator: Locator) -> bool:
        """判断元素是否可见"""

    @abstractmethod
    async def evaluate(self, expression: str) -> Any:
        """执行JavaScript表达式"""

    @abstractmethod
    async def get_url(self) -> str:
        """获取当前URL"""

    @abstractmethod
    async def get_title(self) -> str:
        """获取页面标题"""

    # --- 高级操作（带默认实现，子类可覆写） ---

    async def fill_form(self, fields: list[tuple[Locator, str]]) -> None:
        """批量填充表单"""
        for locator, value in fields:
            await self.fill(locator, value)

    async def drag(self, source: Locator, target: Locator) -> None:
        """拖拽（默认实现：click源→click目标，子类应覆写）"""
        await self.click(source)
        await self.click(target)

    async def upload_file(self, locator: Locator, file_path: str) -> None:
        """上传文件（默认抛出未实现）"""
        raise NotImplementedError(f"upload_file not implemented for {self.__class__.__name__}")

    async def handle_dialog(self, accept: bool = True, prompt_text: str | None = None) -> None:
        """处理对话框"""
        raise NotImplementedError(f"handle_dialog not implemented for {self.__class__.__name__}")

    async def go_back(self) -> None:
        """浏览器后退"""
        raise NotImplementedError(f"go_back not implemented for {self.__class__.__name__}")

    async def go_forward(self) -> None:
        """浏览器前进"""
        raise NotImplementedError(f"go_forward not implemented for {self.__class__.__name__}")

    async def reload(self) -> None:
        """刷新页面"""
        raise NotImplementedError(f"reload not implemented for {self.__class__.__name__}")

    async def close(self) -> None:
        """关闭当前页面/标签"""
        await self.stop()

    async def get_console_messages(self) -> list[str]:
        """获取控制台消息"""
        return []

    async def get_network_requests(self) -> list[dict]:
        """获取网络请求列表"""
        return []
