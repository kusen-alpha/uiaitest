"""Lighthouse性能测试集成 - Web性能基线检测"""
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PerformanceResult:
    """性能测试结果"""
    url: str
    performance_score: float = 0.0
    accessibility_score: float = 0.0
    best_practices_score: float = 0.0
    seo_score: float = 0.0
    fcp: float = 0.0  # First Contentful Paint (ms)
    lcp: float = 0.0  # Largest Contentful Paint (ms)
    cls: float = 0.0  # Cumulative Layout Shift
    tti: float = 0.0  # Time to Interactive (ms)
    tbt: float = 0.0  # Total Blocking Time (ms)
    si: float = 0.0   # Speed Index (ms)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "scores": {
                "performance": self.performance_score,
                "accessibility": self.accessibility_score,
                "best_practices": self.best_practices_score,
                "seo": self.seo_score,
            },
            "metrics": {
                "FCP": f"{self.fcp:.0f}ms",
                "LCP": f"{self.lcp:.0f}ms",
                "CLS": f"{self.cls:.3f}",
                "TTI": f"{self.tti:.0f}ms",
                "TBT": f"{self.tbt:.0f}ms",
                "SI": f"{self.si:.0f}ms",
            },
            "timestamp": self.timestamp,
        }

    @property
    def is_good(self) -> bool:
        """性能是否达标（Core Web Vitals）"""
        return (
            self.performance_score >= 0.9
            and self.lcp <= 2500
            and self.cls <= 0.1
            and self.tbt <= 200
        )


class LighthouseRunner:
    """Lighthouse性能测试运行器

    通过Playwright执行Lighthouse审计，生成性能报告。
    支持基线对比和回归检测。
    """

    def __init__(self, output_dir: str = "./performance_reports",
                 baseline_dir: str = "./performance_baselines"):
        self.output_dir = Path(output_dir)
        self.baseline_dir = Path(baseline_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)

    async def run(self, url: str, device: str = "desktop",
                  categories: list[str] | None = None) -> PerformanceResult:
        """执行Lighthouse性能测试"""
        categories = categories or ["performance", "accessibility", "best-practices", "seo"]

        try:
            # 使用lighthouse CLI
            output_path = self.output_dir / f"lh_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            cmd = [
                "npx", "lighthouse", url,
                "--output=json",
                f"--output-path={output_path}",
                f"--only-categories={','.join(categories)}",
                "--chrome-flags=--headless",
                "--quiet",
            ]
            if device == "mobile":
                cmd.append("--emulated-form-factor=mobile")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if output_path.exists():
                return self._parse_result(url, output_path)
            else:
                logger.warning(f"Lighthouse output not found: {output_path}")
                return PerformanceResult(url=url)

        except FileNotFoundError:
            logger.warning("lighthouse CLI not available, using Playwright-based metrics")
            return await self._playwright_metrics(url)

    def _parse_result(self, url: str, path: Path) -> PerformanceResult:
        """解析Lighthouse JSON结果"""
        data = json.loads(path.read_text(encoding="utf-8"))
        categories = data.get("categories", {})
        audits = data.get("audits", {})

        def get_score(cat_name: str) -> float:
            cat = categories.get(cat_name, {})
            return cat.get("score", 0.0) or 0.0

        def get_metric(name: str) -> float:
            audit = audits.get(name, {})
            return audit.get("numericValue", 0.0) or 0.0

        return PerformanceResult(
            url=url,
            performance_score=get_score("performance"),
            accessibility_score=get_score("accessibility"),
            best_practices_score=get_score("best-practices"),
            seo_score=get_score("seo"),
            fcp=get_metric("first-contentful-paint"),
            lcp=get_metric("largest-contentful-paint"),
            cls=get_metric("cumulative-layout-shift"),
            tti=get_metric("interactive"),
            tbt=get_metric("total-blocking-time"),
            si=get_metric("speed-index"),
        )

    async def _playwright_metrics(self, url: str) -> PerformanceResult:
        """使用Playwright获取基础性能指标（Lighthouse不可用时的降级方案）"""
        try:
            from uiai.executor.playwright_executor import PlaywrightExecutor
            from uiai.config import BrowserConfig

            executor = PlaywrightExecutor(BrowserConfig(headless=True))
            await executor.start()
            await executor.navigate(url)

            # 获取Navigation Timing API数据
            metrics = await executor.evaluate("""() => {
                const [nav] = performance.getEntriesByType('navigation');
                return {
                    fcp: nav ? nav.loadEventEnd - nav.startTime : 0,
                    domContentLoaded: nav ? nav.domContentLoadedEventEnd - nav.startTime : 0,
                    loadComplete: nav ? nav.loadEventEnd - nav.startTime : 0,
                };
            }""")

            await executor.stop()

            return PerformanceResult(
                url=url,
                performance_score=0.0,  # 需要Lighthouse才能计算
                fcp=metrics.get("fcp", 0),
            )
        except Exception as e:
            logger.warning(f"Playwright metrics failed: {e}")
            return PerformanceResult(url=url)

    def save_baseline(self, result: PerformanceResult, name: str = "default") -> str:
        """保存性能基线"""
        path = self.baseline_dir / f"{name}.json"
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def load_baseline(self, name: str = "default") -> dict | None:
        """加载性能基线"""
        path = self.baseline_dir / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def compare_with_baseline(self, result: PerformanceResult, baseline_name: str = "default") -> dict:
        """与基线对比"""
        baseline = self.load_baseline(baseline_name)
        if not baseline:
            return {"status": "no_baseline", "message": "No baseline found"}

        baseline_metrics = baseline.get("metrics", {})
        current = result.to_dict().get("metrics", {})

        regression = []
        for key in ["FCP", "LCP", "TBT"]:
            b_val = float(baseline_metrics.get(key, "0").replace("ms", ""))
            c_val = float(current.get(key, "0").replace("ms", ""))
            if b_val > 0 and c_val > b_val * 1.2:  # 超过基线20%视为回归
                regression.append(f"{key}: {c_val:.0f}ms (baseline: {b_val:.0f}ms, +{(c_val/b_val-1)*100:.0f}%)")

        return {
            "status": "regression" if regression else "ok",
            "regressions": regression,
            "baseline": baseline,
            "current": result.to_dict(),
        }
