"""浏览器资源池 - 管理Playwright浏览器实例的创建和复用"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from uiai.config import BrowserConfig

logger = logging.getLogger(__name__)


@dataclass
class BrowserSlot:
    """浏览器槽位"""
    slot_id: str
    executor: any  # PlaywrightExecutor
    in_use: bool = False
    owner: str | None = None


class BrowserPool:
    """浏览器资源池

    管理Playwright浏览器实例的创建、分配和回收。
    支持并发限流和资源隔离。
    """

    def __init__(self, max_size: int = 5, config: BrowserConfig | None = None):
        self.max_size = max_size
        self.config = config or BrowserConfig()
        self._pool: list[BrowserSlot] = []
        self._semaphore = asyncio.Semaphore(max_size)
        self._lock = asyncio.Lock()

    async def acquire(self, owner: str = "") -> any:
        """获取一个浏览器实例

        Args:
            owner: 占用者标识

        Returns:
            PlaywrightExecutor实例
        """
        await self._semaphore.acquire()

        async with self._lock:
            # 尝试复用空闲实例
            for slot in self._pool:
                if not slot.in_use:
                    slot.in_use = True
                    slot.owner = owner
                    logger.debug(f"Browser slot {slot.slot_id} reused by {owner}")
                    return slot.executor

            # 创建新实例
            from uiai.executor.playwright_executor import PlaywrightExecutor
            executor = PlaywrightExecutor(config=self.config)
            await executor.start()

            slot_id = f"browser-{len(self._pool)}"
            slot = BrowserSlot(slot_id=slot_id, executor=executor, in_use=True, owner=owner)
            self._pool.append(slot)
            logger.info(f"Browser slot {slot_id} created for {owner}")
            return executor

    async def release(self, executor: any) -> None:
        """释放浏览器实例（归还池中，不关闭）"""
        async with self._lock:
            for slot in self._pool:
                if slot.executor is executor:
                    slot.in_use = False
                    slot.owner = None
                    logger.debug(f"Browser slot {slot.slot_id} released")
                    self._semaphore.release()
                    return

    async def close_all(self) -> None:
        """关闭所有浏览器实例"""
        async with self._lock:
            for slot in self._pool:
                try:
                    await slot.executor.stop()
                except Exception as e:
                    logger.warning(f"Error closing browser slot {slot.slot_id}: {e}")
            self._pool.clear()
            logger.info("All browser instances closed")

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._pool if s.in_use)

    @property
    def total_count(self) -> int:
        return len(self._pool)
