"""纯视觉Agent - 不依赖DOM，仅通过截图和坐标操作"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

from uiai.agent.llm import BaseLLMClient, LLMMessage
from uiai.executor.base import BaseExecutor

logger = logging.getLogger(__name__)


@dataclass
class VisualLocation:
    """视觉定位结果"""
    x: float
    y: float
    width: float = 0
    height: float = 0
    confidence: float = 1.0
    description: str = ""


class VisualAgent:
    """纯视觉Agent

    不依赖DOM/辅助功能树，仅通过截图和VL模型理解页面。
    适用于Canvas/WebGL/游戏等无障碍树缺失场景。

    参考Playwright MCP的Vision模式（click_xy, move_xy, drag_xy）。
    """

    def __init__(self, vl_model: BaseLLMClient | None = None, executor: BaseExecutor | None = None):
        self.vl_model = vl_model
        self.executor = executor

    async def understand_page(self) -> dict:
        """理解当前页面状态"""
        if not self.executor or not self.vl_model:
            return {"error": "Executor or VL model not configured"}

        screenshot = await self.executor.screenshot()
        prompt = "请详细描述当前页面的内容，包括所有可见的UI元素、文字、按钮、输入框等。"

        messages = [LLMMessage(role="user", content=prompt)]
        description = await self.vl_model.chat_with_images(messages, [screenshot])

        return {
            "description": description,
            "url": await self.executor.get_url(),
            "title": await self.executor.get_title(),
        }

    async def locate_element(self, description: str) -> VisualLocation | None:
        """通过自然语言描述定位元素

        Args:
            description: 元素描述，如"登录按钮"、"搜索输入框"

        Returns:
            VisualLocation 或 None
        """
        if not self.executor or not self.vl_model:
            return None

        screenshot = await self.executor.screenshot()
        prompt = f"""在页面中找到"{description}"元素，返回其位置。

请以JSON格式返回：
{{"x": 中心点X坐标, "y": 中心点Y坐标, "width": 宽度, "height": 高度, "confidence": 置信度0-1}}

如果找不到该元素，返回 {{"found": false}}"""

        messages = [LLMMessage(role="user", content=prompt)]
        response = await self.vl_model.chat_with_images(messages, [screenshot])

        # 解析响应
        try:
            import json
            # 尝试从响应中提取JSON
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                data = json.loads(response[start:end])
                if data.get("found") is False:
                    return None
                return VisualLocation(
                    x=data.get("x", 0),
                    y=data.get("y", 0),
                    width=data.get("width", 0),
                    height=data.get("height", 0),
                    confidence=data.get("confidence", 0.5),
                    description=description,
                )
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    async def click_element(self, description: str) -> bool:
        """通过自然语言描述点击元素"""
        location = await self.locate_element(description)
        if location and self.executor:
            # 使用Playwright的mouse.click进行坐标点击
            page = getattr(self.executor, "_page", None)
            if page:
                await page.mouse.click(location.x, location.y)
                return True
        return False

    async def verify_visual(self, description: str) -> bool:
        """视觉语义验证

        用自然语言描述预期页面状态，VL模型判断是否匹配。
        """
        if not self.executor or not self.vl_model:
            return False

        screenshot = await self.executor.screenshot()
        prompt = f"""请判断当前页面是否符合以下描述：
"{description}"

请只回答 true 或 false。"""

        messages = [LLMMessage(role="user", content=prompt)]
        response = await self.vl_model.chat_with_images(messages, [screenshot])

        return "true" in response.lower()

    async def find_visual_anomalies(self) -> list[dict]:
        """发现页面视觉异常"""
        if not self.executor or not self.vl_model:
            return []

        screenshot = await self.executor.screenshot()
        prompt = """请检查当前页面是否存在以下视觉异常：
1. 文字重叠或截断
2. 按钮或元素被遮挡
3. 布局错位或溢出
4. 图片加载失败
5. 颜色对比度不足

请以JSON列表格式返回发现的异常：
[{"type": "异常类型", "description": "描述", "severity": "high/medium/low"}]

如果没有异常，返回空列表 []"""

        messages = [LLMMessage(role="user", content=prompt)]
        response = await self.vl_model.chat_with_images(messages, [screenshot])

        try:
            import json
            if "[" in response and "]" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        return []
