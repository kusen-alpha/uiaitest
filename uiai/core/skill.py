"""技能注册表与输入原语定义

参考 playwright-cli 的 SKILL 机制与 Midscene.js 的 InputPrimitives 设计，
提供跨平台的输入原语枚举、技能数据模型与技能注册表。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from uiai.core.platform import Platform


class InputPrimitive(Enum):
    """跨平台输入原语

    定义 UI 自动化中所有基本输入操作类型，
    作为技能（Skill）的构建块。
    """
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    HOVER = "hover"
    TYPE = "type"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "unchecked"
    PRESS_KEY = "press_key"
    SCROLL = "scroll"
    DRAG = "drag"
    UPLOAD = "upload"
    SCREENSHOT = "screenshot"
    WAIT = "wait"


@dataclass
class Skill:
    """技能数据模型

    一个技能代表一组有序的输入原语组合，
    用于完成特定的用户操作目标（如登录、搜索、加购）。
    """
    name: str
    description: str
    primitives: list[InputPrimitive]
    steps: list[dict]
    platform: Optional[Platform] = None
    metadata: dict = field(default_factory=dict)


class SkillRegistry:
    """技能注册表

    管理技能的注册、查询与检索，支持按名称、描述、平台等维度搜索。
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """注册一个技能

        Args:
            skill: 要注册的技能实例

        Raises:
            ValueError: 当同名技能已存在时
        """
        if skill.name in self._skills:
            raise ValueError(f"技能 '{skill.name}' 已存在，请先卸载或使用其他名称")
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        """卸载指定名称的技能

        Args:
            name: 技能名称

        Raises:
            KeyError: 当技能不存在时
        """
        if name not in self._skills:
            raise KeyError(f"技能 '{name}' 不存在")
        del self._skills[name]

    def get(self, name: str) -> Optional[Skill]:
        """按名称获取技能

        Args:
            name: 技能名称

        Returns:
            技能实例，不存在时返回 None
        """
        return self._skills.get(name)

    def search(self, query: str) -> list[Skill]:
        """按名称或描述搜索技能

        搜索不区分大小写，匹配技能名称或描述中包含查询关键词的技能。

        Args:
            query: 搜索关键词

        Returns:
            匹配的技能列表
        """
        query_lower = query.lower()
        return [
            skill for skill in self._skills.values()
            if query_lower in skill.name.lower()
            or query_lower in skill.description.lower()
        ]

    def list_skills(self, platform: Optional[Platform] = None) -> list[Skill]:
        """列出所有技能

        Args:
            platform: 可选的平台过滤条件，为 None 时列出全部技能

        Returns:
            技能列表
        """
        if platform is None:
            return list(self._skills.values())
        return [
            skill for skill in self._skills.values()
            if skill.platform is None or skill.platform == platform
        ]

    def get_skills_for_task(self, task_description: str) -> list[Skill]:
        """根据任务描述获取相关技能

        通过关键词匹配从已注册技能中筛选与任务描述相关的技能，
        按匹配度降序排列。

        Args:
            task_description: 任务描述文本

        Returns:
            相关技能列表，按匹配度降序排列
        """
        task_lower = task_description.lower()
        scored: list[tuple[int, Skill]] = []
        for skill in self._skills.values():
            score = 0
            name_lower = skill.name.lower()
            desc_lower = skill.description.lower()
            # 名称完全匹配
            if name_lower == task_lower:
                score += 100
            # 名称包含关键词
            elif name_lower in task_lower or task_lower in name_lower:
                score += 50
            # 描述包含关键词
            if task_lower in desc_lower:
                score += 30
            # 逐词匹配
            task_words = task_lower.split()
            for word in task_words:
                if word in name_lower:
                    score += 10
                if word in desc_lower:
                    score += 5
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in scored]

    def register_defaults(self) -> None:
        """注册默认技能集

        包含 UI 自动化中最常用的基础技能：
        navigate, click_element, type_text, fill_form, select_option,
        assert_visible, assert_text, take_screenshot, wait_for_element, scroll_page
        """
        defaults: list[Skill] = [
            Skill(
                name="navigate",
                description="导航到指定URL",
                primitives=[InputPrimitive.CLICK],
                steps=[{"action_type": "navigate", "params": {"url": ""}}],
            ),
            Skill(
                name="click_element",
                description="点击页面元素",
                primitives=[InputPrimitive.CLICK],
                steps=[{"action_type": "click", "params": {"selector": ""}}],
            ),
            Skill(
                name="type_text",
                description="在输入框中逐字输入文本",
                primitives=[InputPrimitive.TYPE],
                steps=[{"action_type": "type", "params": {"selector": "", "text": ""}}],
            ),
            Skill(
                name="fill_form",
                description="使用数据字典填充表单",
                primitives=[InputPrimitive.FILL, InputPrimitive.CLICK],
                steps=[{"action_type": "fill", "params": {"selector": "", "value": ""}}],
            ),
            Skill(
                name="select_option",
                description="从下拉框中选择选项",
                primitives=[InputPrimitive.SELECT],
                steps=[{"action_type": "select", "params": {"selector": "", "value": ""}}],
            ),
            Skill(
                name="assert_visible",
                description="断言元素可见",
                primitives=[InputPrimitive.SCREENSHOT],
                steps=[{"action_type": "assert_visible", "params": {"selector": ""}}],
            ),
            Skill(
                name="assert_text",
                description="断言元素文本内容",
                primitives=[InputPrimitive.SCREENSHOT],
                steps=[{"action_type": "assert_text", "params": {"selector": "", "expected": ""}}],
            ),
            Skill(
                name="take_screenshot",
                description="截取页面截图",
                primitives=[InputPrimitive.SCREENSHOT],
                steps=[{"action_type": "screenshot", "params": {"path": ""}}],
            ),
            Skill(
                name="wait_for_element",
                description="等待元素出现",
                primitives=[InputPrimitive.WAIT],
                steps=[{"action_type": "wait", "params": {"selector": "", "state": "visible"}}],
            ),
            Skill(
                name="scroll_page",
                description="滚动页面",
                primitives=[InputPrimitive.SCROLL],
                steps=[{"action_type": "scroll", "params": {"direction": "down", "amount": 300}}],
            ),
        ]
        for skill in defaults:
            if skill.name not in self._skills:
                self._skills[skill.name] = skill
