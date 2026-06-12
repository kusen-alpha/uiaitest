"""检查点管理器 - 浏览器状态快照与恢复

提供检查点的保存、恢复和自动管理功能，支持在测试执行过程中
捕获浏览器完整状态（URL、Cookie、localStorage、滚动位置等），
并在需要时回滚到任意检查点。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from uiai.executor.base import BaseExecutor

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """检查点数据类

    保存某一时刻浏览器的完整状态快照，用于后续恢复。

    Attributes:
        id: 检查点唯一标识
        url: 检查点时的页面URL
        title: 检查点时的页面标题
        storage_state: Cookie + localStorage 快照
        scroll_position: 滚动位置 {x, y}
        step_index: 保存检查点时的步骤索引
        timestamp: 检查点创建时间
        metadata: 附加元数据
    """

    id: str
    url: str
    title: str
    storage_state: Optional[dict]
    scroll_position: Optional[dict]
    step_index: int
    timestamp: datetime
    metadata: dict = field(default_factory=dict)


class CheckpointManager:
    """检查点管理器

    管理浏览器状态检查点的保存与恢复，支持：
    - 手动保存/恢复检查点
    - 最大检查点数量限制（FIFO淘汰）
    - 按步骤间隔自动保存

    使用示例::

        manager = CheckpointManager(executor, max_checkpoints=10)
        # 手动保存
        cp = await manager.save(step_index=3, metadata={"reason": "登录前"})
        # 手动恢复
        await manager.restore(cp.id)
        # 自动检查点（每5步保存一次）
        await manager.auto_checkpoint(step_index=5, interval=5)
    """

    def __init__(self, executor: BaseExecutor, max_checkpoints: int = 10) -> None:
        """初始化检查点管理器

        Args:
            executor: 执行器实例，用于获取和恢复浏览器状态
            max_checkpoints: 最大检查点数量，超出后淘汰最早的
        """
        self._executor = executor
        self._max_checkpoints = max_checkpoints
        self._checkpoints: list[Checkpoint] = []
        self._last_auto_step: int = -1

    async def save(self, step_index: int, metadata: Optional[dict] = None) -> Checkpoint:
        """保存当前浏览器状态为检查点

        捕获当前页面的URL、标题、存储状态（Cookie + localStorage）
        和滚动位置，生成检查点并存入管理器。

        Args:
            step_index: 当前步骤索引
            metadata: 附加元数据

        Returns:
            新创建的检查点对象
        """
        cp_id = uuid.uuid4().hex[:12]

        # 获取页面基本信息
        try:
            url = await self._executor.get_url()
        except Exception:
            url = ""
            logger.warning("保存检查点时获取URL失败")

        try:
            title = await self._executor.get_title()
        except Exception:
            title = ""
            logger.warning("保存检查点时获取标题失败")

        # 获取存储状态（Cookie + localStorage）
        storage_state: Optional[dict] = None
        try:
            # PlaywrightExecutor 提供 save_storage_state 方法
            if hasattr(self._executor, "context"):
                storage_state = await self._executor.context.storage_state()
        except Exception:
            logger.debug("保存检查点时获取存储状态失败，跳过")

        # 获取滚动位置
        scroll_position: Optional[dict] = None
        try:
            scroll_position = await self._executor.evaluate(
                "() => ({ x: window.scrollX, y: window.scrollY })"
            )
        except Exception:
            logger.debug("保存检查点时获取滚动位置失败，跳过")

        checkpoint = Checkpoint(
            id=cp_id,
            url=url,
            title=title,
            storage_state=storage_state,
            scroll_position=scroll_position,
            step_index=step_index,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

        self._checkpoints.append(checkpoint)

        # 超出上限时淘汰最早的检查点
        while len(self._checkpoints) > self._max_checkpoints:
            removed = self._checkpoints.pop(0)
            logger.debug("淘汰最早检查点: id=%s step=%d", removed.id, removed.step_index)

        logger.info(
            "检查点已保存: id=%s step=%d url=%s",
            checkpoint.id, step_index, url,
        )
        return checkpoint

    async def restore(self, checkpoint_id: Optional[str] = None) -> bool:
        """恢复到指定检查点

        将浏览器状态恢复到指定检查点时刻的状态，包括导航到原URL、
        恢复存储状态和滚动位置。

        Args:
            checkpoint_id: 检查点ID，为None时恢复最新的检查点

        Returns:
            是否恢复成功
        """
        checkpoint = self.get_checkpoint(checkpoint_id) if checkpoint_id else self.get_latest()
        if checkpoint is None:
            logger.warning("恢复失败：未找到检查点%s", f" id={checkpoint_id}" if checkpoint_id else "")
            return False

        try:
            # 恢复URL
            if checkpoint.url:
                await self._executor.navigate(checkpoint.url)

            # 恢复存储状态
            if checkpoint.storage_state and hasattr(self._executor, "context"):
                # 通过设置Cookie恢复
                cookies = checkpoint.storage_state.get("origins", [])
                if cookies:
                    cookie_list = checkpoint.storage_state.get("cookies", [])
                    if cookie_list:
                        await self._executor.context.add_cookies(cookie_list)

                # 恢复localStorage
                origins = checkpoint.storage_state.get("origins", [])
                for origin_data in origins:
                    origin = origin_data.get("origin", "")
                    local_storage = origin_data.get("localStorage", [])
                    for entry in local_storage:
                        try:
                            await self._executor.evaluate(
                                f"() => {{ localStorage.setItem('{entry.get('name', '')}', "
                                f"'{entry.get('value', '')}'); }}"
                            )
                        except Exception:
                            logger.debug("恢复localStorage项失败: %s", entry.get("name"))

            # 恢复滚动位置
            if checkpoint.scroll_position:
                x = checkpoint.scroll_position.get("x", 0)
                y = checkpoint.scroll_position.get("y", 0)
                try:
                    await self._executor.evaluate(f"() => window.scrollTo({x}, {y})")
                except Exception:
                    logger.debug("恢复滚动位置失败")

            logger.info(
                "检查点已恢复: id=%s step=%d url=%s",
                checkpoint.id, checkpoint.step_index, checkpoint.url,
            )
            return True

        except Exception:
            logger.exception("恢复检查点失败: id=%s", checkpoint.id)
            return False

    def get_latest(self) -> Optional[Checkpoint]:
        """获取最新的检查点

        Returns:
            最新的检查点，无检查点时返回None
        """
        if not self._checkpoints:
            return None
        return self._checkpoints[-1]

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """根据ID获取检查点

        Args:
            checkpoint_id: 检查点唯一标识

        Returns:
            匹配的检查点，未找到时返回None
        """
        for cp in self._checkpoints:
            if cp.id == checkpoint_id:
                return cp
        return None

    def list_checkpoints(self) -> list[Checkpoint]:
        """获取所有检查点列表

        Returns:
            按创建时间排序的检查点列表
        """
        return list(self._checkpoints)

    def clear(self) -> None:
        """清除所有检查点"""
        self._checkpoints.clear()
        self._last_auto_step = -1
        logger.info("所有检查点已清除")

    async def auto_checkpoint(self, step_index: int, interval: int = 5) -> Optional[Checkpoint]:
        """自动检查点 — 每隔N步自动保存

        当 step_index 与上次自动保存的步数差值达到 interval 时，
        自动保存一个检查点。

        Args:
            step_index: 当前步骤索引
            interval: 自动保存间隔（步数），默认5

        Returns:
            新创建的检查点，未触发保存时返回None
        """
        if self._last_auto_step < 0:
            # 首次调用，记录基准
            self._last_auto_step = step_index
            return None

        if step_index - self._last_auto_step >= interval:
            checkpoint = await self.save(
                step_index=step_index,
                metadata={"auto": True, "interval": interval},
            )
            self._last_auto_step = step_index
            return checkpoint

        return None
