"""辅助功能树快照 - 解析和格式化accessibility tree"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AccessibilitySnapshot:
    """辅助功能树快照

    参考Playwright MCP的browser_snapshot实现，
    将accessibility tree转为LLM友好的结构化文本。
    """

    def __init__(self, raw_snapshot: dict):
        self.raw = raw_snapshot

    def to_text(self, max_depth: int = 10) -> str:
        """转为YAML风格的结构化文本（参考Playwright MCP格式）"""
        lines = []
        self._format_node(self.raw, lines, depth=0, max_depth=max_depth)
        return "\n".join(lines)

    def _format_node(self, node: dict, lines: list, depth: int, max_depth: int) -> None:
        if depth > max_depth or not node:
            return

        role = node.get("role", "")
        name = node.get("name", "")
        children = node.get("children", [])

        # 构建行
        indent = " " * (depth * 2)
        parts = [f"{indent}- {role}"]

        if name:
            parts.append(f' "{name}"')

        # 添加属性
        attrs = []
        if node.get("value"):
            attrs.append(f'value="{node["value"]}"')
        if node.get("checked") is not None:
            attrs.append(f'checked={node["checked"]}')
        if node.get("disabled"):
            attrs.append("disabled")
        if node.get("required"):
            attrs.append("required")
        if node.get("level"):
            attrs.append(f'level={node["level"]}')

        if attrs:
            parts.append(f' [{", ".join(attrs)}]')

        lines.append("".join(parts))

        # 递归处理子节点
        for child in children:
            self._format_node(child, lines, depth + 1, max_depth)

    def find_interactive_elements(self) -> list[dict]:
        """查找所有可交互元素"""
        interactive_roles = {
            "button", "link", "textbox", "checkbox", "radio",
            "combobox", "menuitem", "tab", "switch", "searchbox",
        }
        elements = []
        self._find_by_roles(self.raw, interactive_roles, elements)
        return elements

    def _find_by_roles(self, node: dict, roles: set, result: list) -> None:
        if not node:
            return
        if node.get("role") in roles:
            result.append(node)
        for child in node.get("children", []):
            self._find_by_roles(child, roles, result)

    def find_by_text(self, text: str) -> list[dict]:
        """按文本查找元素"""
        results = []
        self._search_by_text(self.raw, text, results)
        return results

    def _search_by_text(self, node: dict, text: str, results: list) -> None:
        if not node:
            return
        if text.lower() in (node.get("name") or "").lower():
            results.append(node)
        for child in node.get("children", []):
            self._search_by_text(child, text, results)

    @property
    def token_estimate(self) -> int:
        """估算快照的token数（约4字符=1token）"""
        text = self.to_text()
        return len(text) // 4
