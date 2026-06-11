"""Flaky测试检测器 - 识别不稳定的测试用例"""
from __future__ import annotations
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from uiai.core.result import TestResult, TestStatus

logger = logging.getLogger(__name__)


@dataclass
class FlakyRecord:
    """Flaky记录"""
    test_id: str
    test_name: str
    total_runs: int = 0
    pass_runs: int = 0
    fail_runs: int = 0
    heal_runs: int = 0
    recent_results: list[str] = field(default_factory=list)  # 最近N次结果
    flaky_score: float = 0.0  # 0-1, 越高越不稳定
    first_seen: str = ""
    last_seen: str = ""

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "total_runs": self.total_runs,
            "pass_runs": self.pass_runs,
            "fail_runs": self.fail_runs,
            "heal_runs": self.heal_runs,
            "flaky_score": round(self.flaky_score, 3),
            "recent_results": self.recent_results[-10:],
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class FlakyDetector:
    """Flaky测试检测器

    通过历史执行数据识别不稳定的测试用例。
    Flaky定义：同一测试在相同条件下，有时通过有时失败。

    检测算法：
    1. 交替率：通过/失败交替出现的频率
    2. 失败率：总失败次数/总执行次数
    3. 自愈率：需要自愈才能通过的比率
    4. 综合评分：加权计算
    """

    def __init__(self, history_dir: str = "./history", flaky_threshold: float = 0.3,
                 min_runs: int = 5, max_recent: int = 20):
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.flaky_threshold = flaky_threshold
        self.min_runs = min_runs
        self.max_recent = max_recent
        self._records: dict[str, FlakyRecord] = {}
        self._load_history()

    def record(self, result: TestResult) -> FlakyRecord | None:
        """记录测试结果并更新Flaky评分"""
        test_id = result.test_id
        if test_id not in self._records:
            self._records[test_id] = FlakyRecord(
                test_id=test_id,
                test_name=result.test_name,
                first_seen=datetime.now().isoformat(),
            )

        record = self._records[test_id]
        record.total_runs += 1
        record.last_seen = datetime.now().isoformat()

        if result.status == TestStatus.PASSED:
            record.pass_runs += 1
            record.recent_results.append("pass")
        elif result.status == TestStatus.FAILED:
            record.fail_runs += 1
            record.recent_results.append("fail")
        elif result.status == TestStatus.HEALED:
            record.heal_runs += 1
            record.recent_results.append("heal")
        elif result.status == TestStatus.FLAKY:
            record.recent_results.append("flaky")
        else:
            record.recent_results.append("other")

        # 保留最近N次
        if len(record.recent_results) > self.max_recent:
            record.recent_results = record.recent_results[-self.max_recent:]

        # 计算Flaky评分
        record.flaky_score = self._calculate_flaky_score(record)

        # 持久化
        self._save_record(record)

        return record

    def _calculate_flaky_score(self, record: FlakyRecord) -> float:
        """计算Flaky评分"""
        if record.total_runs < self.min_runs:
            return 0.0

        # 1. 失败率 (0-1)
        fail_rate = record.fail_runs / record.total_runs

        # 2. 自愈率 (0-1) - 自愈率高说明测试不稳定
        heal_rate = record.heal_runs / record.total_runs

        # 3. 交替率 - 通过/失败交替出现的频率
        alternation_count = 0
        recent = record.recent_results
        for i in range(1, len(recent)):
            if recent[i] != recent[i-1]:
                alternation_count += 1
        alternation_rate = alternation_count / max(len(recent) - 1, 1)

        # 加权综合评分
        score = (fail_rate * 0.3) + (heal_rate * 0.3) + (alternation_rate * 0.4)
        return min(score, 1.0)

    def is_flaky(self, test_id: str) -> bool:
        """判断测试是否为Flaky"""
        record = self._records.get(test_id)
        if not record or record.total_runs < self.min_runs:
            return False
        return record.flaky_score >= self.flaky_threshold

    def get_flaky_tests(self) -> list[FlakyRecord]:
        """获取所有Flaky测试"""
        return [
            r for r in self._records.values()
            if r.flaky_score >= self.flaky_threshold and r.total_runs >= self.min_runs
        ]

    def get_stable_tests(self) -> list[FlakyRecord]:
        """获取所有稳定测试"""
        return [
            r for r in self._records.values()
            if r.flaky_score < self.flaky_threshold and r.total_runs >= self.min_runs
        ]

    def get_stats(self) -> dict:
        """获取统计信息"""
        total = len(self._records)
        flaky = len(self.get_flaky_tests())
        stable = len(self.get_stable_tests())
        insufficient = total - flaky - stable
        return {
            "total_tests": total,
            "flaky_tests": flaky,
            "stable_tests": stable,
            "insufficient_data": insufficient,
            "flaky_rate": f"{flaky/max(total,1):.1%}",
        }

    def _save_record(self, record: FlakyRecord) -> None:
        path = self.history_dir / f"{record.test_id}.json"
        path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_history(self) -> None:
        for path in self.history_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = FlakyRecord(
                    test_id=data["test_id"],
                    test_name=data["test_name"],
                    total_runs=data.get("total_runs", 0),
                    pass_runs=data.get("pass_runs", 0),
                    fail_runs=data.get("fail_runs", 0),
                    heal_runs=data.get("heal_runs", 0),
                    recent_results=data.get("recent_results", []),
                    flaky_score=data.get("flaky_score", 0.0),
                    first_seen=data.get("first_seen", ""),
                    last_seen=data.get("last_seen", ""),
                )
                self._records[record.test_id] = record
            except Exception:
                pass
