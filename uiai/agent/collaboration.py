"""多Agent协作与人机协作模块

实现架构设计文档第21节（多Agent协作）和第26节（人机协作）：

多Agent协作（AgentCollabor）：
    - 串行协作：前一个Agent的输出作为后一个Agent的输入
    - 并行协作：多个Agent同时执行同一任务
    - 层级协作：Planner分解任务，Executors并行执行子任务

人机协作（HumanCollaboration）：
    - 人工审批：关键操作需人工确认后方可执行
    - 人工输入：Agent可向人工请求信息
    - 人工通知：Agent向人工推送非阻塞通知
    - 人工接管/释放：人工可暂停/恢复Agent循环
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uiai.agent.base import AgentOutput, BaseAgent
    from uiai.core.eventbus import Event, EventBus

logger = logging.getLogger(__name__)


# ── Agent间消息 ───────────────────────────────────────────────


@dataclass
class AgentMessage:
    """Agent间通信消息

    Attributes:
        sender: 发送Agent标识
        receiver: 接收Agent标识（"broadcast"表示广播）
        msg_type: 消息类型（task/result/error/control）
        payload: 消息内容
        priority: 优先级，数值越大越优先
        correlation_id: 关联ID，用于请求-响应匹配
        timestamp: 消息时间戳
    """

    sender: str
    receiver: str
    msg_type: str
    payload: dict
    priority: int = 0
    correlation_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# ── 协作模式 ──────────────────────────────────────────────────


class CollaborationMode(Enum):
    """协作模式枚举"""

    SERIAL = "serial"              # 串行协作
    PARALLEL = "parallel"          # 并行协作
    HIERARCHICAL = "hierarchical"  # 层级协作


# ── 多Agent协作框架 ────────────────────────────────────────────


class AgentCollabor:
    """多Agent协作框架

    提供串行、并行、层级三种协作模式，协调多个Agent共同完成任务。
    Agent间通过EventBus进行消息传递，支持广播和点对点通信。

    Args:
        event_bus: 事件总线实例，用于Agent间消息传递
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def execute_serial(
        self,
        agents: list[BaseAgent],
        task: str,
        **kwargs: Any,
    ) -> list[AgentOutput]:
        """串行执行：前一个Agent输出作为后一个输入

        执行流程：
            Agent_1(task) → Agent_2(Agent_1.output) → ... → Agent_N(Agent_{N-1}.output)

        任何Agent执行失败时，后续Agent不再执行，已执行的结果仍会返回。

        Args:
            agents: 按顺序执行的Agent列表
            task: 初始任务描述
            **kwargs: 传递给Agent的额外参数

        Returns:
            各Agent的输出列表，长度等于执行的Agent数量
        """
        results: list[AgentOutput] = []
        current_input: Any = task

        for i, agent in enumerate(agents):
            logger.info(
                "串行协作 [%d/%d]: Agent=%s 输入类型=%s",
                i + 1, len(agents), agent.name, type(current_input).__name__,
            )
            try:
                output = await agent.execute(current_input, **kwargs)
                results.append(output)

                if not output.success:
                    logger.warning(
                        "串行协作中断: Agent=%s 执行失败, message=%s",
                        agent.name, output.message,
                    )
                    break

                # 将当前Agent的输出作为下一个Agent的输入
                current_input = output.data if output.data is not None else output.message

            except Exception as e:
                logger.exception("串行协作异常: Agent=%s", agent.name)
                from uiai.agent.base import AgentOutput, AgentRole
                results.append(AgentOutput(
                    role=agent.role,
                    success=False,
                    message=str(e),
                ))
                break

        return results

    async def execute_parallel(
        self,
        agents: list[BaseAgent],
        task: str,
        **kwargs: Any,
    ) -> list[AgentOutput]:
        """并行执行：所有Agent同时执行同一任务

        所有Agent接收相同的输入，并发执行，互不依赖。
        单个Agent失败不影响其他Agent的执行。

        Args:
            agents: 并行执行的Agent列表
            task: 任务描述
            **kwargs: 传递给Agent的额外参数

        Returns:
            各Agent的输出列表，顺序与输入agents一致
        """

        async def _safe_execute(agent: BaseAgent) -> AgentOutput:
            try:
                return await agent.execute(task, **kwargs)
            except Exception as e:
                logger.exception("并行协作异常: Agent=%s", agent.name)
                from uiai.agent.base import AgentOutput
                return AgentOutput(
                    role=agent.role,
                    success=False,
                    message=str(e),
                )

        logger.info("并行协作: 启动 %d 个Agent", len(agents))
        results = await asyncio.gather(*[_safe_execute(agent) for agent in agents])
        return list(results)

    async def execute_hierarchical(
        self,
        planner: BaseAgent,
        executors: list[BaseAgent],
        task: str,
        **kwargs: Any,
    ) -> list[AgentOutput]:
        """层级执行：Planner分解任务，Executors并行执行子任务

        执行流程：
            1. Planner接收原始任务，输出分解后的子任务列表
            2. 从Planner输出中提取子任务
            3. Executors并行执行各自的子任务
            4. 收集所有Executor的输出

        Args:
            planner: 规划Agent，负责分解任务
            executors: 执行Agent列表，负责并行执行子任务
            task: 原始任务描述
            **kwargs: 传递给Agent的额外参数

        Returns:
            所有Executor的输出列表（不包含Planner的输出）
        """
        # Step 1: Planner分解任务
        logger.info("层级协作: Planner=%s 分解任务", planner.name)
        plan_output = await planner.execute(task, **kwargs)

        if not plan_output.success:
            logger.warning("层级协作: Planner执行失败, message=%s", plan_output.message)
            return [plan_output]

        # Step 2: 提取子任务
        sub_tasks = self._decompose_task(plan_output)
        if not sub_tasks:
            logger.warning("层级协作: Planner未产出有效子任务，使用原始任务")
            sub_tasks = [task]

        logger.info("层级协作: 分解为 %d 个子任务", len(sub_tasks))

        # Step 3: Executors并行执行子任务
        # 子任务数与Executor数取较小值，多余的子任务追加到最后一个Executor
        paired_tasks: list[str] = []
        for i in range(max(len(sub_tasks), len(executors))):
            task_idx = min(i, len(sub_tasks) - 1)
            paired_tasks.append(sub_tasks[task_idx])

        async def _safe_execute(agent: BaseAgent, sub_task: str) -> AgentOutput:
            try:
                return await agent.execute(sub_task, **kwargs)
            except Exception as e:
                logger.exception("层级协作: Executor=%s 执行异常", agent.name)
                from uiai.agent.base import AgentOutput
                return AgentOutput(
                    role=agent.role,
                    success=False,
                    message=str(e),
                )

        exec_coros = [
            _safe_execute(executors[i], paired_tasks[i])
            for i in range(min(len(executors), len(paired_tasks)))
        ]

        results = await asyncio.gather(*exec_coros)
        return list(results)

    def _decompose_task(self, plan_output: AgentOutput) -> list[str]:
        """从Planner输出中提取子任务列表

        支持以下格式：
            - plan_output.data 为 list[str]：直接使用
            - plan_output.data 为 str：按换行符分割
            - plan_output.message 为非空字符串：按换行符分割
            - 其他：返回空列表

        Args:
            plan_output: Planner的输出

        Returns:
            子任务描述列表
        """
        data = plan_output.data

        if isinstance(data, list):
            # 过滤空字符串
            return [str(item).strip() for item in data if str(item).strip()]

        if isinstance(data, str) and data.strip():
            return [line.strip() for line in data.strip().splitlines() if line.strip()]

        # 回退到 message 字段
        if plan_output.message and plan_output.message.strip():
            return [
                line.strip()
                for line in plan_output.message.strip().splitlines()
                if line.strip()
            ]

        return []

    async def send_message(self, message: AgentMessage) -> None:
        """通过EventBus发送Agent间消息

        将AgentMessage封装为EventBus事件并发布。
        接收方可通过订阅 "agent:message" 事件类型来接收消息。

        Args:
            message: 要发送的Agent间消息
        """
        from uiai.core.eventbus import Event

        event = Event(
            event_type="agent:message",
            source=message.sender,
            data={
                "sender": message.sender,
                "receiver": message.receiver,
                "msg_type": message.msg_type,
                "payload": message.payload,
                "priority": message.priority,
                "correlation_id": message.correlation_id,
                "timestamp": message.timestamp.isoformat(),
            },
        )
        await self._event_bus.publish(event)
        logger.debug(
            "Agent消息已发送: %s → %s, type=%s, correlation_id=%s",
            message.sender, message.receiver, message.msg_type, message.correlation_id,
        )


# ── 人机协作 ──────────────────────────────────────────────────


class ApprovalResult(Enum):
    """审批结果枚举"""

    APPROVED = "approved"       # 批准
    REJECTED = "rejected"       # 拒绝
    MODIFIED = "modified"       # 人工修改后批准


@dataclass
class HumanInput:
    """人工输入

    Attributes:
        value: 输入值
        source: 输入来源标识，默认为 "human"
    """

    value: str
    source: str = "human"


class HumanCollaboration:
    """人机协作接口

    提供人工审批、人工输入、人工通知、人工接管/释放等协作能力。
    通过EventBus发布事件并等待人工响应，实现Agent与人的异步交互。

    Args:
        event_bus: 事件总线实例，为 None 时仅记录日志不发送事件
    """

    # 人工响应事件类型前缀
    _RESPONSE_PREFIX = "human:response:"
    # 人工审批超时时间（秒）
    _APPROVAL_TIMEOUT = 300
    # 人工输入超时时间（秒）
    _INPUT_TIMEOUT = 600

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus
        self._taken_over = False
        self._pending_responses: dict[str, asyncio.Future[Any]] = {}

        # 注册人工响应监听
        if self._event_bus is not None:
            self._event_bus.subscribe(
                self._handle_human_response,
                event_type="human:response",
            )

    async def request_approval(self, action: dict, reason: str) -> ApprovalResult:
        """请求人工审批

        通过EventBus发布审批请求事件，等待人工响应。
        如果在超时时间内无人工响应，默认返回 REJECTED。

        Args:
            action: 待审批的操作描述
            reason: 请求审批的原因

        Returns:
            审批结果
        """
        correlation_id = uuid.uuid4().hex[:12]

        if self._event_bus is None:
            logger.warning("无EventBus，审批请求无法发送，默认拒绝: action=%s", action)
            return ApprovalResult.REJECTED

        # 创建等待Future
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalResult] = loop.create_future()
        self._pending_responses[correlation_id] = future  # type: ignore[assignment]

        # 发布审批请求事件
        from uiai.core.eventbus import Event

        event = Event(
            event_type="human:approval_request",
            source="human_collaboration",
            data={
                "correlation_id": correlation_id,
                "action": action,
                "reason": reason,
            },
        )
        await self._event_bus.publish(event)
        logger.info("已发送审批请求: correlation_id=%s, reason=%s", correlation_id, reason)

        # 等待人工响应
        try:
            result = await asyncio.wait_for(future, timeout=self._APPROVAL_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            logger.warning("审批请求超时，默认拒绝: correlation_id=%s", correlation_id)
            return ApprovalResult.REJECTED
        finally:
            self._pending_responses.pop(correlation_id, None)

    async def request_input(
        self,
        question: str,
        options: list[str] | None = None,
    ) -> HumanInput:
        """请求人工输入

        通过EventBus发布输入请求事件，等待人工提供信息。
        如果在超时时间内无人工响应，返回空值。

        Args:
            question: 向人工提出的问题
            options: 可选项列表（可选）

        Returns:
            人工输入结果
        """
        correlation_id = uuid.uuid4().hex[:12]

        if self._event_bus is None:
            logger.warning("无EventBus，输入请求无法发送: question=%s", question)
            return HumanInput(value="", source="timeout")

        # 创建等待Future
        loop = asyncio.get_running_loop()
        future: asyncio.Future[HumanInput] = loop.create_future()
        self._pending_responses[correlation_id] = future  # type: ignore[assignment]

        # 发布输入请求事件
        from uiai.core.eventbus import Event

        event = Event(
            event_type="human:input_request",
            source="human_collaboration",
            data={
                "correlation_id": correlation_id,
                "question": question,
                "options": options or [],
            },
        )
        await self._event_bus.publish(event)
        logger.info("已发送输入请求: correlation_id=%s, question=%s", correlation_id, question)

        # 等待人工响应
        try:
            result = await asyncio.wait_for(future, timeout=self._INPUT_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            logger.warning("输入请求超时: correlation_id=%s", correlation_id)
            return HumanInput(value="", source="timeout")
        finally:
            self._pending_responses.pop(correlation_id, None)

    async def notify(self, event: str, detail: dict) -> None:
        """通知人工（非阻塞）

        向人工推送通知信息，不等待响应。

        Args:
            event: 通知事件名称
            detail: 通知详情
        """
        if self._event_bus is None:
            logger.info("人工通知（无EventBus）: event=%s, detail=%s", event, detail)
            return

        from uiai.core.eventbus import Event as EventBusEvent

        evt = EventBusEvent(
            event_type="human:notification",
            source="human_collaboration",
            data={
                "event": event,
                "detail": detail,
            },
        )
        await self._event_bus.publish(evt)
        logger.debug("已发送人工通知: event=%s", event)

    async def takeover(self) -> None:
        """人工接管控制权

        暂停Agent循环，人工获得控制权。
        发布接管事件通知所有相关模块。
        """
        self._taken_over = True
        logger.info("人工已接管控制权")

        if self._event_bus is not None:
            from uiai.core.eventbus import Event

            event = Event(
                event_type="human:takeover",
                source="human_collaboration",
                data={"action": "takeover"},
            )
            await self._event_bus.publish(event)

    async def release(self) -> None:
        """释放控制权

        恢复Agent循环，人工交还控制权。
        发布释放事件通知所有相关模块。
        """
        self._taken_over = False
        logger.info("人工已释放控制权")

        if self._event_bus is not None:
            from uiai.core.eventbus import Event

            event = Event(
                event_type="human:release",
                source="human_collaboration",
                data={"action": "release"},
            )
            await self._event_bus.publish(event)

    @property
    def is_taken_over(self) -> bool:
        """是否已被人工接管"""
        return self._taken_over

    async def _handle_human_response(self, event: Event) -> None:
        """处理人工响应事件

        匹配 correlation_id，将响应结果设置到对应的 Future 中。

        Args:
            event: 人工响应事件
        """
        data = event.data
        correlation_id = data.get("correlation_id", "")
        if not correlation_id or correlation_id not in self._pending_responses:
            return

        future = self._pending_responses[correlation_id]
        if future.done():
            return

        response_type = data.get("response_type", "")

        if response_type == "approval":
            result_str = data.get("result", "rejected")
            try:
                approval_result = ApprovalResult(result_str)
            except ValueError:
                approval_result = ApprovalResult.REJECTED
            future.set_result(approval_result)

        elif response_type == "input":
            value = data.get("value", "")
            source = data.get("source", "human")
            future.set_result(HumanInput(value=value, source=source))

        else:
            logger.warning("未知的人工响应类型: %s", response_type)
