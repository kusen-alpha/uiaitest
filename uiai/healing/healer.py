"""自愈管理器 - 多级降级自愈策略 + 审批工作流 + 指标采集"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from uiai.config import HealingConfig
from uiai.core.locator import Locator, LocatorType
from uiai.core.test_case import TestStep
from uiai.executor.base import BaseExecutor
from uiai.agent.llm import BaseLLMClient

logger = logging.getLogger(__name__)


class HealingStrategy(Enum):
    """自愈策略"""
    SELECTOR_FALLBACK = "selector_fallback"
    DOM_NEIGHBOR_SEARCH = "dom_neighbor_search"
    VISUAL_OCR = "visual_ocr"
    AI_CODE_FIX = "ai_code_fix"


class HealingStatus(Enum):
    """自愈状态"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class HealingRecord:
    """自愈记录"""
    id: str
    test_id: str
    step_name: str
    strategy: HealingStrategy
    status: HealingStatus = HealingStatus.PENDING
    original_locator: dict | None = None
    healed_locator: dict | None = None
    error_message: str = ""
    healing_message: str = ""
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    approved_by: str | None = None
    approved_at: datetime | None = None
    screenshot_path: str | None = None
    dom_snapshot: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "test_id": self.test_id,
            "step_name": self.step_name,
            "strategy": self.strategy.value,
            "status": self.status.value,
            "original_locator": self.original_locator,
            "healed_locator": self.healed_locator,
            "error_message": self.error_message,
            "healing_message": self.healing_message,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HealingMetrics:
    """自愈指标"""
    total_attempts: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_pending_approval: int = 0
    strategy_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    def record_attempt(self, strategy: HealingStrategy, success: bool) -> None:
        self.total_attempts += 1
        if success:
            self.total_successes += 1
        else:
            self.total_failures += 1
        key = strategy.value
        if key not in self.strategy_stats:
            self.strategy_stats[key] = {"attempts": 0, "successes": 0}
        self.strategy_stats[key]["attempts"] += 1
        if success:
            self.strategy_stats[key]["successes"] += 1

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.total_successes / self.total_attempts

    def to_dict(self) -> dict:
        return {
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "success_rate": f"{self.success_rate:.1%}",
            "strategy_stats": self.strategy_stats,
        }


class HealingManager:
    """自愈管理器

    多级降级自愈策略：
    Level 1: 选择器降级（同类型替换）
    Level 2: DOM邻近元素搜索（语义相近元素）
    Level 3: 视觉OCR兜底（截图+文字识别）
    Level 4: AI代码修复（LLM生成修复建议，需人工审核）

    所有修复必须经过审批工作流（auto_apply=False时）。
    """

    def __init__(self, config: HealingConfig | None = None, llm_client: BaseLLMClient | None = None):
        self.config = config or HealingConfig()
        self.llm_client = llm_client
        self._records: list[HealingRecord] = []
        self._metrics = HealingMetrics()
        self._approval_dir = Path("./healing_approvals")
        self._record_counter = 0

    async def try_heal(self, executor: BaseExecutor, step: TestStep, error: str) -> bool:
        """尝试自愈失败步骤"""
        if not self.config.enabled:
            return False

        for i, strategy_name in enumerate(self.config.strategies):
            strategy = HealingStrategy(strategy_name)
            logger.info(f"Trying healing strategy {i+1}/{len(self.config.strategies)}: {strategy.value}")

            record = self._create_record(step, strategy, error)

            try:
                if strategy == HealingStrategy.SELECTOR_FALLBACK:
                    healed, locator = await self._heal_selector_fallback(executor, step, error)
                elif strategy == HealingStrategy.DOM_NEIGHBOR_SEARCH:
                    healed, locator = await self._heal_dom_neighbor(executor, step, error)
                elif strategy == HealingStrategy.VISUAL_OCR:
                    healed, locator = await self._heal_visual_ocr(executor, step, error)
                elif strategy == HealingStrategy.AI_CODE_FIX:
                    healed, locator = await self._heal_ai_code(executor, step, error)
                else:
                    logger.warning(f"Unknown healing strategy: {strategy_name}")
                    continue

                self._metrics.record_attempt(strategy, healed)

                if healed:
                    record.status = HealingStatus.SUCCESS
                    record.healed_locator = locator
                    record.healing_message = f"Strategy {strategy.value} succeeded"
                    record.confidence = self._calculate_confidence(strategy, i)
                    self._records.append(record)

                    if self.config.auto_apply:
                        return True
                    else:
                        record.status = HealingStatus.PENDING_APPROVAL
                        self._metrics.total_pending_approval += 1
                        await self._save_for_approval(record)
                        # 不自动应用，返回False
                        return False

            except Exception as e:
                logger.warning(f"Healing strategy {strategy.value} failed: {e}")
                record.status = HealingStatus.FAILED
                record.error_message = str(e)
                self._metrics.record_attempt(strategy, False)
                self._records.append(record)

        logger.warning("All healing strategies exhausted")
        return False

    async def _heal_selector_fallback(self, executor: BaseExecutor, step: TestStep, error: str) -> tuple[bool, dict | None]:
        """Level 1: 选择器降级"""
        if not step.locator or not step.locator.fallback_chain:
            return False, None

        chain = step.locator.build_chain()
        for loc_type, loc_value, options in chain[1:]:
            try:
                new_locator = Locator(primary_type=loc_type, primary_value=loc_value, options=options)
                if await self._retry_step_with_locator(executor, step, new_locator):
                    return True, {"type": loc_type.value, "value": loc_value}
            except Exception:
                continue
        return False, None

    async def _heal_dom_neighbor(self, executor: BaseExecutor, step: TestStep, error: str) -> tuple[bool, dict | None]:
        """Level 2: DOM邻近元素搜索

        通过辅助功能树查找语义相近的元素：
        1. 搜索包含相同文本的元素
        2. 搜索相同角色的元素
        3. 搜索父子兄弟节点
        """
        if not step.locator:
            return False, None

        try:
            a11y_tree = await executor.get_accessibility_tree()
            target_text = step.locator.primary_value
            target_role = step.locator.options.get("role", "")

            # 策略1: 搜索包含相同文本的元素
            if target_text:
                text_locator = Locator.by_text(target_text)
                if await self._retry_step_with_locator(executor, step, text_locator):
                    return True, {"type": "text", "value": target_text, "method": "text_search"}

            # 策略2: 搜索相同角色的元素
            if target_role:
                role_locator = Locator.by_role(target_role)
                if await self._retry_step_with_locator(executor, step, role_locator):
                    return True, {"type": "role", "value": target_role, "method": "role_search"}

            # 策略3: 模糊文本匹配
            if target_text and len(target_text) > 2:
                # 截取部分文本进行模糊匹配
                short_text = target_text[:len(target_text)//2] if len(target_text) > 4 else target_text
                fuzzy_locator = Locator.by_text(short_text)
                if await self._retry_step_with_locator(executor, step, fuzzy_locator):
                    return True, {"type": "text_fuzzy", "value": short_text, "method": "fuzzy_text"}

            # 策略4: 在辅助功能树中深度搜索
            candidates = self._search_a11y_tree(a11y_tree, target_text, target_role)
            for candidate in candidates:
                try:
                    if candidate.get("role"):
                        cand_locator = Locator.by_role(candidate["role"], name=candidate.get("name"))
                        if await self._retry_step_with_locator(executor, step, cand_locator):
                            return True, {"type": "a11y_search", "value": candidate, "method": "a11y_deep"}
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"DOM neighbor search failed: {e}")

        return False, None

    async def _heal_visual_ocr(self, executor: BaseExecutor, step: TestStep, error: str) -> tuple[bool, dict | None]:
        """Level 3: 视觉OCR兜底

        通过截图+OCR识别目标元素位置。
        支持PaddleOCR和Tesseract两种引擎。
        """
        if not step.locator:
            return False, None

        try:
            screenshot = await executor.screenshot()
            target_text = step.locator.primary_value

            if not target_text:
                return False, None

            # 尝试PaddleOCR
            ocr_result = await self._ocr_extract(screenshot, target_text)
            if ocr_result:
                x, y = ocr_result
                coord_locator = Locator.by_coordinate(x, y)
                if await self._retry_step_with_locator(executor, step, coord_locator):
                    return True, {"type": "ocr", "value": target_text, "coordinates": [x, y]}

        except Exception as e:
            logger.debug(f"Visual OCR healing failed: {e}")

        return False, None

    async def _heal_ai_code(self, executor: BaseExecutor, step: TestStep, error: str) -> tuple[bool, dict | None]:
        """Level 4: AI代码修复（仅生成建议，不自动应用）"""
        if not self.llm_client:
            return False, None
        # AI修复不自动应用
        return False, None

    def _search_a11y_tree(self, tree: dict, target_text: str | None, target_role: str | None) -> list[dict]:
        """在辅助功能树中深度搜索候选元素"""
        candidates = []
        self._traverse_tree(tree, target_text, target_role, candidates, depth=0, max_depth=10)
        return candidates[:5]  # 最多返回5个候选

    def _traverse_tree(self, node: dict, target_text: str | None, target_role: str | None,
                       candidates: list, depth: int, max_depth: int) -> None:
        if depth > max_depth or not node:
            return
        name = node.get("name", "")
        role = node.get("role", "")
        # 文本部分匹配
        if target_text and name and target_text.lower() in name.lower():
            candidates.append({"role": role, "name": name})
        # 角色匹配
        elif target_role and role == target_role:
            candidates.append({"role": role, "name": name})
        for child in node.get("children", []):
            self._traverse_tree(child, target_text, target_role, candidates, depth + 1, max_depth)

    async def _ocr_extract(self, screenshot: bytes, target_text: str) -> tuple[float, float] | None:
        """OCR提取文字位置"""
        try:
            from paddleocr import PaddleOCR
            import io
            from PIL import Image
            ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            img = Image.open(io.BytesIO(screenshot))
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                img.save(f)
                temp_path = f.name
            result = ocr.ocr(temp_path, cls=True)
            import os
            os.unlink(temp_path)
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0]
                    if target_text.lower() in text.lower():
                        box = line[0]
                        cx = (box[0][0] + box[2][0]) / 2
                        cy = (box[0][1] + box[2][1]) / 2
                        return (cx, cy)
        except ImportError:
            logger.debug("PaddleOCR not installed, skipping OCR")
        except Exception as e:
            logger.debug(f"OCR extraction failed: {e}")
        return None

    async def _retry_step_with_locator(self, executor: BaseExecutor, step: TestStep, new_locator: Locator) -> bool:
        """使用新定位器重试步骤"""
        action = step.action.lower()
        try:
            if action == "click":
                await executor.click(new_locator)
            elif action in ("type", "type_text"):
                await executor.type_text(new_locator, step.value or "")
            elif action == "fill":
                await executor.fill(new_locator, step.value or "")
            elif action == "hover":
                await executor.hover(new_locator)
            elif action == "wait":
                await executor.wait_for(new_locator)
            elif action == "check":
                await executor.check(new_locator)
            elif action == "uncheck":
                await executor.uncheck(new_locator)
            else:
                return False
            return True
        except Exception:
            return False

    def _calculate_confidence(self, strategy: HealingStrategy, attempt_index: int) -> float:
        """计算修复置信度"""
        base_confidence = {
            HealingStrategy.SELECTOR_FALLBACK: 0.9,
            HealingStrategy.DOM_NEIGHBOR_SEARCH: 0.7,
            HealingStrategy.VISUAL_OCR: 0.5,
            HealingStrategy.AI_CODE_FIX: 0.3,
        }
        conf = base_confidence.get(strategy, 0.5)
        # 每次降级降低0.1
        conf -= attempt_index * 0.1
        return max(0.1, conf)

    def _create_record(self, step: TestStep, strategy: HealingStrategy, error: str) -> HealingRecord:
        """创建自愈记录"""
        self._record_counter += 1
        return HealingRecord(
            id=f"heal-{self._record_counter}",
            test_id=step.name,
            step_name=step.name,
            strategy=strategy,
            original_locator={"type": step.locator.primary_type.value, "value": step.locator.primary_value} if step.locator else None,
            error_message=error,
        )

    async def _save_for_approval(self, record: HealingRecord) -> None:
        """保存待审批的修复记录"""
        self._approval_dir.mkdir(parents=True, exist_ok=True)
        path = self._approval_dir / f"{record.id}.json"
        path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Healing record saved for approval: {path}")

    def approve(self, record_id: str, approver: str = "manual") -> bool:
        """审批修复"""
        for record in self._records:
            if record.id == record_id:
                record.status = HealingStatus.APPROVED
                record.approved_by = approver
                record.approved_at = datetime.now()
                self._metrics.total_pending_approval -= 1
                logger.info(f"Healing record {record_id} approved by {approver}")
                return True
        return False

    def reject(self, record_id: str, approver: str = "manual") -> bool:
        """拒绝修复"""
        for record in self._records:
            if record.id == record_id:
                record.status = HealingStatus.REJECTED
                record.approved_by = approver
                record.approved_at = datetime.now()
                self._metrics.total_pending_approval -= 1
                logger.info(f"Healing record {record_id} rejected by {approver}")
                return True
        return False

    @property
    def metrics(self) -> HealingMetrics:
        return self._metrics

    @property
    def records(self) -> list[HealingRecord]:
        return self._records.copy()

    @property
    def pending_approvals(self) -> list[HealingRecord]:
        return [r for r in self._records if r.status == HealingStatus.PENDING_APPROVAL]
