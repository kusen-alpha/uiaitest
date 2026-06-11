"""Agent上下文管理 - RAG知识库 + 对话历史 + 业务规则"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """对话轮次"""
    role: str  # user / assistant / system
    content: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessRule:
    """业务规则"""
    id: str
    name: str
    description: str
    domain: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = ""


class ContextManager:
    """上下文管理器

    为Agent提供：
    1. RAG知识库（业务规则、平台文档）
    2. 对话历史管理
    3. 上下文窗口控制（token预算）
    """

    def __init__(self, max_history: int = 20, max_context_tokens: int = 8000):
        self._history: list[ConversationTurn] = []
        self._knowledge_base: list[BusinessRule] = []
        self._max_history = max_history
        self._max_context_tokens = max_context_tokens

    # --- 对话历史 ---

    def add_turn(self, role: str, content: str, **metadata) -> None:
        """添加对话轮次"""
        from datetime import datetime
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
        )
        self._history.append(turn)
        # 保留最近N轮
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, last_n: int | None = None) -> list[ConversationTurn]:
        """获取对话历史"""
        if last_n:
            return self._history[-last_n:]
        return self._history.copy()

    def get_history_as_messages(self, last_n: int | None = None) -> list[dict]:
        """获取对话历史（格式化为LLM消息格式）"""
        turns = self.get_history(last_n)
        return [{"role": t.role, "content": t.content} for t in turns]

    def clear_history(self) -> None:
        """清除对话历史"""
        self._history.clear()

    # --- RAG知识库 ---

    def add_rule(self, rule: BusinessRule) -> None:
        """添加业务规则"""
        self._knowledge_base.append(rule)
        logger.debug(f"Business rule added: {rule.id} - {rule.name}")

    def add_rules_from_dict(self, rules_data: list[dict]) -> None:
        """从字典列表添加业务规则"""
        for rd in rules_data:
            rule = BusinessRule(
                id=rd.get("id", ""),
                name=rd.get("name", ""),
                description=rd.get("description", ""),
                domain=rd.get("domain", ""),
                tags=rd.get("tags", []),
                source=rd.get("source", ""),
            )
            self.add_rule(rule)

    def load_rules_from_file(self, path: str | Path) -> None:
        """从JSON文件加载业务规则"""
        path = Path(path)
        if not path.exists():
            logger.warning(f"Rules file not found: {path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            self.add_rules_from_dict(data)
        elif isinstance(data, dict) and "rules" in data:
            self.add_rules_from_dict(data["rules"])

        logger.info(f"Loaded {len(self._knowledge_base)} rules from {path}")

    def search_rules(self, query: str, domain: str | None = None, tags: list[str] | None = None) -> list[BusinessRule]:
        """搜索业务规则（简单关键词匹配）"""
        results = []
        query_lower = query.lower()
        for rule in self._knowledge_base:
            # 关键词匹配
            if query_lower in rule.description.lower() or query_lower in rule.name.lower():
                if domain and rule.domain != domain:
                    continue
                if tags and not any(t in rule.tags for t in tags):
                    continue
                results.append(rule)
        return results

    def get_relevant_context(self, query: str, max_rules: int = 5) -> str:
        """获取与查询相关的上下文文本"""
        rules = self.search_rules(query)[:max_rules]
        if not rules:
            return ""

        context_parts = ["## 相关业务规则\n"]
        for rule in rules:
            context_parts.append(f"- **{rule.name}** ({rule.id}): {rule.description}")
            if rule.domain:
                context_parts.append(f"  领域: {rule.domain}")

        return "\n".join(context_parts)

    @property
    def rule_count(self) -> int:
        return len(self._knowledge_base)

    # --- 上下文窗口控制 ---

    def build_context_messages(self, system_prompt: str, user_query: str,
                               include_history: bool = True, include_rag: bool = True) -> list[dict]:
        """构建完整的上下文消息列表

        在token预算内组装：系统提示 + RAG上下文 + 对话历史 + 用户查询
        """
        messages = []

        # 1. 系统提示
        system_content = system_prompt

        # 2. RAG上下文
        if include_rag:
            rag_context = self.get_relevant_context(user_query)
            if rag_context:
                system_content += f"\n\n{rag_context}"

        messages.append({"role": "system", "content": system_content})

        # 3. 对话历史（在token预算内）
        if include_history and self._history:
            # 估算token（简单：4字符=1token）
            system_tokens = len(system_content) // 4
            query_tokens = len(user_query) // 4
            remaining_tokens = self._max_context_tokens - system_tokens - query_tokens - 500  # 留500余量

            history_messages = []
            for turn in reversed(self._history):
                turn_tokens = len(turn.content) // 4
                if remaining_tokens - turn_tokens < 0:
                    break
                history_messages.insert(0, {"role": turn.role, "content": turn.content})
                remaining_tokens -= turn_tokens

            messages.extend(history_messages)

        # 4. 用户查询
        messages.append({"role": "user", "content": user_query})

        return messages
