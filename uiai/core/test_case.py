"""测试用例模型"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

class TestCaseType(Enum):
    """用例类型"""
    SCRIPT = "script"           # 确定性脚本
    NATURAL_LANGUAGE = "nl"     # 自然语言用例
    RECORDED = "recorded"       # 录制用例
    DATA_DRIVEN = "data_driven" # 数据驱动
    AI_GENERATED = "ai_generated"  # AI生成

class Priority(Enum):
    """优先级"""
    SMOKE = "smoke"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class TestStep:
    """测试步骤"""
    name: str
    action: str                    # 操作类型: click, type, navigate, assert, wait...
    locator: Any | None = None     # Locator 对象
    value: str | None = None       # 输入值/期望值
    options: dict[str, Any] = field(default_factory=dict)
    description: str = ""

@dataclass
class TestCase:
    """测试用例"""
    id: str
    name: str
    steps: list[TestStep] = field(default_factory=list)
    case_type: TestCaseType = TestCaseType.SCRIPT
    priority: Priority = Priority.MEDIUM
    platform: str = "web"
    tags: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    fixtures: dict[str, Any] = field(default_factory=dict)
    source: str = ""               # 来源: 手写/ai生成/录制
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, name: str, action: str, locator=None, value=None, **options) -> TestCase:
        """添加步骤（链式调用）"""
        self.steps.append(TestStep(
            name=name, action=action, locator=locator,
            value=value, options=options
        ))
        return self
