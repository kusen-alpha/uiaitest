"""代码录制器 - 将Agent执行过程录制为可复现的Python代码

支持DOM模式（生成Playwright Python代码）和视觉模式（仅注释），
录制Agent执行过程中的导航、操作、断言、等待等行为，
生成可直接运行的异步测试脚本。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from uiai.core.locator import Locator, LocatorType

if TYPE_CHECKING:
    from uiai.core.result import StepResult

logger = logging.getLogger(__name__)


@dataclass
class CodeAction:
    """录制的代码动作"""
    action_type: str                          # 动作类型：click / type / fill / navigate / assert / wait / comment 等
    locator_code: str | None = None           # 定位器代码，如 page.get_by_role("button", name="Submit")
    action_code: str = ""                     # 动作代码，如 .click() / .fill("hello")
    comment: str = ""                         # 自然语言注释
    timestamp: datetime = field(default_factory=datetime.now)


class CodeRecorder:
    """代码录制器 - 将Agent执行过程录制为可复现的Python代码

    DOM模式下生成Playwright异步Python代码，视觉模式下仅生成注释。
    支持语义定位器优先（get_by_role / get_by_test_id / get_by_label 等），
    CSS/XPATH作为降级方案。

    用法::

        recorder = CodeRecorder()
        recorder.record_navigation("https://example.com")
        recorder.record_action("click", Locator.by_role("button", name="登录"), {}, result)
        recorder.record_assertion("visible", Locator.by_text("欢迎"), "欢迎")
        code = recorder.generate_code()
    """

    # 视觉模式定位器类型集合 - 这些类型无法生成可执行代码
    _VISUAL_LOCATOR_TYPES: frozenset[LocatorType] = frozenset({
        LocatorType.IMAGE,
        LocatorType.OCR,
        LocatorType.COORDINATE,
    })

    def __init__(self, target_language: str = "python") -> None:
        self._target_language = target_language
        self._actions: list[CodeAction] = []
        self._navigation_url: str | None = None

    # ------------------------------------------------------------------
    # 录制接口
    # ------------------------------------------------------------------

    def record_action(
        self,
        action_type: str,
        locator: Optional[Locator],
        params: dict,
        result: StepResult | None = None,
    ) -> None:
        """录制一个操作动作

        Args:
            action_type: 动作类型（click / type / fill / hover / check / uncheck / select 等）
            locator: 定位器，视觉模式定位器时生成注释
            params: 动作参数，如 {"text": "hello", "clear": True}
            result: 执行结果（可选，用于生成注释）
        """
        # 判断是否为视觉模式定位器
        is_visual = locator is not None and locator.primary_type in self._VISUAL_LOCATOR_TYPES

        if is_visual:
            self._actions.append(CodeAction(
                action_type=action_type,
                locator_code=None,
                action_code="",
                comment=f"[视觉模式] 无法录制代码: {action_type} {locator.description}",
            ))
            return

        locator_code = self._locator_to_code(locator) if locator else None
        action_code = self._build_action_code(action_type, locator_code, params)
        comment = self._build_action_comment(action_type, locator, params, result)

        self._actions.append(CodeAction(
            action_type=action_type,
            locator_code=locator_code,
            action_code=action_code,
            comment=comment,
        ))

    def record_navigation(self, url: str) -> None:
        """录制页面导航

        Args:
            url: 导航目标URL
        """
        self._navigation_url = url
        self._actions.append(CodeAction(
            action_type="navigate",
            locator_code=None,
            action_code=f'await page.goto("{url}")',
            comment=f"导航到 {url}",
        ))

    def record_assertion(
        self,
        assertion_type: str,
        locator: Optional[Locator],
        expected: str,
    ) -> None:
        """录制断言

        Args:
            assertion_type: 断言类型（visible / text_equals / text_contains 等）
            locator: 定位器（可选，URL断言等不需要）
            expected: 期望值
        """
        is_visual = locator is not None and locator.primary_type in self._VISUAL_LOCATOR_TYPES

        if is_visual:
            self._actions.append(CodeAction(
                action_type="assert",
                locator_code=None,
                action_code="",
                comment=f"[视觉模式] 无法录制断言代码: {assertion_type} {locator.description}",
            ))
            return

        locator_code = self._locator_to_code(locator) if locator else None
        action_code = self._build_assertion_code(assertion_type, locator_code, expected)
        comment = f"断言: {assertion_type}" + (f" - {locator.description}" if locator else "") + f" 期望: {expected}"

        self._actions.append(CodeAction(
            action_type="assert",
            locator_code=locator_code,
            action_code=action_code,
            comment=comment,
        ))

    def record_comment(self, comment: str) -> None:
        """添加注释行

        Args:
            comment: 注释内容
        """
        self._actions.append(CodeAction(
            action_type="comment",
            locator_code=None,
            action_code="",
            comment=comment,
        ))

    def record_wait(self, condition: str, timeout: int = 5000) -> None:
        """录制等待操作

        Args:
            condition: 等待条件描述
            timeout: 超时时间（毫秒）
        """
        self._actions.append(CodeAction(
            action_type="wait",
            locator_code=None,
            action_code=f"await page.wait_for_load_state(\"networkidle\", timeout={timeout})",
            comment=f"等待: {condition} (超时 {timeout}ms)",
        ))

    # ------------------------------------------------------------------
    # 代码生成
    # ------------------------------------------------------------------

    def generate_code(self, include_imports: bool = True, class_name: str = "RecordedTest") -> str:
        """生成完整的测试文件代码

        Args:
            include_imports: 是否包含import语句
            class_name: 生成的测试类名

        Returns:
            完整的Python测试代码字符串
        """
        lines: list[str] = []

        if include_imports:
            lines.append(self._generate_imports())
            lines.append("")

        lines.append(f"async def {class_name.lower()}():")
        lines.append('    """自动录制的测试脚本"""')
        lines.append("    async with async_playwright() as p:")
        lines.append("        browser = await p.chromium.launch()")
        lines.append('        page = await browser.new_page()')
        lines.append("")

        # 生成步骤代码
        step_lines = self.generate_step_code()
        for line in step_lines:
            lines.append(line)

        lines.append("")
        lines.append("        await browser.close()")
        lines.append("")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append(f"    import asyncio")
        lines.append(f"    asyncio.run({class_name.lower()}())")
        lines.append("")

        return "\n".join(lines)

    def generate_step_code(self) -> list[str]:
        """生成每个步骤的代码行

        Returns:
            代码行列表，每行已包含8空格缩进（在async with块内）
        """
        lines: list[str] = []

        for action in self._actions:
            # 添加注释
            if action.comment:
                lines.append(f"        # {action.comment}")

            # 添加代码
            if action.action_code:
                lines.append(f"        {action.action_code}")
            elif action.action_type == "comment":
                pass  # 注释已添加
            elif not action.action_code and action.action_type != "comment":
                # 无代码的动作（如视觉模式），注释已说明
                pass

            lines.append("")  # 步骤间空行

        return lines

    # ------------------------------------------------------------------
    # 定位器转换
    # ------------------------------------------------------------------

    def _locator_to_code(self, locator: Optional[Locator]) -> str:
        """将Locator转换为Playwright代码字符串

        优先使用语义定位器，CSS/XPATH作为降级方案。

        Args:
            locator: 定位器对象

        Returns:
            Playwright定位器代码，如 page.get_by_role("button", name="Submit")
        """
        if locator is None:
            return ""

        loc_type = locator.primary_type
        loc_value = locator.primary_value
        options = locator.options

        if loc_type == LocatorType.ROLE:
            role = options.get("role", loc_value)
            name = options.get("name")
            if name:
                return f'page.get_by_role("{role}", name="{name}")'
            return f'page.get_by_role("{role}")'

        if loc_type == LocatorType.TEST_ID:
            return f'page.get_by_test_id("{loc_value}")'

        if loc_type == LocatorType.LABEL:
            return f'page.get_by_label("{loc_value}")'

        if loc_type == LocatorType.PLACEHOLDER:
            return f'page.get_by_placeholder("{loc_value}")'

        if loc_type == LocatorType.TEXT:
            exact = options.get("exact", False)
            if exact:
                return f'page.get_by_text("{loc_value}", exact=True)'
            return f'page.get_by_text("{loc_value}")'

        if loc_type == LocatorType.ALT_TEXT:
            return f'page.get_by_alt_text("{loc_value}")'

        if loc_type == LocatorType.TITLE:
            return f'page.get_by_title("{loc_value}")'

        if loc_type == LocatorType.CSS:
            return f'page.locator("{loc_value}")'

        if loc_type == LocatorType.XPATH:
            return f'page.locator("xpath={loc_value}")'

        if loc_type == LocatorType.ACCESSIBILITY_ID:
            # App端定位器，Web端降级为CSS属性选择器
            return f'page.locator("[aria-label=\\"{loc_value}\\"]")'

        # 视觉模式定位器 - 无法生成可执行代码
        if loc_type in self._VISUAL_LOCATOR_TYPES:
            return ""

        # 未知类型降级
        return f'page.locator("{loc_value}")'

    # ------------------------------------------------------------------
    # 动作代码生成
    # ------------------------------------------------------------------

    def _action_to_code(self, action: CodeAction) -> str:
        """将CodeAction转换为代码行

        Args:
            action: 代码动作

        Returns:
            代码行字符串
        """
        return action.action_code

    def _build_action_code(
        self,
        action_type: str,
        locator_code: str | None,
        params: dict,
    ) -> str:
        """构建动作代码

        Args:
            action_type: 动作类型
            locator_code: 定位器代码
            params: 动作参数

        Returns:
            完整的动作代码行
        """
        if not locator_code:
            return ""

        action_map: dict[str, str] = {
            "click": "click()",
            "hover": "hover()",
            "check": "check()",
            "uncheck": "uncheck()",
        }

        if action_type in action_map:
            return f"await {locator_code}.{action_map[action_type]}"

        if action_type in ("type", "type_text"):
            text = params.get("text", "")
            clear = params.get("clear", True)
            if clear:
                return f'await {locator_code}.fill("{text}")'
            return f'await {locator_code}.type("{text}")'

        if action_type == "fill":
            value = params.get("value", params.get("text", ""))
            return f'await {locator_code}.fill("{value}")'

        if action_type == "select":
            value = params.get("value", "")
            return f'await {locator_code}.select_option("{value}")'

        if action_type == "press":
            key = params.get("key", "")
            return f'await {locator_code}.press("{key}")'

        if action_type == "scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 300)
            if direction == "up":
                return f"await page.mouse.wheel(0, -{amount})"
            return f"await page.mouse.wheel(0, {amount})"

        # 未知动作类型，生成注释
        return f"# 未知动作: {action_type}({params})"

    def _build_assertion_code(
        self,
        assertion_type: str,
        locator_code: str | None,
        expected: str,
    ) -> str:
        """构建断言代码

        Args:
            assertion_type: 断言类型
            locator_code: 定位器代码
            expected: 期望值

        Returns:
            断言代码行
        """
        if assertion_type == "visible" and locator_code:
            return f"assert await {locator_code}.is_visible()"

        if assertion_type == "hidden" and locator_code:
            return f"assert await {locator_code}.is_hidden()"

        if assertion_type == "text_equals" and locator_code:
            return f'assert await {locator_code}.text_content() == "{expected}"'

        if assertion_type == "text_contains" and locator_code:
            return f'assert "{expected}" in await {locator_code}.text_content()'

        if assertion_type == "has_text" and locator_code:
            return f'assert await {locator_code}.text_content() is not None'

        if assertion_type == "is_enabled" and locator_code:
            return f"assert await {locator_code}.is_enabled()"

        if assertion_type == "is_checked" and locator_code:
            return f"assert await {locator_code}.is_checked()"

        if assertion_type == "url_equals":
            return f'assert page.url == "{expected}"'

        if assertion_type == "url_contains":
            return f'assert "{expected}" in page.url'

        if assertion_type == "title_equals":
            return f'assert await page.title() == "{expected}"'

        if assertion_type == "title_contains":
            return f'assert "{expected}" in await page.title()'

        # 通用断言降级
        if locator_code:
            return f"# 断言: {assertion_type}, 期望: {expected}"

        return f"# 断言: {assertion_type} 期望: {expected}"

    def _build_action_comment(
        self,
        action_type: str,
        locator: Optional[Locator],
        params: dict,
        result: StepResult | None,
    ) -> str:
        """构建动作注释

        Args:
            action_type: 动作类型
            locator: 定位器
            params: 动作参数
            result: 执行结果

        Returns:
            注释字符串
        """
        action_labels: dict[str, str] = {
            "click": "点击",
            "type": "输入",
            "type_text": "输入",
            "fill": "填充",
            "hover": "悬停",
            "check": "勾选",
            "uncheck": "取消勾选",
            "select": "选择",
            "press": "按键",
            "scroll": "滚动",
        }
        label = action_labels.get(action_type, action_type)
        desc = f" {locator.description}" if locator and locator.description else ""
        text = params.get("text", params.get("value", ""))
        text_info = f' "{text}"' if text else ""

        comment = f"{label}{desc}{text_info}"

        if result and result.healing_applied:
            comment += f" [自愈: {result.healing_applied}]"

        return comment

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_imports() -> str:
        """生成import语句"""
        return (
            "from playwright.async_api import async_playwright\n"
            "import asyncio"
        )

    @property
    def actions(self) -> list[CodeAction]:
        """获取所有录制的动作"""
        return self._actions.copy()

    def clear(self) -> None:
        """清空录制的动作"""
        self._actions.clear()
        self._navigation_url = None

    def save_to_file(self, filepath: str) -> None:
        """将生成的代码保存到文件

        Args:
            filepath: 目标文件路径
        """
        code = self.generate_code()
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")
        logger.info(f"录制代码已保存到: {filepath}")
