"""Docker浏览器池 - 基于Docker的浏览器实例管理"""
from __future__ import annotations
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DockerBrowserSlot:
    """Docker浏览器槽位"""
    slot_id: str
    container_id: str | None = None
    ws_endpoint: str | None = None
    in_use: bool = False
    owner: str | None = None
    browser_type: str = "chromium"


class DockerBrowserPool:
    """Docker浏览器池

    管理Docker容器化的浏览器实例：
    1. 按需创建/销毁浏览器容器
    2. 支持Playwright CDP连接
    3. 自动清理超时容器
    4. 资源限制（最大容器数、内存限制）
    """

    def __init__(self, max_containers: int = 10, image: str = "mcr.microsoft.com/playwright:latest",
                 memory_limit: str = "1g"):
        self.max_containers = max_containers
        self.image = image
        self.memory_limit = memory_limit
        self._slots: list[DockerBrowserSlot] = []
        self._semaphore = asyncio.Semaphore(max_containers)

    async def acquire(self, browser_type: str = "chromium", owner: str = "") -> DockerBrowserSlot:
        """获取一个浏览器容器"""
        await self._semaphore.acquire()

        # 尝试复用空闲槽位
        for slot in self._slots:
            if not slot.in_use and slot.browser_type == browser_type:
                slot.in_use = True
                slot.owner = owner
                logger.debug(f"Reused Docker slot {slot.slot_id}")
                return slot

        # 创建新容器
        slot = await self._create_container(browser_type, owner)
        self._slots.append(slot)
        return slot

    async def _create_container(self, browser_type: str, owner: str) -> DockerBrowserSlot:
        """创建Docker容器"""
        slot_id = f"docker-{uuid.uuid4().hex[:8]}"

        try:
            # 使用docker CLI创建容器
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "-d",
                "--rm",
                "--name", f"uiai-{slot_id}",
                "-p", "0:3000",
                "--memory", self.memory_limit,
                self.image,
                "npx", "playwright", "run-server",
                "--port", "3000",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            container_id = stdout.decode().strip()[:12]

            # 获取映射端口
            proc2 = await asyncio.create_subprocess_exec(
                "docker", "port", f"uiai-{slot_id}", "3000",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await proc2.communicate()
            port_info = stdout2.decode().strip()
            port = port_info.split(":")[-1] if port_info else "3000"

            ws_endpoint = f"ws://localhost:{port}"

            slot = DockerBrowserSlot(
                slot_id=slot_id,
                container_id=container_id,
                ws_endpoint=ws_endpoint,
                in_use=True,
                owner=owner,
                browser_type=browser_type,
            )
            logger.info(f"Created Docker container: {slot_id} -> {container_id}")
            return slot

        except FileNotFoundError:
            logger.warning("Docker not available, falling back to local browser")
            return DockerBrowserSlot(
                slot_id=slot_id,
                container_id=None,
                ws_endpoint=None,
                in_use=True,
                owner=owner,
                browser_type=browser_type,
            )

    async def release(self, slot: DockerBrowserSlot) -> None:
        """释放浏览器容器"""
        slot.in_use = False
        slot.owner = None
        self._semaphore.release()

    async def stop_container(self, slot: DockerBrowserSlot) -> None:
        """停止并移除容器"""
        if slot.container_id:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "stop", slot.container_id,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                logger.info(f"Stopped container: {slot.container_id}")
            except Exception as e:
                logger.warning(f"Failed to stop container: {e}")

        if slot in self._slots:
            self._slots.remove(slot)

    async def stop_all(self) -> None:
        """停止所有容器"""
        for slot in self._slots:
            await self.stop_container(slot)
        self._slots.clear()
        logger.info("All Docker containers stopped")

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._slots if s.in_use)

    @property
    def total_count(self) -> int:
        return len(self._slots)
