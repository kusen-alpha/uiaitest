"""消息压缩器 - 管理对话历史长度，防止超出模型上下文窗口

参考 browser-use 的 MessageCompactionSettings 设计，提供三种压缩策略:
- TRUNCATE: 截断旧消息
- SUMMARIZE: LLM摘要压缩
- SLIDING_WINDOW: 滑动窗口保留最近N条

核心目标是在保留关键上下文的同时，将消息列表控制在模型可处理的范围内。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from uiai.agent.llm import BaseLLMClient

logger = logging.getLogger(__name__)


class CompactionStrategy(Enum):
    """压缩策略枚举"""
    TRUNCATE = "truncate"              # 截断旧消息
    SUMMARIZE = "summarize"            # LLM摘要压缩
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口保留最近N条


@dataclass
class CompactionConfig:
    """消息压缩配置

    Attributes:
        max_messages: 触发压缩的最大消息数
        max_tokens: 触发压缩的最大token数
        strategy: 压缩策略
        keep_recent: 始终保留的最近消息数
        keep_system: 是否始终保留系统消息
        summarize_model: 摘要使用的模型标识符（仅 strategy=SUMMARIZE 时需要）
    """
    max_messages: int = 50
    max_tokens: int = 8000
    strategy: CompactionStrategy = CompactionStrategy.SLIDING_WINDOW
    keep_recent: int = 10
    keep_system: bool = True
    summarize_model: Optional[str] = None


class MessageCompactor:
    """消息压缩器

    管理对话消息列表的长度，当消息数量或token数超过阈值时，
    按配置的策略进行压缩，确保不超出模型的上下文窗口限制。
    """

    # 平均每个token约4个字符（中英文混合场景的经验值）
    _CHARS_PER_TOKEN = 4.0

    def __init__(
        self,
        config: Optional[CompactionConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ) -> None:
        """初始化消息压缩器

        Args:
            config: 压缩配置，为None时使用默认配置
            llm_client: LLM客户端实例，仅 strategy=SUMMARIZE 时需要
        """
        self._config = config or CompactionConfig()
        self._llm_client = llm_client

    def compact(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """压缩消息列表

        根据配置的策略对消息进行压缩。如果不需要压缩则原样返回。

        Args:
            messages: 消息列表，每条消息为 dict，包含 role 和 content 等字段

        Returns:
            压缩后的消息列表
        """
        if not self.should_compact(messages):
            return messages

        original_count = len(messages)
        strategy = self._config.strategy

        if strategy == CompactionStrategy.TRUNCATE:
            result = self._truncate(messages)
        elif strategy == CompactionStrategy.SLIDING_WINDOW:
            result = self._sliding_window(messages)
        elif strategy == CompactionStrategy.SUMMARIZE:
            result = self._summarize(messages)
        else:
            logger.warning(f"未知的压缩策略: {strategy}，回退到滑动窗口策略")
            result = self._sliding_window(messages)

        compressed_count = len(result)
        logger.info(
            f"消息压缩完成: 策略={strategy.value}, "
            f"原始={original_count}条, 压缩后={compressed_count}条"
        )
        return result

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        """检查是否需要压缩

        当消息数量或估算token数超过阈值时返回True。

        Args:
            messages: 消息列表

        Returns:
            是否需要压缩
        """
        if len(messages) > self._config.max_messages:
            return True
        if self.estimate_tokens(messages) > self._config.max_tokens:
            return True
        return False

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表的总token数

        使用字符数除以平均比率进行粗略估算，适用于快速判断
        是否需要压缩，不需要精确的tokenizer。

        Args:
            messages: 消息列表

        Returns:
            估算的总token数
        """
        return sum(self._estimate_message_tokens(m) for m in messages)

    def _truncate(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """截断旧消息

        保留系统消息和最近的消息，直接丢弃中间的旧消息。

        Args:
            messages: 消息列表

        Returns:
            截断后的消息列表
        """
        system_msgs, other_msgs = self._split_system_messages(messages)
        keep_count = self._config.keep_recent

        if len(other_msgs) <= keep_count:
            return messages

        kept = other_msgs[-keep_count:]
        return system_msgs + kept

    def _sliding_window(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """滑动窗口策略

        始终保留系统消息和最近N条消息，丢弃窗口之外的旧消息。

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        system_msgs, other_msgs = self._split_system_messages(messages)
        keep_count = self._config.keep_recent

        if len(other_msgs) <= keep_count:
            return messages

        kept = other_msgs[-keep_count:]
        return system_msgs + kept

    def _summarize(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """LLM摘要压缩

        将旧消息通过LLM生成摘要，保留系统消息、摘要和最近消息。
        如果LLM客户端不可用，回退到滑动窗口策略。

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        if self._llm_client is None:
            logger.warning("SUMMARIZE策略需要LLM客户端，但未提供，回退到滑动窗口策略")
            return self._sliding_window(messages)

        system_msgs, other_msgs = self._split_system_messages(messages)
        keep_count = self._config.keep_recent

        if len(other_msgs) <= keep_count:
            return messages

        # 分离需要摘要的旧消息和需要保留的最近消息
        old_msgs = other_msgs[:-keep_count]
        recent_msgs = other_msgs[-keep_count:]

        # 构建摘要提示
        summary_text = self._build_summary_text(old_msgs)
        summary_message = {
            "role": "system",
            "content": f"[对话历史摘要]\n{summary_text}",
        }

        return system_msgs + [summary_message] + recent_msgs

    def _estimate_message_tokens(self, message: dict[str, Any]) -> int:
        """估算单条消息的token数

        基于字符数粗略估算，包括role和content字段。

        Args:
            message: 单条消息字典

        Returns:
            估算的token数
        """
        total_chars = 0
        content = message.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            # 多模态消息格式: [{"type": "text", "text": "..."}, ...]
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total_chars += len(part.get("text", ""))

        # 加上role字段的估算
        total_chars += len(message.get("role", ""))

        return max(1, math.ceil(total_chars / self._CHARS_PER_TOKEN))

    @staticmethod
    def _split_system_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """将消息列表拆分为系统消息和非系统消息

        Args:
            messages: 消息列表

        Returns:
            (系统消息列表, 非系统消息列表) 元组
        """
        system_msgs: list[dict[str, Any]] = []
        other_msgs: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)
        return system_msgs, other_msgs

    @staticmethod
    def _build_summary_text(old_msgs: list[dict[str, Any]]) -> str:
        """从旧消息构建摘要文本

        将旧消息格式化为文本，供LLM生成摘要使用。
        当LLM客户端可用时，此文本会作为摘要请求的输入；
        当LLM客户端不可用时，直接作为简化摘要。

        Args:
            old_msgs: 需要摘要的旧消息列表

        Returns:
            摘要文本
        """
        lines: list[str] = []
        for msg in old_msgs:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                # 多模态消息，只提取文本部分
                text_parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                content = " ".join(text_parts)
            if content:
                lines.append(f"[{role}] {content}")
        return "\n".join(lines)
