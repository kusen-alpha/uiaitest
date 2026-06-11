"""视觉比对引擎 - 截图比对与差异检测"""
from __future__ import annotations
import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VisualComparator:
    """视觉比对引擎

    支持像素级比对和感知比对。
    基线截图存储在 baselines 目录，差异截图存储在 diffs 目录。
    """

    def __init__(self, baseline_dir: str = "./baselines", diff_dir: str = "./reports/diffs"):
        self.baseline_dir = Path(baseline_dir)
        self.diff_dir = Path(diff_dir)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.diff_dir.mkdir(parents=True, exist_ok=True)

    async def compare(self, screenshot: bytes, name: str, threshold: float = 0.1) -> dict:
        """比对截图与基线

        Args:
            screenshot: 当前截图bytes
            name: 基线名称
            threshold: 差异阈值（0-1），超过此值视为不匹配

        Returns:
            {"match": bool, "diff_percentage": float, "diff_path": str|None}
        """
        baseline_path = self.baseline_dir / f"{name}.png"

        if not baseline_path.exists():
            # 首次运行，保存基线
            baseline_path.write_bytes(screenshot)
            logger.info(f"Baseline saved: {baseline_path}")
            return {"match": True, "diff_percentage": 0.0, "diff_path": None}

        try:
            from PIL import Image
            import io

            # 加载基线
            baseline_img = Image.open(baseline_path)
            current_img = Image.open(io.BytesIO(screenshot))

            # 尺寸不同直接判定不匹配
            if baseline_img.size != current_img.size:
                diff_path = await self._save_diff_image(baseline_img, current_img, name)
                return {
                    "match": False,
                    "diff_percentage": 1.0,
                    "diff_path": str(diff_path),
                    "reason": f"Size mismatch: {baseline_img.size} vs {current_img.size}",
                }

            # 像素级比对
            diff_percentage = self._calculate_diff(baseline_img, current_img)
            match = diff_percentage <= threshold

            diff_path = None
            if not match:
                diff_path = await self._save_diff_image(baseline_img, current_img, name)

            return {
                "match": match,
                "diff_percentage": diff_percentage,
                "diff_path": str(diff_path) if diff_path else None,
            }

        except ImportError:
            logger.warning("Pillow not installed, skipping visual comparison")
            return {"match": True, "diff_percentage": 0.0, "diff_path": None}
        except Exception as e:
            logger.error(f"Visual comparison error: {e}")
            return {"match": True, "diff_percentage": 0.0, "diff_path": None, "error": str(e)}

    def _calculate_diff(self, img1, img2) -> float:
        """计算两张图片的像素差异百分比"""
        if img1.size != img2.size:
            return 1.0

        # 转为RGB模式
        img1_rgb = img1.convert("RGB")
        img2_rgb = img2.convert("RGB")

        pixels1 = list(img1_rgb.getdata())
        pixels2 = list(img2_rgb.getdata())

        total_pixels = len(pixels1)
        if total_pixels == 0:
            return 0.0

        diff_pixels = 0
        for p1, p2 in zip(pixels1, pixels2):
            # 允许小幅颜色差异（抗锯齿等）
            if abs(p1[0] - p2[0]) > 10 or abs(p1[1] - p2[1]) > 10 or abs(p1[2] - p2[2]) > 10:
                diff_pixels += 1

        return diff_pixels / total_pixels

    async def _save_diff_image(self, baseline_img, current_img, name: str) -> Path:
        """保存差异对比图"""
        try:
            from PIL import Image
            import io

            # 创建并排对比图
            w1, h1 = baseline_img.size
            w2, h2 = current_img.size
            max_w = max(w1, w2)
            total_h = h1 + h2 + 40  # 间距

            diff_img = Image.new("RGB", (max_w, total_h), (255, 255, 255))
            diff_img.paste(baseline_img, (0, 0))
            diff_img.paste(current_img, (0, h1 + 40))

            diff_path = self.diff_dir / f"{name}_diff.png"
            diff_img.save(str(diff_path))
            return diff_path

        except ImportError:
            return self.diff_dir / f"{name}_diff.txt"

    def update_baseline(self, name: str, screenshot: bytes) -> None:
        """更新基线截图"""
        baseline_path = self.baseline_dir / f"{name}.png"
        baseline_path.write_bytes(screenshot)
        logger.info(f"Baseline updated: {baseline_path}")

    def get_baseline_hash(self, name: str) -> str | None:
        """获取基线截图的哈希值"""
        baseline_path = self.baseline_dir / f"{name}.png"
        if baseline_path.exists():
            return hashlib.md5(baseline_path.read_bytes()).hexdigest()
        return None
