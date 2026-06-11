"""报告生成器 - JSON/HTML/Allure/趋势报告"""
from __future__ import annotations
import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from uiai.core.result import SuiteResult, TestResult, TestStatus, StepResult

logger = logging.getLogger(__name__)


class ReportGenerator:
    """报告生成器

    支持多种报告格式：
    - JSON: 结构化数据
    - HTML: 可视化报告（含截图/视频/自愈信息）
    - Allure: Allure框架兼容格式
    - Console: 终端输出
    - Trend: 趋势报告（通过率随时间变化）
    """

    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._trend_file = self.output_dir / "trend_data.json"

    # --- JSON报告 ---

    def generate_json_report(self, suite_result: SuiteResult, filename: str | None = None) -> str:
        """生成JSON格式报告"""
        filename = filename or f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = self.output_dir / filename

        data = {
            "suite_name": suite_result.suite_name,
            "summary": suite_result.to_dict(),
            "timestamp": datetime.now().isoformat(),
            "results": [],
        }

        for r in suite_result.results:
            result_data = {
                "test_id": r.test_id,
                "test_name": r.test_name,
                "status": r.status.value,
                "duration_ms": r.duration_ms,
                "error": r.error,
                "traceback": r.traceback,
                "steps": [
                    {
                        "name": s.name,
                        "status": s.status.value,
                        "duration_ms": s.duration_ms,
                        "error": s.error,
                        "healing_applied": s.healing_applied,
                        "screenshot_path": s.screenshot_path,
                    }
                    for s in r.steps
                ],
                "healing_records": r.healing_records,
                "screenshots": r.screenshots,
                "trace_path": r.trace_path,
                "video_path": r.video_path,
            }
            data["results"].append(result_data)

        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"JSON report generated: {path}")
        return str(path)

    # --- HTML报告 ---

    def generate_html_report(self, suite_result: SuiteResult, filename: str | None = None) -> str:
        """生成HTML格式报告（含截图/视频/自愈信息）"""
        filename = filename or f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path = self.output_dir / filename

        html = self._build_html(suite_result)
        path.write_text(html, encoding="utf-8")
        logger.info(f"HTML report generated: {path}")
        return str(path)

    # --- Allure报告 ---

    def generate_allure_results(self, suite_result: SuiteResult, allure_dir: str | None = None) -> str:
        """生成Allure兼容的结果文件"""
        allure_dir = Path(allure_dir or self.output_dir / "allure-results")
        allure_dir.mkdir(parents=True, exist_ok=True)

        for r in suite_result.results:
            allure_result = {
                "name": r.test_name,
                "fullName": f"{suite_result.suite_name}.{r.test_name}",
                "status": self._to_allure_status(r.status),
                "start": int(r.timestamp.timestamp() * 1000) if r.timestamp else 0,
                "stop": int((r.timestamp.timestamp() * 1000) + r.duration_ms) if r.timestamp else 0,
                "duration": int(r.duration_ms),
                "labels": [
                    {"name": "suite", "value": suite_result.suite_name},
                    {"name": "framework", "value": "uiai"},
                ],
                "steps": [],
            }

            for s in r.steps:
                step = {
                    "name": s.name,
                    "status": self._to_allure_step_status(s.status),
                    "start": int(s.timestamp.timestamp() * 1000) if s.timestamp else 0,
                    "stop": int((s.timestamp.timestamp() * 1000) + s.duration_ms) if s.timestamp else 0,
                    "duration": int(s.duration_ms),
                }
                if s.error:
                    step["statusDetails"] = {"message": s.error}
                if s.healing_applied:
                    step["statusDetails"] = step.get("statusDetails", {})
                    step["statusDetails"]["message"] = f"[Healed] {s.healing_applied}"
                allure_result["steps"].append(step)

            if r.error:
                allure_result["statusDetails"] = {"message": r.error}
                if r.traceback:
                    allure_result["statusDetails"]["trace"] = r.traceback

            # 写入文件
            result_path = allure_dir / f"{r.test_id}-result.json"
            result_path.write_text(json.dumps(allure_result, ensure_ascii=False, indent=2), encoding="utf-8")

            # 附件（截图）
            for i, ss in enumerate(r.screenshots):
                ss_path = Path(ss)
                if ss_path.exists():
                    attachment = allure_dir / f"{r.test_id}-attachment-{i}.png"
                    shutil.copy2(ss_path, attachment)

        logger.info(f"Allure results generated: {allure_dir}")
        return str(allure_dir)

    @staticmethod
    def _to_allure_status(status: TestStatus) -> str:
        mapping = {
            TestStatus.PASSED: "passed",
            TestStatus.FAILED: "failed",
            TestStatus.SKIPPED: "skipped",
            TestStatus.ERROR: "broken",
            TestStatus.HEALED: "passed",
            TestStatus.FLAKY: "passed",
        }
        return mapping.get(status, "unknown")

    @staticmethod
    def _to_allure_step_status(status) -> str:
        from uiai.core.result import StepStatus
        mapping = {
            StepStatus.PASSED: "passed",
            StepStatus.FAILED: "failed",
            StepStatus.SKIPPED: "skipped",
            StepStatus.HEALED: "passed",
        }
        return mapping.get(status, "unknown")

    # --- 趋势报告 ---

    def record_trend(self, suite_result: SuiteResult) -> None:
        """记录趋势数据"""
        trend_data = self._load_trend()
        trend_data.append({
            "timestamp": datetime.now().isoformat(),
            "suite_name": suite_result.suite_name,
            "total": suite_result.total,
            "passed": suite_result.passed_count,
            "failed": suite_result.failed_count,
            "healed": suite_result.healed_count,
            "pass_rate": suite_result.pass_rate,
            "duration_ms": suite_result.duration_ms,
        })
        # 保留最近100条
        trend_data = trend_data[-100:]
        self._trend_file.write_text(json.dumps(trend_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def generate_trend_report(self, filename: str = "trend.html") -> str:
        """生成趋势报告HTML"""
        trend_data = self._load_trend()
        if not trend_data:
            logger.warning("No trend data available")
            return ""

        path = self.output_dir / filename
        html = self._build_trend_html(trend_data)
        path.write_text(html, encoding="utf-8")
        logger.info(f"Trend report generated: {path}")
        return str(path)

    def _load_trend(self) -> list[dict]:
        if self._trend_file.exists():
            return json.loads(self._trend_file.read_text(encoding="utf-8"))
        return []

    # --- Console报告 ---

    def generate_console_report(self, suite_result: SuiteResult) -> str:
        """生成终端输出报告"""
        lines = []
        lines.append("=" * 70)
        lines.append(f"  UIAI 测试报告: {suite_result.suite_name}")
        lines.append("=" * 70)
        lines.append(f"  总计: {suite_result.total}  通过: {suite_result.passed_count}  "
                     f"失败: {suite_result.failed_count}  自愈: {suite_result.healed_count}  "
                     f"跳过: {suite_result.skipped_count}  错误: {suite_result.error_count}")
        lines.append(f"  通过率: {suite_result.pass_rate:.1%}  耗时: {suite_result.duration_ms:.0f}ms")
        lines.append("-" * 70)

        for r in suite_result.results:
            status_icon = {"passed": "✓", "failed": "✗", "healed": "⟳", "skipped": "○", "error": "!", "flaky": "~"}.get(r.status.value, "?")
            lines.append(f"  {status_icon} {r.test_name} ({r.duration_ms:.0f}ms)")
            if r.error:
                lines.append(f"    错误: {r.error[:200]}")
            for s in r.steps:
                s_icon = {"passed": "  ✓", "failed": "  ✗", "healed": "  ⟳", "skipped": "  ○"}.get(s.status.value, "  ?")
                healing = f" [自愈: {s.healing_applied}]" if s.healing_applied else ""
                lines.append(f"  {s_icon} {s.name} ({s.duration_ms:.0f}ms){healing}")
                if s.error:
                    lines.append(f"      {s.error[:150]}")
            for h in r.healing_records:
                lines.append(f"    🔧 自愈: {h.get('strategy', 'unknown')} @ {h.get('step', '')}")

        lines.append("=" * 70)
        output = "\n".join(lines)
        print(output)
        return output

    # --- HTML构建 ---

    def _build_html(self, suite_result: SuiteResult) -> str:
        summary = suite_result.to_dict()
        status_colors = {
            "passed": "#4caf50", "failed": "#f44336", "healed": "#ff9800",
            "skipped": "#9e9e9e", "error": "#f44336", "flaky": "#ffc107",
        }

        rows = ""
        for r in suite_result.results:
            color = status_colors.get(r.status.value, "#666")
            steps_html = ""
            for s in r.steps:
                s_color = status_colors.get(s.status.value, "#666")
                healing = f' <span style="color:#ff9800;font-weight:bold">[自愈: {s.healing_applied}]</span>' if s.healing_applied else ""
                error_html = f' <span style="color:#f44336;font-size:11px">{s.error}</span>' if s.error else ""
                steps_html += f'<div style="margin-left:20px;padding:2px 0;color:{s_color}">{s.status.value}: {s.name} ({s.duration_ms:.0f}ms){healing}{error_html}</div>'

            error_html = f'<div style="color:#f44336;margin-left:20px;font-size:12px;padding:4px 0">{r.error}</div>' if r.error else ""

            # 自愈记录
            healing_html = ""
            for h in r.healing_records:
                healing_html += f'<div style="margin-left:20px;color:#ff9800;font-size:12px">🔧 {h.get("strategy","")} @ {h.get("step","")}</div>'

            # 截图
            screenshots_html = ""
            for ss in r.screenshots:
                if Path(ss).exists():
                    screenshots_html += f'<div style="margin-left:20px"><a href="{ss}" target="_blank">📷 截图</a></div>'

            rows += f"""
            <tr>
                <td>{r.test_id}</td>
                <td>{r.test_name}</td>
                <td style="color:{color};font-weight:bold">{r.status.value.upper()}</td>
                <td>{r.duration_ms:.0f}ms</td>
                <td>{steps_html}{error_html}{healing_html}{screenshots_html}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>UIAI 测试报告 - {suite_result.suite_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f0f2f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0 0 10px 0; font-size: 24px; }}
        .header .meta {{ opacity: 0.9; font-size: 14px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px; margin: 20px 0; }}
        .summary-card {{ padding: 20px; border-radius: 10px; color: white; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .summary-card .number {{ font-size: 28px; font-weight: bold; }}
        .summary-card .label {{ font-size: 12px; opacity: 0.9; margin-top: 5px; }}
        .table-container {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #fafafa; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #eee; font-size: 13px; color: #666; }}
        td {{ padding: 12px; border-bottom: 1px solid #f0f0f0; vertical-align: top; font-size: 13px; }}
        tr:hover {{ background: #fafbfc; }}
        .status-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>UIAI 测试报告</h1>
            <div class="meta">{suite_result.suite_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | uiai v0.1.0</div>
        </div>
        <div class="summary">
            <div class="summary-card" style="background:#2196f3"><div class="number">{summary['total']}</div><div class="label">总计</div></div>
            <div class="summary-card" style="background:#4caf50"><div class="number">{summary['passed']}</div><div class="label">通过</div></div>
            <div class="summary-card" style="background:#f44336"><div class="number">{summary['failed']}</div><div class="label">失败</div></div>
            <div class="summary-card" style="background:#ff9800"><div class="number">{summary['healed']}</div><div class="label">自愈</div></div>
            <div class="summary-card" style="background:#9e9e9e"><div class="number">{summary['skipped']}</div><div class="label">跳过</div></div>
            <div class="summary-card" style="background:#4caf50"><div class="number">{summary['pass_rate']}</div><div class="label">通过率</div></div>
        </div>
        <div class="table-container">
            <table>
                <thead><tr><th>ID</th><th>名称</th><th>状态</th><th>耗时</th><th>详情</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </div>
</body>
</html>"""

    def _build_trend_html(self, trend_data: list[dict]) -> str:
        """构建趋势报告HTML（使用简单的ASCII图表，不依赖外部JS库）"""
        rows = ""
        for entry in trend_data[-20:]:
            ts = entry.get("timestamp", "")[:16]
            rate = entry.get("pass_rate", 0)
            bar_width = int(rate * 200)
            color = "#4caf50" if rate >= 0.9 else "#ff9800" if rate >= 0.7 else "#f44336"
            rows += f"""
            <tr>
                <td>{ts}</td>
                <td>{entry.get('suite_name', '')}</td>
                <td>{entry.get('total', 0)}</td>
                <td>{entry.get('passed', 0)}</td>
                <td>{entry.get('failed', 0)}</td>
                <td>{entry.get('healed', 0)}</td>
                <td>
                    <div style="display:flex;align-items:center;gap:8px">
                        <div style="width:200px;background:#eee;border-radius:4px;height:20px;overflow:hidden">
                            <div style="width:{bar_width}px;background:{color};height:100%;border-radius:4px"></div>
                        </div>
                        <span>{rate:.1%}</span>
                    </div>
                </td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>UIAI 趋势报告</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 20px; background: #f0f2f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 12px; }}
        h1 {{ color: #333; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #fafafa; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>UIAI 趋势报告</h1>
        <table>
            <thead><tr><th>时间</th><th>套件</th><th>总计</th><th>通过</th><th>失败</th><th>自愈</th><th>通过率</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
</body>
</html>"""
