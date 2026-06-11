"""断言引擎 - 多层级断言体系 + 软断言 + 等待断言 + 自定义匹配器"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from uiai.core.locator import Locator
from uiai.executor.base import BaseExecutor

logger = logging.getLogger(__name__)


class AssertionType(Enum):
    """断言类型"""
    VISIBLE = "visible"
    HIDDEN = "hidden"
    TEXT_EQUALS = "text_equals"
    TEXT_CONTAINS = "text_contains"
    TEXT_MATCHES = "text_matches"
    TEXT_NOT_EQUALS = "text_not_equals"
    ATTRIBUTE_EQUALS = "attribute_equals"
    URL_EQUALS = "url_equals"
    URL_CONTAINS = "url_contains"
    URL_MATCHES = "url_matches"
    TITLE_EQUALS = "title_equals"
    TITLE_CONTAINS = "title_contains"
    SCREENSHOT_MATCH = "screenshot_match"
    LAYOUT_STABLE = "layout_stable"
    SEMANTIC_MATCH = "semantic_match"
    ELEMENT_COUNT = "element_count"
    HAS_TEXT = "has_text"
    NOT_HAS_TEXT = "not_has_text"
    IS_ENABLED = "is_enabled"
    IS_EDITABLE = "is_editable"
    IS_CHECKED = "is_checked"
    VALUE_EQUALS = "value_equals"
    NO_CONSOLE_ERRORS = "no_console_errors"
    CUSTOM = "custom"


@dataclass
class AssertionResult:
    """断言结果"""
    assertion_type: AssertionType
    passed: bool
    message: str = ""
    expected: Any = None
    actual: Any = None
    screenshot_path: str | None = None
    duration_ms: float = 0.0


class SoftAssertionCollector:
    """软断言收集器

    不立即抛出异常，收集所有断言结果，最后统一检查。

    用法:
        soft = SoftAssertionCollector()
        soft.collect(await engine.assert_visible(locator1))
        soft.collect(await engine.assert_text_equals(locator2, "hello"))
        soft.assert_all()  # 如果有失败的断言，此处抛出异常
    """

    def __init__(self):
        self._results: list[AssertionResult] = []

    def collect(self, result: AssertionResult) -> None:
        """收集断言结果"""
        self._results.append(result)

    def assert_all(self) -> None:
        """检查所有断言，如果有失败的则抛出异常"""
        failures = [r for r in self._results if not r.passed]
        if failures:
            messages = [f"  - {r.message}" for r in failures]
            raise AssertionError(
                f"{len(failures)} assertion(s) failed:\n" + "\n".join(messages)
            )

    @property
    def results(self) -> list[AssertionResult]:
        return self._results.copy()

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self._results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self._results if not r.passed)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self._results)


class AssertionEngine:
    """断言引擎

    支持四层断言：
    - 结构断言：DOM元素存在性、文本内容、属性值
    - 视觉断言：截图比对、布局稳定性
    - 语义断言：AI理解页面语义，自然语言描述验证
    - 自定义断言：用户自定义匹配器
    """

    def __init__(self, executor: BaseExecutor, vl_model=None):
        self.executor = executor
        self.vl_model = vl_model
        self._custom_matchers: dict[str, Callable] = {}

    def register_matcher(self, name: str, matcher: Callable) -> None:
        """注册自定义匹配器"""
        self._custom_matchers[name] = matcher

    # --- 结构断言 ---

    async def assert_visible(self, locator: Locator, message: str = "") -> AssertionResult:
        """断言元素可见"""
        try:
            visible = await self.executor.is_visible(locator)
            return AssertionResult(
                assertion_type=AssertionType.VISIBLE,
                passed=visible,
                message=message or f"Element should be visible: {locator.description}",
                expected="visible",
                actual="visible" if visible else "hidden",
            )
        except Exception as e:
            return AssertionResult(
                assertion_type=AssertionType.VISIBLE,
                passed=False,
                message=f"Assertion failed with error: {e}",
                expected="visible",
                actual=str(e),
            )

    async def assert_hidden(self, locator: Locator, message: str = "") -> AssertionResult:
        """断言元素隐藏"""
        try:
            visible = await self.executor.is_visible(locator)
            return AssertionResult(
                assertion_type=AssertionType.HIDDEN,
                passed=not visible,
                message=message or f"Element should be hidden: {locator.description}",
                expected="hidden",
                actual="hidden" if not visible else "visible",
            )
        except Exception:
            return AssertionResult(
                assertion_type=AssertionType.HIDDEN,
                passed=True,
                message=message or f"Element is hidden (not found): {locator.description}",
            )

    async def assert_text_equals(self, locator: Locator, expected: str, message: str = "") -> AssertionResult:
        """断言文本内容相等"""
        try:
            actual = await self.executor.get_text(locator)
            passed = actual == expected
            return AssertionResult(
                assertion_type=AssertionType.TEXT_EQUALS,
                passed=passed,
                message=message or f"Text should equal '{expected}', got '{actual}'",
                expected=expected,
                actual=actual,
            )
        except Exception as e:
            return AssertionResult(
                assertion_type=AssertionType.TEXT_EQUALS,
                passed=False,
                message=f"Assertion failed with error: {e}",
                expected=expected,
                actual=str(e),
            )

    async def assert_text_contains(self, locator: Locator, expected: str, message: str = "") -> AssertionResult:
        """断言文本包含"""
        try:
            actual = await self.executor.get_text(locator)
            passed = expected in actual
            return AssertionResult(
                assertion_type=AssertionType.TEXT_CONTAINS,
                passed=passed,
                message=message or f"Text should contain '{expected}'",
                expected=expected,
                actual=actual,
            )
        except Exception as e:
            return AssertionResult(
                assertion_type=AssertionType.TEXT_CONTAINS,
                passed=False,
                message=f"Assertion failed with error: {e}",
                expected=expected,
                actual=str(e),
            )

    async def assert_text_matches(self, locator: Locator, pattern: str, message: str = "") -> AssertionResult:
        """断言文本匹配正则"""
        import re
        try:
            actual = await self.executor.get_text(locator)
            passed = bool(re.search(pattern, actual))
            return AssertionResult(
                assertion_type=AssertionType.TEXT_MATCHES,
                passed=passed,
                message=message or f"Text should match pattern '{pattern}'",
                expected=pattern,
                actual=actual,
            )
        except Exception as e:
            return AssertionResult(
                assertion_type=AssertionType.TEXT_MATCHES,
                passed=False,
                message=f"Assertion failed with error: {e}",
                expected=pattern,
                actual=str(e),
            )

    async def assert_url_equals(self, expected: str, message: str = "") -> AssertionResult:
        """断言URL相等"""
        actual = await self.executor.get_url()
        passed = actual == expected
        return AssertionResult(
            assertion_type=AssertionType.URL_EQUALS,
            passed=passed,
            message=message or f"URL should be '{expected}', got '{actual}'",
            expected=expected,
            actual=actual,
        )

    async def assert_url_contains(self, expected: str, message: str = "") -> AssertionResult:
        """断言URL包含"""
        actual = await self.executor.get_url()
        passed = expected in actual
        return AssertionResult(
            assertion_type=AssertionType.URL_CONTAINS,
            passed=passed,
            message=message or f"URL should contain '{expected}'",
            expected=expected,
            actual=actual,
        )

    async def assert_title_contains(self, expected: str, message: str = "") -> AssertionResult:
        """断言标题包含"""
        actual = await self.executor.get_title()
        passed = expected in actual
        return AssertionResult(
            assertion_type=AssertionType.TITLE_CONTAINS,
            passed=passed,
            message=message or f"Title should contain '{expected}'",
            expected=expected,
            actual=actual,
        )

    # --- 等待断言 ---

    async def wait_and_assert_visible(self, locator: Locator, timeout: int = 10000,
                                       interval: int = 500, message: str = "") -> AssertionResult:
        """等待元素出现并断言可见"""
        import time
        start = time.time()
        while (time.time() - start) * 1000 < timeout:
            try:
                visible = await self.executor.is_visible(locator)
                if visible:
                    return AssertionResult(
                        assertion_type=AssertionType.VISIBLE,
                        passed=True,
                        message=message or f"Element became visible: {locator.description}",
                        expected="visible",
                        actual="visible",
                        duration_ms=(time.time() - start) * 1000,
                    )
            except Exception:
                pass
            await asyncio.sleep(interval / 1000)

        return AssertionResult(
            assertion_type=AssertionType.VISIBLE,
            passed=False,
            message=message or f"Element not visible within {timeout}ms: {locator.description}",
            expected="visible",
            actual="timeout",
            duration_ms=(time.time() - start) * 1000,
        )

    async def wait_and_assert_text(self, locator: Locator, expected: str, timeout: int = 10000,
                                    interval: int = 500, message: str = "") -> AssertionResult:
        """等待文本出现并断言"""
        import time
        start = time.time()
        while (time.time() - start) * 1000 < timeout:
            try:
                actual = await self.executor.get_text(locator)
                if actual == expected:
                    return AssertionResult(
                        assertion_type=AssertionType.TEXT_EQUALS,
                        passed=True,
                        message=message or f"Text matched: {expected}",
                        expected=expected,
                        actual=actual,
                        duration_ms=(time.time() - start) * 1000,
                    )
            except Exception:
                pass
            await asyncio.sleep(interval / 1000)

        try:
            actual = await self.executor.get_text(locator)
        except Exception as e:
            actual = str(e)

        return AssertionResult(
            assertion_type=AssertionType.TEXT_EQUALS,
            passed=False,
            message=message or f"Text did not match within {timeout}ms",
            expected=expected,
            actual=actual,
            duration_ms=(time.time() - start) * 1000,
        )

    # --- 视觉断言 ---

    async def assert_screenshot_match(self, name: str, threshold: float = 0.1, message: str = "") -> AssertionResult:
        """视觉断言：截图比对"""
        try:
            from uiai.visual.comparator import VisualComparator
            comparator = VisualComparator()
            screenshot = await self.executor.screenshot()
            result = await comparator.compare(screenshot, name, threshold)
            return AssertionResult(
                assertion_type=AssertionType.SCREENSHOT_MATCH,
                passed=result["match"],
                message=message or f"Screenshot should match baseline '{name}'",
                expected="baseline",
                actual=f"diff={result.get('diff_percentage', 0):.2%}",
                screenshot_path=result.get("diff_path"),
            )
        except ImportError:
            return AssertionResult(
                assertion_type=AssertionType.SCREENSHOT_MATCH,
                passed=False,
                message="Visual comparison not available (pillow not installed)",
            )
        except Exception as e:
            return AssertionResult(
                assertion_type=AssertionType.SCREENSHOT_MATCH,
                passed=False,
                message=f"Visual assertion failed: {e}",
            )

    # --- 语义断言 ---

    async def assert_semantic(self, description: str, message: str = "") -> AssertionResult:
        """语义断言：用自然语言描述预期页面状态，VL模型判断是否匹配"""
        if not self.vl_model:
            return AssertionResult(
                assertion_type=AssertionType.SEMANTIC_MATCH,
                passed=False,
                message="Semantic assertion requires VL model (not configured)",
                expected=description,
                actual="VL model not available",
            )
        try:
            screenshot = await self.executor.screenshot()
            result = await self.vl_model.verify(screenshot, description)
            return AssertionResult(
                assertion_type=AssertionType.SEMANTIC_MATCH,
                passed=result,
                message=message or f"Page should match: {description}",
                expected=description,
                actual="matched" if result else "not matched",
            )
        except Exception as e:
            return AssertionResult(
                assertion_type=AssertionType.SEMANTIC_MATCH,
                passed=False,
                message=f"Semantic assertion failed: {e}",
                expected=description,
                actual=str(e),
            )

    # --- 自定义断言 ---

    async def assert_custom(self, matcher_name: str, *args, **kwargs) -> AssertionResult:
        """使用自定义匹配器断言"""
        if matcher_name not in self._custom_matchers:
            return AssertionResult(
                assertion_type=AssertionType.CUSTOM,
                passed=False,
                message=f"Custom matcher not found: {matcher_name}",
            )
        try:
            matcher = self._custom_matchers[matcher_name]
            if asyncio.iscoroutinefunction(matcher):
                result = await matcher(self.executor, *args, **kwargs)
            else:
                result = matcher(self.executor, *args, **kwargs)
            if isinstance(result, AssertionResult):
                return result
            return AssertionResult(
                assertion_type=AssertionType.CUSTOM,
                passed=bool(result),
                message=f"Custom matcher '{matcher_name}': {result}",
            )
        except Exception as e:
            return AssertionResult(
                assertion_type=AssertionType.CUSTOM,
                passed=False,
                message=f"Custom matcher error: {e}",
            )

    async def assert_no_console_errors(self, message: str = "") -> AssertionResult:
        """断言无控制台错误"""
        messages = await self.executor.get_console_messages()
        # 兼容 list[str] 和 list[ConsoleMessageLog] 两种返回类型
        errors = []
        for m in messages:
            text = m if isinstance(m, str) else str(getattr(m, 'text', getattr(m, 'message', str(m))))
            if "error" in text.lower():
                errors.append(text)
        return AssertionResult(
            assertion_type=AssertionType.NO_CONSOLE_ERRORS,
            passed=len(errors) == 0,
            message=message or "No console errors expected",
            expected="no errors",
            actual=f"{len(errors)} errors" if errors else "no errors",
        )

    # --- 软断言 ---

    def create_soft_collector(self) -> SoftAssertionCollector:
        """创建软断言收集器"""
        return SoftAssertionCollector()
