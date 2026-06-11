"""测试执行结果模型"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    HEALED = "healed"       # 自愈后通过
    FLAKY = "flaky"         # 不稳定但最终通过

class StepStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    HEALED = "healed"

@dataclass
class StepResult:
    """单步执行结果"""
    name: str
    status: StepStatus
    duration_ms: float = 0.0
    error: str | None = None
    screenshot_path: str | None = None
    healing_applied: str | None = None  # 应用的自愈策略描述
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class TestResult:
    """单个测试用例结果"""
    test_id: str
    test_name: str
    status: TestStatus
    duration_ms: float = 0.0
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None
    traceback: str | None = None
    screenshots: list[str] = field(default_factory=list)
    trace_path: str | None = None
    video_path: str | None = None
    healing_records: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def passed(self) -> bool:
        return self.status in (TestStatus.PASSED, TestStatus.HEALED, TestStatus.FLAKY)

@dataclass
class SuiteResult:
    """测试套件结果"""
    suite_name: str
    results: list[TestResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASSED)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAILED)

    @property
    def healed_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.HEALED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.SKIPPED)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.ERROR)

    @property
    def pass_rate(self) -> float:
        if not self.total:
            return 0.0
        return (self.passed_count + self.healed_count) / self.total

    @property
    def duration_ms(self) -> float:
        return sum(r.duration_ms for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total": self.total,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "healed": self.healed_count,
            "skipped": self.skipped_count,
            "error": self.error_count,
            "pass_rate": f"{self.pass_rate:.1%}",
            "duration_ms": self.duration_ms,
        }
