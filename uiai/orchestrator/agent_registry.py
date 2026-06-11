"""Agent注册中心 - 管理所有Agent实例"""
from __future__ import annotations
import logging
from typing import Optional

from uiai.agent.base import BaseAgent, AgentRole

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent注册中心

    管理所有Agent实例的注册、查询和生命周期。
    """

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._role_map: dict[AgentRole, list[str]] = {}

    def register(self, agent: BaseAgent) -> None:
        """注册Agent"""
        self._agents[agent.name] = agent
        if agent.role not in self._role_map:
            self._role_map[agent.role] = []
        self._role_map[agent.role].append(agent.name)
        logger.debug(f"Registered agent: {agent.name} (role={agent.role.value})")

    def get(self, name: str) -> BaseAgent | None:
        """按名称获取Agent"""
        return self._agents.get(name)

    def get_by_role(self, role: AgentRole) -> list[BaseAgent]:
        """按角色获取Agent列表"""
        names = self._role_map.get(role, [])
        return [self._agents[n] for n in names if n in self._agents]

    def get_first_by_role(self, role: AgentRole) -> BaseAgent | None:
        """按角色获取第一个Agent"""
        agents = self.get_by_role(role)
        return agents[0] if agents else None

    def list_all(self) -> list[BaseAgent]:
        """列出所有Agent"""
        return list(self._agents.values())

    def unregister(self, name: str) -> None:
        """注销Agent"""
        if name in self._agents:
            agent = self._agents.pop(name)
            if agent.role in self._role_map:
                self._role_map[agent.role] = [
                    n for n in self._role_map[agent.role] if n != name
                ]

    def __len__(self) -> int:
        return len(self._agents)
