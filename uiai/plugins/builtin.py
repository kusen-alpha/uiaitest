"""内置插件 — TraceRecorder / KnowledgeSync / MetricsExporter"""
from __future__ import annotations
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from uiai.plugins.manager import BasePlugin

logger = logging.getLogger(__name__)


class TraceRecorder(BasePlugin):
    """Trace录制插件 — 记录每步操作的详细追踪信息"""

    name = "TraceRecorder"
    version = "1.0.0"
    description = "记录操作追踪"

    def __init__(self, output_dir: str = ".uiai_traces"):
        self._output_dir = Path(output_dir)
        self._current_trace: list[dict] = []
        self._trace_id: str = ""

    def on_before_test(self, context: dict) -> None:
        self._trace_id = f"trace_{int(time.time())}"
        self._current_trace = []

    def on_after_step(self, context: dict) -> None:
        step_info = {
            "step": len(self._current_trace),
            "action": context.get("action", ""),
            "locator": str(context.get("locator", "")),
            "success": context.get("success", False),
            "duration_ms": context.get("duration_ms", 0),
            "timestamp": datetime.now().isoformat(),
        }
        self._current_trace.append(step_info)

    def on_after_test(self, context: dict) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        trace_file = self._output_dir / f"{self._trace_id}.json"
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(self._current_trace, f, ensure_ascii=False, indent=2)
        logger.info(f"Trace saved: {trace_file}")


class KnowledgeSync(BasePlugin):
    """知识同步插件 — 自动将成功/失败经验沉淀到知识库"""

    name = "KnowledgeSync"
    version = "1.0.0"
    description = "自动知识沉淀"

    def __init__(self, knowledge_dir: str = ".uiai_knowledge"):
        self._knowledge_dir = Path(knowledge_dir)
        self._task_description: str = ""

    def on_before_test(self, context: dict) -> None:
        self._task_description = context.get("task", "")

    def on_after_test(self, context: dict) -> None:
        success = context.get("success", False)
        self._knowledge_dir.mkdir(parents=True, exist_ok=True)
        exp_file = self._knowledge_dir / "auto_experiences.jsonl"
        entry = {
            "task": self._task_description,
            "success": success,
            "steps": context.get("steps", 0),
            "duration_ms": context.get("duration_ms", 0),
            "timestamp": datetime.now().isoformat(),
        }
        with open(exp_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class MetricsExporter(BasePlugin):
    """指标导出插件 — 采集并导出执行指标"""

    name = "MetricsExporter"
    version = "1.0.0"
    description = "指标导出"

    def __init__(self, output_file: str = ".uiai_metrics/metrics.json"):
        self._output_file = Path(output_file)
        self._metrics: list[dict] = []

    def on_after_test(self, context: dict) -> None:
        metric = {
            "test_name": context.get("test_name", ""),
            "success": context.get("success", False),
            "duration_ms": context.get("duration_ms", 0),
            "steps": context.get("steps", 0),
            "llm_calls": context.get("llm_calls", 0),
            "token_usage": context.get("token_usage", {}),
            "cache_hits": context.get("cache_hits", 0),
            "heal_attempts": context.get("heal_attempts", 0),
            "timestamp": datetime.now().isoformat(),
        }
        self._metrics.append(metric)

    def on_before_stop(self, context: dict) -> None:
        self._output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._output_file, "w", encoding="utf-8") as f:
            json.dump(self._metrics, f, ensure_ascii=False, indent=2)
        logger.info(f"Metrics exported: {self._output_file}")
