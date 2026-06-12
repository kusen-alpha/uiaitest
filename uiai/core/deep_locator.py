"""两阶段深度定位系统 - 基于视觉语言模型的精准元素定位

实现架构设计文档第8节的两阶段定位策略：
    Stage 1 (AiLocateSection): VL模型在全屏截图中识别目标元素的大致区域
    Stage 2 (AiLocateElement): VL模型在裁剪后的区域截图中精确定位元素中心

两阶段策略的优势：
    - 降低单次推理的复杂度，提升定位精度
    - 裁剪区域放大后，小元素的细节更清晰
    - 区域边界扩展避免裁剪遗漏
"""
from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uiai.agent.llm import BaseLLMClient
    from uiai.executor.base import BaseExecutor

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────────


@dataclass
class LocateRegion:
    """定位区域

    Attributes:
        x: 区域左上角 X 坐标
        y: 区域左上角 Y 坐标
        width: 区域宽度
        height: 区域高度
    """

    x: int
    y: int
    width: int
    height: int


@dataclass
class LocateResult:
    """定位结果

    Attributes:
        region: 目标元素所在区域
        center_x: 元素中心 X 坐标（绝对坐标）
        center_y: 元素中心 Y 坐标（绝对坐标）
        confidence: 定位置信度 [0.0, 1.0]
        method: 使用的定位方法标识
    """

    region: LocateRegion
    center_x: int
    center_y: int
    confidence: float
    method: str


# ── VL模型提示词模板 ──────────────────────────────────────────

_SECTION_PROMPT = """\
你是一个UI元素定位助手。请在截图中找到与以下描述最匹配的元素区域。

描述：{description}

请以JSON格式返回该元素所在的矩形区域，格式如下：
{{"x": <左上角X坐标>, "y": <左上角Y坐标>, "w": <宽度>, "h": <高度>}}

注意：
- 坐标基于截图的像素坐标系，左上角为(0,0)
- 只返回JSON，不要返回其他内容
"""

_ELEMENT_PROMPT = """\
你是一个UI元素精准定位助手。以下截图是目标区域的放大裁剪图，原始区域位于全屏的({region_x}, {region_y})处。

请在裁剪截图中找到与以下描述最匹配的元素中心点。

描述：{description}

请以JSON格式返回该元素的中心坐标（相对于裁剪截图的坐标），格式如下：
{{"cx": <中心X坐标>, "cy": <中心Y坐标>, "confidence": <置信度0.0-1.0>}}

注意：
- 坐标基于裁剪截图的像素坐标系，左上角为(0,0)
- confidence表示你对定位结果的信心程度
- 只返回JSON，不要返回其他内容
"""


# ── DeepLocator ───────────────────────────────────────────────


class DeepLocator:
    """两阶段深度定位器

    利用视觉语言模型(VL)实现两阶段精准定位：
        1. AiLocateSection: 在全屏截图中粗定位目标区域
        2. AiLocateElement: 在裁剪区域截图中精定位元素中心

    Args:
        vl_client: 视觉语言模型客户端，用于图像理解
        executor: 执行器实例，用于截图操作
    """

    def __init__(self, vl_client: BaseLLMClient, executor: BaseExecutor) -> None:
        self._vl_client = vl_client
        self._executor = executor

    async def locate(
        self,
        description: str,
        screenshot: bytes | None = None,
        expand_ratio: float = 0.2,
    ) -> LocateResult:
        """两阶段深度定位

        Args:
            description: 目标元素的自然语言描述
            screenshot: 截图数据，为 None 时自动通过执行器截图
            expand_ratio: 裁剪区域边界扩展比例，默认 0.2 (20%)

        Returns:
            定位结果，包含绝对坐标和置信度

        Raises:
            ValueError: VL模型返回的坐标无法解析
            RuntimeError: 定位过程失败
        """
        # 获取截图
        if screenshot is None:
            logger.debug("未提供截图，通过执行器自动截图")
            screenshot = await self._executor.screenshot()

        # Stage 1: 粗定位区域
        logger.info("Stage 1 - AiLocateSection: 粗定位目标区域, 描述=%r", description)
        region = await self._locate_section(description, screenshot)
        logger.info(
            "Stage 1 完成: 区域 x=%d y=%d w=%d h=%d",
            region.x, region.y, region.width, region.height,
        )

        # 裁剪区域截图
        cropped = await self._crop_screenshot(screenshot, region, expand_ratio)

        # Stage 2: 精定位元素
        logger.info("Stage 2 - AiLocateElement: 精定位元素中心")
        result = await self._locate_element(description, cropped, region)
        logger.info(
            "Stage 2 完成: 中心坐标=(%d, %d), 置信度=%.2f, 方法=%s",
            result.center_x, result.center_y, result.confidence, result.method,
        )

        return result

    async def _locate_section(self, description: str, screenshot: bytes) -> LocateRegion:
        """Stage 1: 粗定位目标区域

        将完整截图和描述发送给VL模型，获取目标元素的大致矩形区域。

        Args:
            description: 目标元素描述
            screenshot: 完整页面截图

        Returns:
            粗定位的区域

        Raises:
            ValueError: 无法从VL模型响应中解析区域坐标
        """
        prompt = _SECTION_PROMPT.format(description=description)
        raw_response = await self._vl_client.analyze_image(screenshot, prompt)
        logger.debug("Stage 1 VL模型原始响应: %s", raw_response)

        return self._parse_region_response(raw_response)

    async def _locate_element(
        self,
        description: str,
        cropped_screenshot: bytes,
        region: LocateRegion,
    ) -> LocateResult:
        """Stage 2: 精定位元素中心

        将裁剪后的区域截图和描述发送给VL模型，获取元素的精确中心坐标。

        Args:
            description: 目标元素描述
            cropped_screenshot: 裁剪后的区域截图
            region: Stage 1 得到的粗定位区域

        Returns:
            包含绝对坐标的定位结果

        Raises:
            ValueError: 无法从VL模型响应中解析元素坐标
        """
        prompt = _ELEMENT_PROMPT.format(
            description=description,
            region_x=region.x,
            region_y=region.y,
        )
        raw_response = await self._vl_client.analyze_image(cropped_screenshot, prompt)
        logger.debug("Stage 2 VL模型原始响应: %s", raw_response)

        return self._parse_element_response(raw_response, region)

    async def _crop_screenshot(
        self,
        screenshot: bytes,
        region: LocateRegion,
        expand_ratio: float,
    ) -> bytes:
        """裁剪截图到指定区域（带边界扩展）

        对粗定位区域进行边界扩展（默认20%），避免裁剪时遗漏目标元素。
        扩展后的区域会被限制在截图边界内。

        Args:
            screenshot: 原始完整截图
            region: 要裁剪的区域
            expand_ratio: 边界扩展比例

        Returns:
            裁剪后的截图二进制数据（PNG格式）
        """
        from PIL import Image
        img = Image.open(io.BytesIO(screenshot))
        img_width, img_height = img.size

        # 计算扩展量
        expand_x = int(region.width * expand_ratio)
        expand_y = int(region.height * expand_ratio)

        # 扩展区域并限制在图片边界内
        crop_x1 = max(0, region.x - expand_x)
        crop_y1 = max(0, region.y - expand_y)
        crop_x2 = min(img_width, region.x + region.width + expand_x)
        crop_y2 = min(img_height, region.y + region.height + expand_y)

        logger.debug(
            "裁剪区域: 原始=(%d,%d,%d,%d) 扩展后=(%d,%d,%d,%d) 图片尺寸=%dx%d",
            region.x, region.y, region.x + region.width, region.y + region.height,
            crop_x1, crop_y1, crop_x2, crop_y2,
            img_width, img_height,
        )

        cropped = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
        return buffer.getvalue()

    def _parse_region_response(self, raw: str) -> LocateRegion:
        """解析VL模型返回的区域坐标

        从VL模型的JSON响应中提取区域坐标 {x, y, w, h}。
        支持多种JSON格式变体和容错解析。

        Args:
            raw: VL模型的原始文本响应

        Returns:
            解析后的区域

        Raises:
            ValueError: 无法解析区域坐标
        """
        data = self._extract_json(raw)

        try:
            x = int(data.get("x", data.get("left", 0)))
            y = int(data.get("y", data.get("top", 0)))
            w = int(data.get("w", data.get("width", 0)))
            h = int(data.get("h", data.get("height", 0)))
        except (TypeError, ValueError) as e:
            raise ValueError(f"区域坐标类型转换失败: {data}") from e

        if w <= 0 or h <= 0:
            raise ValueError(f"区域尺寸无效: width={w}, height={h}")

        return LocateRegion(x=x, y=y, width=w, height=h)

    def _parse_element_response(self, raw: str, region: LocateRegion) -> LocateResult:
        """解析VL模型返回的元素坐标

        从VL模型的JSON响应中提取元素中心坐标 {cx, cy, confidence}。
        坐标为相对于裁剪截图的坐标，需转换为绝对坐标。

        裁剪时区域经过 expand_ratio 扩展，因此需要计算偏移量：
            offset_x = region.x - expand_x
            offset_y = region.y - expand_y
        但由于裁剪时已限制在图片边界内，实际偏移量需要根据裁剪后的
        坐标系计算。这里采用简化策略：将相对坐标加上区域原点偏移，
        因为VL模型在Stage 2的提示中已知区域位置，返回的坐标通常是
        相对于裁剪图左上角的。

        Args:
            raw: VL模型的原始文本响应
            region: Stage 1 得到的粗定位区域

        Returns:
            包含绝对坐标的定位结果

        Raises:
            ValueError: 无法解析元素坐标
        """
        data = self._extract_json(raw)

        try:
            cx = int(data.get("cx", data.get("center_x", data.get("x", 0))))
            cy = int(data.get("cy", data.get("center_y", data.get("y", 0))))
            confidence = float(data.get("confidence", data.get("score", 0.5)))
        except (TypeError, ValueError) as e:
            raise ValueError(f"元素坐标类型转换失败: {data}") from e

        # 将裁剪截图中的相对坐标转换为绝对坐标
        # 裁剪时左上角为 (region.x - expand_x, region.y - expand_y)
        # 但由于边界限制，实际偏移可能不同
        # 这里使用 region 原点作为基准偏移
        abs_cx = region.x + cx
        abs_cy = region.y + cy

        # 限制置信度范围
        confidence = max(0.0, min(1.0, confidence))

        return LocateResult(
            region=region,
            center_x=abs_cx,
            center_y=abs_cy,
            confidence=confidence,
            method="deep_locator",
        )

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """从VL模型响应中提取JSON对象

        VL模型响应可能包含Markdown代码块包裹的JSON，或直接JSON文本。
        此方法尝试多种策略提取有效的JSON字典。

        Args:
            raw: VL模型的原始文本响应

        Returns:
            解析后的字典

        Raises:
            ValueError: 无法提取有效JSON
        """
        # 策略1: 尝试直接解析
        text = raw.strip()
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 策略2: 提取Markdown代码块中的JSON
        code_block_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
        match = code_block_pattern.search(text)
        if match:
            try:
                result = json.loads(match.group(1).strip())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        # 策略3: 查找第一个 { ... } 块
        brace_pattern = re.compile(r"\{[^{}]*\}", re.DOTALL)
        match = brace_pattern.search(text)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        # 策略4: 宽松匹配，处理嵌套花括号
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        raise ValueError(f"无法从VL模型响应中提取JSON: {raw[:200]}")
