"""定位器抽象 - 支持多策略降级定位"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

class LocatorType(Enum):
    """定位器类型，按优先级排序"""
    ROLE = "role"           # getByRole - 最高优先级
    TEST_ID = "test_id"     # getByTestId
    LABEL = "label"         # getByLabel
    PLACEHOLDER = "placeholder"
    TEXT = "text"           # getByText
    ALT_TEXT = "alt_text"
    TITLE = "title"
    CSS = "css"             # CSS选择器
    XPATH = "xpath"         # XPath - 较低优先级
    ACCESSIBILITY_ID = "accessibility_id"  # App端
    IMAGE = "image"         # 图像识别定位
    OCR = "ocr"             # OCR文字定位
    COORDINATE = "coordinate"  # 坐标定位 - 最低优先级

@dataclass
class Locator:
    """定位器 - 支持多策略降级链"""
    primary_type: LocatorType
    primary_value: str
    fallback_chain: list[tuple[LocatorType, str]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def by_role(cls, role: str, name: str | None = None, **options) -> Locator:
        """通过角色定位"""
        opts = {"role": role, **options}
        if name:
            opts["name"] = name
        return cls(
            primary_type=LocatorType.ROLE,
            primary_value=role,
            options=opts,
            description=f"role={role}" + (f", name={name}" if name else "")
        )

    @classmethod
    def by_test_id(cls, test_id: str) -> Locator:
        return cls(
            primary_type=LocatorType.TEST_ID,
            primary_value=test_id,
            description=f"testId={test_id}"
        )

    @classmethod
    def by_label(cls, label: str) -> Locator:
        return cls(
            primary_type=LocatorType.LABEL,
            primary_value=label,
            description=f"label={label}"
        )

    @classmethod
    def by_placeholder(cls, placeholder: str) -> Locator:
        return cls(
            primary_type=LocatorType.PLACEHOLDER,
            primary_value=placeholder,
            description=f"placeholder={placeholder}"
        )

    @classmethod
    def by_text(cls, text: str, exact: bool = False) -> Locator:
        return cls(
            primary_type=LocatorType.TEXT,
            primary_value=text,
            options={"exact": exact},
            description=f"text={text}"
        )

    @classmethod
    def by_css(cls, selector: str) -> Locator:
        return cls(
            primary_type=LocatorType.CSS,
            primary_value=selector,
            description=f"css={selector}"
        )

    @classmethod
    def by_xpath(cls, xpath: str) -> Locator:
        return cls(
            primary_type=LocatorType.XPATH,
            primary_value=xpath,
            description=f"xpath={xpath}"
        )

    @classmethod
    def by_accessibility_id(cls, aid: str) -> Locator:
        return cls(
            primary_type=LocatorType.ACCESSIBILITY_ID,
            primary_value=aid,
            description=f"accessibility_id={aid}"
        )

    @classmethod
    def by_image(cls, image_path: str, threshold: float = 0.9) -> Locator:
        return cls(
            primary_type=LocatorType.IMAGE,
            primary_value=image_path,
            options={"threshold": threshold},
            description=f"image={image_path}"
        )

    @classmethod
    def by_ocr(cls, text: str, region: tuple | None = None) -> Locator:
        return cls(
            primary_type=LocatorType.OCR,
            primary_value=text,
            options={"region": region},
            description=f"ocr={text}"
        )

    @classmethod
    def by_coordinate(cls, x: float, y: float) -> Locator:
        return cls(
            primary_type=LocatorType.COORDINATE,
            primary_value=f"{x},{y}",
            options={"x": x, "y": y},
            description=f"coordinate=({x},{y})"
        )

    def with_fallback(self, locator_type: LocatorType, value: str, **options) -> Locator:
        """添加降级定位策略"""
        self.fallback_chain.append((locator_type, value))
        return self

    def build_chain(self) -> list[tuple[LocatorType, str, dict]]:
        """构建完整的降级链"""
        chain = [(self.primary_type, self.primary_value, self.options)]
        for lt, val in self.fallback_chain:
            chain.append((lt, val, {}))
        return chain
