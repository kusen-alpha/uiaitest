"""Flaky测试检测器 - 识别不稳定的测试用例"""
from __future__ import annotations
import asyncio
import enum
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from uiai.core.result import TestResult, TestStatus

logger = logging.getLogger(__name__)


class FlakyMark(enum.Enum):
    """Flaky标记等级"""
    SUSPECTED = "疑似"    # score 0.3-0.5
    CONFIRMED = "确认"    # score 0.5-0.8
    SEVERE = "严重"       # score > 0.8


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

    # ── FlakyMarking: 三级标记系统 ──────────────────────────────

    def mark_flaky(self, test_id: str) -> FlakyMark | None:
        """根据 flaky_score 返回标记等级

        Returns:
            FlakyMark 等级，若测试不存在或数据不足则返回 None
        """
        record = self._records.get(test_id)
        if not record or record.total_runs < self.min_runs:
            return None

        score = record.flaky_score
        if score > 0.8:
            return FlakyMark.SEVERE
        elif score >= 0.5:
            return FlakyMark.CONFIRMED
        elif score >= self.flaky_threshold:
            return FlakyMark.SUSPECTED
        return None

    # ── FlakyIsolation: 隔离验证执行 ───────────────────────────

    async def isolate_and_verify(self, test_id: str, executor_factory, test_case,
                                 repeat: int = 3) -> dict:
        """在隔离环境中多次运行测试以验证是否为 Flaky

        Args:
            test_id: 测试标识
            executor_factory: 可调用对象，返回一个可执行测试的执行器
            test_case: 测试用例对象
            repeat: 重复执行次数，默认3次

        Returns:
            {"test_id": ..., "results": [bool], "pass_rate": float, "is_flaky": bool}
        """
        results: list[bool] = []

        for i in range(repeat):
            try:
                executor = executor_factory()
                if asyncio.iscoroutinefunction(executor):
                    result = await executor(test_case)
                else:
                    result = executor(test_case)

                # 判断执行结果是否为通过
                if isinstance(result, TestResult):
                    passed = result.status in (TestStatus.PASSED, TestStatus.HEALED)
                elif isinstance(result, bool):
                    passed = result
                else:
                    passed = bool(result)

                results.append(passed)
            except Exception:
                results.append(False)

        pass_rate = sum(results) / len(results) if results else 0.0
        # 通过率不一致（既非全通过也非全失败）则确认为 Flaky
        is_flaky = 0.0 < pass_rate < 1.0

        return {
            "test_id": test_id,
            "results": results,
            "pass_rate": round(pass_rate, 3),
            "is_flaky": is_flaky,
        }

    # ── RepairSuggestions: 根因分析与修复建议 ───────────────────

    def suggest_repairs(self, test_id: str) -> list[dict]:
        """分析失败模式并返回修复建议列表

        根据历史记录中的失败模式匹配对应的修复建议类型。
        """
        record = self._records.get(test_id)
        if not record or record.total_runs < self.min_runs:
            return []

        suggestions: list[dict] = []
        recent = record.recent_results

        # 交替率高 → 时序问题
        alternation_count = 0
        for i in range(1, len(recent)):
            if recent[i] != recent[i - 1]:
                alternation_count += 1
        alternation_rate = alternation_count / max(len(recent) - 1, 1)

        if alternation_rate > 0.5:
            suggestions.append({
                "type": "timing",
                "suggestion": "添加显式等待，元素可能在动态加载",
            })

        # 自愈率高 → 选择器不稳定
        if record.total_runs > 0:
            heal_rate = record.heal_runs / record.total_runs
            if heal_rate > 0.2:
                suggestions.append({
                    "type": "selector",
                    "suggestion": "选择器可能不稳定，建议使用data-testid",
                })

        # 失败率高且交替率低 → 外部依赖问题
        if record.total_runs > 0:
            fail_rate = record.fail_runs / record.total_runs
            if fail_rate > 0.4 and alternation_rate <= 0.5:
                suggestions.append({
                    "type": "dependency",
                    "suggestion": "测试可能依赖外部服务，建议添加Mock",
                })

        # 通过/失败交替但无明显自愈 → 数据不一致
        if alternation_rate > 0.3 and record.heal_runs == 0 and record.fail_runs > 0:
            suggestions.append({
                "type": "data",
                "suggestion": "测试数据可能不一致，建议使用数据工厂",
            })

        # 若无特定模式匹配，给出通用建议
        if not suggestions and record.flaky_score >= self.flaky_threshold:
            suggestions.append({
                "type": "general",
                "suggestion": "测试存在不稳定表现，建议增加重试机制并排查环境因素",
            })

        return suggestions

    # ── ReviewMechanism: 定期审查 ──────────────────────────────

    def review_flaky_tests(self) -> list[dict]:
        """审查所有 Flaky 测试，检查是否有测试已趋于稳定

        对于最近5次运行全部通过的测试，建议降级或移除标记。

        Returns:
            审查条目列表
        """
        review_items: list[dict] = []

        for record in self.get_flaky_tests():
            recent = record.recent_results[-5:]
            current_mark = self.mark_flaky(record.test_id)

            if not current_mark:
                continue

            # 最近5次全部通过 → 建议移除标记
            if len(recent) >= 5 and all(r == "pass" for r in recent):
                review_items.append({
                    "test_id": record.test_id,
                    "current_mark": current_mark.value,
                    "suggested_action": "remove",
                    "reason": f"最近{len(recent)}次运行全部通过，测试已趋于稳定",
                })
            # 最近5次中通过率 >= 80% → 建议降级
            elif len(recent) >= 5:
                pass_count = sum(1 for r in recent if r == "pass")
                if pass_count >= 4:
                    review_items.append({
                        "test_id": record.test_id,
                        "current_mark": current_mark.value,
                        "suggested_action": "downgrade",
                        "reason": f"最近{len(recent)}次运行中{pass_count}次通过，稳定性提升",
                    })
                else:
                    review_items.append({
                        "test_id": record.test_id,
                        "current_mark": current_mark.value,
                        "suggested_action": "keep",
                        "reason": f"最近{len(recent)}次运行中仅{pass_count}次通过，仍不稳定",
                    })
            else:
                review_items.append({
                    "test_id": record.test_id,
                    "current_mark": current_mark.value,
                    "suggested_action": "keep",
                    "reason": f"运行次数不足5次，无法判断稳定性",
                })

        return review_items
