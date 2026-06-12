"""Agent基类 - 定义Agent统一接口和协作模式"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Agent角色"""
    PLANNER = "planner"
    GENERATOR = "generator"
    HEALER = "healer"
    EXPLORER = "explorer"
    EXECUTOR = "executor"
    JUDGE = "judge"
    RECORDER = "recorder"


class AgentState(Enum):
    """Agent状态"""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentOutput:
    """Agent输出"""
    role: AgentRole
    success: bool
    data: Any = None
    message: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)  # 产出文件路径
    requires_approval: bool = False
    approval_data: Any = None  # 需要审核的数据


class BaseAgent(ABC):
    """Agent基类

    所有Agent（Planner/Generator/Healer/Explorer）都继承此类。
    Agent间通过文件系统（Markdown/代码文件）+ 消息传递进行协作。
    """

    def __init__(self, name: str, role: AgentRole, llm_client=None):
        self.name = name
        self.role = role
        self.state = AgentState.IDLE
        self.llm_client = llm_client
        self._history: list[dict] = []

    @abstractmethod
    async def run(self, input_data: Any, **kwargs) -> AgentOutput:
        """执行Agent任务"""

    async def execute(self, input_data: Any, **kwargs) -> AgentOutput:
        """执行入口（带状态管理）"""
        self.state = AgentState.RUNNING
        self._history.append({"input": input_data, "state": "running"})
        try:
            output = await self.run(input_data, **kwargs)
            self.state = AgentState.COMPLETED if output.success else AgentState.FAILED
            if output.requires_approval:
                self.state = AgentState.WAITING_APPROVAL
            self._history.append({"output": output, "state": self.state.value})
            return output
        except Exception as e:
            self.state = AgentState.FAILED
            logger.error(f"Agent {self.name} failed: {e}")
            return AgentOutput(
                role=self.role,
                success=False,
                message=str(e),
            )

    def approve(self, approved: bool = True) -> None:
        """审批Agent输出"""
        if self.state == AgentState.WAITING_APPROVAL:
            self.state = AgentState.COMPLETED if approved else AgentState.FAILED

    @property
    def is_idle(self) -> bool:
        return self.state == AgentState.IDLE

    @property
    def is_running(self) -> bool:
        return self.state == AgentState.RUNNING
