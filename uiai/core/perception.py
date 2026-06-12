"""感知模式引擎 - 多模态页面感知与格式化

提供 A11y Snapshot、DOM 序列化、截图、混合四种感知模式，
将页面状态转换为 LLM 可消费的文本表示，并支持 token 预估与截断。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from uiai.agent.llm import BaseLLMClient
    from uiai.executor.base import BaseExecutor

logger = logging.getLogger(__name__)

# 粗略估算：1 个中文字符 ≈ 2 token，1 个英文单词 ≈ 1.3 token
# 统一按字符数估算：英文 4 字符 ≈ 1 token，中文 1 字符 ≈ 2 token
_CHARS_PER_TOKEN_EN = 4.0
_CHARS_PER_TOKEN_ZH = 0.5


class PerceptionMode(Enum):
    """感知模式枚举"""

    A11Y_SNAPSHOT = "a11y_snapshot"
    DOM_SERIALIZE = "dom_serialize"
    VISUAL_SCREENSHOT = "visual_screenshot"
    HYBRID = "hybrid"


@dataclass
class PerceptionResult:
    """感知结果数据类

    Attributes:
        mode: 使用的感知模式
        a11y_snapshot: 辅助功能树快照文本
        dom_tree: 带索引的 DOM 序列化文本
        screenshot: 页面截图二进制数据
        url: 当前页面 URL
        title: 当前页面标题
        timestamp: 感知时间戳
        token_estimate: 预估 token 数量
    """

    mode: PerceptionMode
    a11y_snapshot: Optional[str] = None
    dom_tree: Optional[str] = None
    screenshot: Optional[bytes] = None
    url: str = ""
    title: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    token_estimate: int = 0


def _estimate_text_tokens(text: str) -> int:
    """估算文本的 token 数量

    采用简单的字符级估算策略：
    - 中文字符：每字符约 2 token
    - 英文/其他字符：每 4 字符约 1 token

    Args:
        text: 待估算文本

    Returns:
        预估 token 数量
    """
    if not text:
        return 0

    zh_chars = 0
    en_chars = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            zh_chars += 1
        else:
            en_chars += 1

    tokens = zh_chars / _CHARS_PER_TOKEN_ZH + en_chars / _CHARS_PER_TOKEN_EN
    return max(1, int(tokens))


def _truncate_text(text: str, max_tokens: int) -> str:
    """按 token 预算截断文本

    Args:
        text: 原始文本
        max_tokens: 最大 token 预算

    Returns:
        截断后的文本，末尾附加截断提示
    """
    if not text:
        return text

    estimated = _estimate_text_tokens(text)
    if estimated <= max_tokens:
        return text

    # 按比例估算可保留的字符数
    ratio = max_tokens / estimated
    keep_chars = int(len(text) * ratio * 0.9)  # 留 10% 余量给截断提示
    truncated = text[:keep_chars]

    # 尝试在最后一个换行符处截断，避免截断在行中间
    last_newline = truncated.rfind("\n")
    if last_newline > keep_chars * 0.5:
        truncated = truncated[:last_newline]

    return truncated + "\n... [内容已截断，原始 token 估算: {0}]".format(estimated)


class PerceptionEngine:
    """感知模式引擎

    根据指定模式采集页面状态，生成 LLM 可消费的感知数据。
    支持四种模式：A11y Snapshot、DOM 序列化、截图、混合模式。

    混合模式策略：
        1. 优先使用 A11y Snapshot（token 效率最高）
        2. 若 A11y Snapshot 为空或页面无 DOM（Canvas/WebGL），回退到截图
        3. 始终包含 URL 和标题信息
        4. 预估 token 数量，超出预算时截断

    Args:
        executor: 执行器实例，用于操作页面
        vl_client: 视觉语言模型客户端，用于截图描述（可选）
        default_mode: 默认感知模式，默认为 HYBRID
    """

    def __init__(
        self,
        executor: BaseExecutor,
        vl_client: Optional[BaseLLMClient] = None,
        default_mode: PerceptionMode = PerceptionMode.HYBRID,
    ) -> None:
        self._executor = executor
        self._vl_client = vl_client
        self._default_mode = default_mode

    async def perceive(self, mode: Optional[PerceptionMode] = None) -> PerceptionResult:
        """执行页面感知

        Args:
            mode: 感知模式，为 None 时使用默认模式

        Returns:
            感知结果

        Raises:
            ValueError: 不支持的感知模式
        """
        effective_mode = mode or self._default_mode
        logger.info("开始页面感知，模式: %s", effective_mode.value)

        match effective_mode:
            case PerceptionMode.A11Y_SNAPSHOT:
                return await self._perceive_a11y()
            case PerceptionMode.DOM_SERIALIZE:
                return await self._perceive_dom()
            case PerceptionMode.VISUAL_SCREENSHOT:
                return await self._perceive_screenshot()
            case PerceptionMode.HYBRID:
                return await self.get_hybrid()
            case _:
                raise ValueError(f"不支持的感知模式: {effective_mode}")

    async def get_a11y_snapshot(self) -> str:
        """获取辅助功能树快照文本

        通过执行器获取 accessibility tree，序列化为可读的缩进文本格式。

        Returns:
            辅助功能树快照文本
        """
        try:
            tree = await self._executor.get_accessibility_tree()
            return self._serialize_a11y_tree(tree)
        except Exception:
            logger.exception("获取辅助功能树失败")
            return ""

    async def get_dom_serialized(self) -> str:
        """获取带元素索引的 DOM 序列化文本

        通过执行器执行 JavaScript 获取 DOM 结构，并为可交互元素
        添加索引标记，便于 LLM 定位和引用。

        Returns:
            带索引的 DOM 序列化文本
        """
        js_script = """
        (() => {
            function serialize(el, depth = 0, index = { value: 0 }) {
                if (depth > 12) return '';
                const tag = el.tagName?.toLowerCase();
                if (!tag) return '';
                // 跳过不可见元素
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return '';
                if (tag === 'script' || tag === 'style' || tag === 'meta' || tag === 'link') return '';

                const indent = '  '.repeat(depth);
                const attrs = [];
                const interactive = el.getAttribute('role') ||
                    ['a','button','input','select','textarea','details','summary'].includes(tag);

                if (interactive) {
                    const idx = index.value++;
                    attrs.push(`data-uid="${idx}"`);
                }

                // 收集关键属性
                for (const name of ['id', 'class', 'href', 'type', 'placeholder', 'aria-label', 'role', 'name', 'value', 'alt', 'title']) {
                    const val = el.getAttribute(name);
                    if (val) attrs.push(`${name}="${val.substring(0, 80)}"`);
                }

                const attrStr = attrs.length ? ' ' + attrs.join(' ') : '';
                const text = (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3)
                    ? el.childNodes[0].textContent.trim().substring(0, 120)
                    : '';
                const textPart = text ? ` "${text}"` : '';
                const selfClose = ['br','hr','img','input'].includes(tag);
                let result = `${indent}<${tag}${attrStr}${textPart}${selfClose ? ' /' : ''}>\\n`;

                if (!selfClose) {
                    for (const child of el.children) {
                        result += serialize(child, depth + 1, index);
                    }
                }
                return result;
            }
            return serialize(document.documentElement);
        })()
        """
        try:
            result = await self._executor.evaluate(js_script)
            return str(result) if result else ""
        except Exception:
            logger.exception("获取 DOM 序列化失败")
            return ""

    async def get_screenshot(self) -> bytes:
        """获取页面截图

        Returns:
            截图的二进制数据（PNG 格式）
        """
        try:
            return await self._executor.screenshot()
        except Exception:
            logger.exception("获取截图失败")
            return b""

    async def get_hybrid(self) -> PerceptionResult:
        """混合模式感知

        策略：
            1. 优先采集 A11y Snapshot
            2. 若 A11y Snapshot 为空或页面为 Canvas/WebGL 等无 DOM 场景，回退到截图
            3. 始终包含 URL 和标题
            4. 预估 token 数量

        Returns:
            混合模式感知结果
        """
        url = await self._safe_get_url()
        title = await self._safe_get_title()

        # 第一步：尝试 A11y Snapshot
        a11y_text = await self.get_a11y_snapshot()

        # 判断是否需要截图补充
        need_screenshot = self._should_fallback_to_screenshot(a11y_text)

        screenshot_data: Optional[bytes] = None
        if need_screenshot:
            logger.info("A11y Snapshot 不可用或页面无 DOM，回退到截图模式")
            screenshot_data = await self.get_screenshot()

        result = PerceptionResult(
            mode=PerceptionMode.HYBRID,
            a11y_snapshot=a11y_text or None,
            screenshot=screenshot_data,
            url=url,
            title=title,
            timestamp=datetime.now(),
        )
        result.token_estimate = self.estimate_tokens(result)
        return result

    def estimate_tokens(self, result: PerceptionResult) -> int:
        """估算感知结果的 token 数量

        文本部分按字符级估算，截图部分按固定值估算
        （截图在多模态模型中通常占用约 1000-2000 token）。

        Args:
            result: 感知结果

        Returns:
            预估 token 数量
        """
        total = 0

        # URL 和标题
        total += _estimate_text_tokens(result.url)
        total += _estimate_text_tokens(result.title)

        # A11y Snapshot
        if result.a11y_snapshot:
            total += _estimate_text_tokens(result.a11y_snapshot)

        # DOM 树
        if result.dom_tree:
            total += _estimate_text_tokens(result.dom_tree)

        # 截图：多模态模型中一张截图约 1500 token
        if result.screenshot:
            total += 1500

        return total

    def format_for_llm(self, result: PerceptionResult, max_tokens: int = 4000) -> str:
        """将感知结果格式化为 LLM 输入文本

        按照优先级组织内容：URL/标题 → A11y Snapshot → DOM → 截图描述，
        超出 token 预算时从低优先级内容开始截断。

        Args:
            result: 感知结果
            max_tokens: 最大 token 预算

        Returns:
            格式化后的文本
        """
        sections: list[str] = []

        # 元信息（最高优先级，不截断）
        meta_lines: list[str] = []
        if result.url:
            meta_lines.append(f"URL: {result.url}")
        if result.title:
            meta_lines.append(f"Title: {result.title}")
        meta_lines.append(f"Mode: {result.mode.value}")
        meta_lines.append(f"Timestamp: {result.timestamp.isoformat()}")
        meta_text = "\n".join(meta_lines)
        meta_tokens = _estimate_text_tokens(meta_text)

        remaining = max_tokens - meta_tokens
        if remaining <= 0:
            return meta_text

        # A11y Snapshot（高优先级）
        a11y_text = ""
        a11y_tokens = 0
        if result.a11y_snapshot:
            a11y_text = f"\n\n--- Accessibility Snapshot ---\n{result.a11y_snapshot}"
            a11y_tokens = _estimate_text_tokens(a11y_text)

        # DOM 树（中优先级）
        dom_text = ""
        dom_tokens = 0
        if result.dom_tree:
            dom_text = f"\n\n--- DOM Tree ---\n{result.dom_tree}"
            dom_tokens = _estimate_text_tokens(dom_text)

        # 截图提示（低优先级）
        screenshot_text = ""
        screenshot_tokens = 0
        if result.screenshot:
            screenshot_text = "\n\n--- Screenshot ---\n[页面截图已采集，请在多模态对话中引用]"
            screenshot_tokens = _estimate_text_tokens(screenshot_text) + 1500

        # 按优先级分配 token 预算
        total_content_tokens = a11y_tokens + dom_tokens + screenshot_tokens

        if total_content_tokens <= remaining:
            # 预算充足，全部保留
            sections.append(meta_text)
            sections.append(a11y_text)
            sections.append(dom_text)
            sections.append(screenshot_text)
        else:
            # 预算不足，按优先级截断
            sections.append(meta_text)

            # 先分配给 A11y Snapshot
            a11y_budget = min(a11y_tokens, remaining)
            if a11y_budget > 0 and result.a11y_snapshot:
                truncated = _truncate_text(result.a11y_snapshot, a11y_budget)
                sections.append(f"\n\n--- Accessibility Snapshot ---\n{truncated}")
                remaining -= _estimate_text_tokens(truncated)

            # 再分配给 DOM
            if remaining > 0 and result.dom_tree:
                dom_budget = min(dom_tokens, remaining)
                truncated = _truncate_text(result.dom_tree, dom_budget)
                sections.append(f"\n\n--- DOM Tree ---\n{truncated}")
                remaining -= _estimate_text_tokens(truncated)

            # 最后分配给截图提示
            if remaining > 0 and result.screenshot:
                sections.append(screenshot_text)

        return "".join(sections)

    # ---- 内部方法 ----

    def _serialize_a11y_tree(self, tree: dict, depth: int = 0) -> str:
        """将辅助功能树字典序列化为缩进文本

        Args:
            tree: 辅助功能树字典
            depth: 当前缩进深度

        Returns:
            缩进格式的文本
        """
        if not tree or not isinstance(tree, dict):
            return ""

        lines: list[str] = []
        indent = "  " * depth

        role = tree.get("role", "")
        name = tree.get("name", "")
        node_id = tree.get("nodeId", "")

        # 构建节点行
        parts: list[str] = []
        if role:
            parts.append(f"role={role}")
        if name:
            parts.append(f'name="{name}"')
        if node_id:
            parts.append(f"id={node_id}")

        # 附加关键属性
        for key in ("value", "description", "checked", "disabled", "expanded", "level"):
            val = tree.get(key)
            if val is not None and val != "":
                parts.append(f"{key}={val}")

        if parts:
            lines.append(f"{indent}[{' '.join(parts)}]")

        # 递归处理子节点
        children = tree.get("children", [])
        if isinstance(children, list):
            for child in children:
                child_text = self._serialize_a11y_tree(child, depth + 1)
                if child_text:
                    lines.append(child_text)

        return "\n".join(lines)

    def _should_fallback_to_screenshot(self, a11y_text: str) -> bool:
        """判断是否需要回退到截图模式

        以下情况需要回退：
            1. A11y Snapshot 为空
            2. A11y Snapshot 中检测到 Canvas/WebGL 等无 DOM 内容标记

        Args:
            a11y_text: A11y Snapshot 文本

        Returns:
            是否需要回退到截图
        """
        if not a11y_text or not a11y_text.strip():
            return True

        # 检测 Canvas/WebGL 场景：A11y 树中只有极少数节点
        # 或包含 canvas 角色且几乎没有其他交互元素
        stripped = a11y_text.strip()
        line_count = stripped.count("\n") + 1

        # 如果 A11y 树行数极少（少于 3 行），说明页面可能没有常规 DOM
        if line_count < 3:
            return True

        # 检测 canvas 关键词
        canvas_indicators = re.search(
            r"role=(canvas|img).*canvas|webgl|<canvas", stripped, re.IGNORECASE
        )
        if canvas_indicators:
            # 如果包含 canvas 但几乎没有交互元素，则回退
            interactive_count = len(
                re.findall(r"role=(button|link|textbox|combobox|checkbox|menuitem)", stripped)
            )
            if interactive_count < 2:
                return True

        return False

    async def _safe_get_url(self) -> str:
        """安全获取当前 URL"""
        try:
            return await self._executor.get_url()
        except Exception:
            logger.exception("获取 URL 失败")
            return ""

    async def _safe_get_title(self) -> str:
        """安全获取页面标题"""
        try:
            return await self._executor.get_title()
        except Exception:
            logger.exception("获取标题失败")
            return ""

    async def _perceive_a11y(self) -> PerceptionResult:
        """A11y Snapshot 模式感知"""
        url = await self._safe_get_url()
        title = await self._safe_get_title()
        a11y_text = await self.get_a11y_snapshot()

        result = PerceptionResult(
            mode=PerceptionMode.A11Y_SNAPSHOT,
            a11y_snapshot=a11y_text or None,
            url=url,
            title=title,
            timestamp=datetime.now(),
        )
        result.token_estimate = self.estimate_tokens(result)
        return result

    async def _perceive_dom(self) -> PerceptionResult:
        """DOM 序列化模式感知"""
        url = await self._safe_get_url()
        title = await self._safe_get_title()
        dom_text = await self.get_dom_serialized()

        result = PerceptionResult(
            mode=PerceptionMode.DOM_SERIALIZE,
            dom_tree=dom_text or None,
            url=url,
            title=title,
            timestamp=datetime.now(),
        )
        result.token_estimate = self.estimate_tokens(result)
        return result

    async def _perceive_screenshot(self) -> PerceptionResult:
        """截图模式感知"""
        url = await self._safe_get_url()
        title = await self._safe_get_title()
        screenshot_data = await self.get_screenshot()

        result = PerceptionResult(
            mode=PerceptionMode.VISUAL_SCREENSHOT,
            screenshot=screenshot_data or None,
            url=url,
            title=title,
            timestamp=datetime.now(),
        )
        result.token_estimate = self.estimate_tokens(result)
        return result
