"""多模型意图路由器 - 根据意图类型智能路由到最合适的模型

参考 Midscene.js 的 Intent Routing 设计，将不同类型的任务路由到
最合适的模型，实现成本与性能的最优平衡。

意图类型与模型映射:
- LOCATE (元素定位) → VL模型（视觉语言模型）
- PLAN (任务规划) → 强LLM
- EXTRACT (信息提取) → 轻量模型
- ASSERT (视觉断言) → VL模型
- EXPLORE (页面探索) → LLM
- HEAL (自愈修复) → LLM
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from uiai.agent.llm import BaseLLMClient

from uiai.agent.llm import create_llm_client
from uiai.config import LLMConfig

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """意图类型枚举"""
    LOCATE = "locate"      # 元素定位 → VL模型
    PLAN = "plan"          # 任务规划 → LLM
    EXTRACT = "extract"    # 信息提取 → 轻量模型
    ASSERT = "assert"      # 视觉断言 → VL模型
    EXPLORE = "explore"    # 页面探索 → LLM
    HEAL = "heal"          # 自愈修复 → LLM


@dataclass(frozen=True)
class ModelConfig:
    """模型配置

    Attributes:
        model_id: 模型标识符（如 "qwen-plus", "ui-tars-7b"）
        provider: 提供商名称（如 "dashscope", "ollama", "openai"）
        capabilities: 该模型可处理的意图类型集合
        priority: 优先级，数值越低优先级越高（默认50）
        max_tokens: 最大输出token数
        cost_per_1k: 每千token成本（用于成本优化）
        is_vl: 是否为视觉语言模型
    """
    model_id: str
    provider: str
    capabilities: frozenset[IntentType] = field(default_factory=frozenset)
    priority: int = 50
    max_tokens: int = 4096
    cost_per_1k: float = 0.0
    is_vl: bool = False

    def __hash__(self) -> int:
        return hash(self.model_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModelConfig):
            return NotImplemented
        return self.model_id == other.model_id


class IntentRouter:
    """多模型意图路由器

    根据意图类型将请求路由到最合适的模型，支持优先级排序、
    VL偏好、成本优化和降级回退策略。
    """

    def __init__(self, llm_configs: Optional[dict[str, ModelConfig]] = None) -> None:
        """初始化意图路由器

        Args:
            llm_configs: 预注册的模型配置字典，key为model_id
        """
        self._models: dict[str, ModelConfig] = {}
        if llm_configs:
            for model_id, config in llm_configs.items():
                self._models[model_id] = config

    def register_model(self, config: ModelConfig) -> None:
        """注册模型

        Args:
            config: 模型配置
        """
        self._models[config.model_id] = config
        logger.info(f"已注册模型: {config.model_id} (provider={config.provider}, "
                     f"capabilities={[c.value for c in config.capabilities]}, "
                     f"priority={config.priority}, is_vl={config.is_vl})")

    def route(
        self,
        intent: IntentType,
        prefer_vl: bool = False,
        prefer_cheapest: bool = False,
    ) -> ModelConfig:
        """将意图路由到最佳模型

        按以下规则选择模型:
        1. 筛选支持该意图的所有模型
        2. 若 prefer_vl=True，优先选择VL模型
        3. 若 prefer_cheapest=True，按成本升序排列
        4. 否则按优先级排序（priority越小越优先）

        Args:
            intent: 意图类型
            prefer_vl: 是否偏好VL模型
            prefer_cheapest: 是否偏好最便宜的模型

        Returns:
            最佳模型配置

        Raises:
            ValueError: 没有模型能处理该意图
        """
        candidates = self._get_candidates(intent)
        if not candidates:
            raise ValueError(
                f"没有已注册的模型能处理意图 '{intent.value}'，"
                f"请先注册支持该意图的模型"
            )

        sorted_candidates = self._sort_candidates(
            candidates, prefer_vl=prefer_vl, prefer_cheapest=prefer_cheapest
        )
        best = sorted_candidates[0]
        logger.debug(f"意图 '{intent.value}' 路由到模型: {best.model_id}")
        return best

    def route_with_fallback(self, intent: IntentType) -> list[ModelConfig]:
        """获取有序模型列表（主模型 + 降级回退模型）

        按优先级排序返回所有支持该意图的模型，当主模型不可用时可依次降级。

        Args:
            intent: 意图类型

        Returns:
            按优先级排序的模型配置列表
        """
        candidates = self._get_candidates(intent)
        if not candidates:
            raise ValueError(
                f"没有已注册的模型能处理意图 '{intent.value}'，"
                f"请先注册支持该意图的模型"
            )
        return self._sort_candidates(candidates)

    def get_model_for_locate(self) -> ModelConfig:
        """快捷方法: 获取元素定位最佳模型（偏好VL模型）

        Returns:
            适合元素定位的模型配置
        """
        return self.route(IntentType.LOCATE, prefer_vl=True)

    def get_model_for_plan(self) -> ModelConfig:
        """快捷方法: 获取任务规划最佳模型（强LLM优先）

        Returns:
            适合任务规划的模型配置
        """
        return self.route(IntentType.PLAN)

    def get_model_for_extract(self) -> ModelConfig:
        """快捷方法: 获取信息提取最佳模型（最便宜的模型）

        Returns:
            适合信息提取的模型配置
        """
        return self.route(IntentType.EXTRACT, prefer_cheapest=True)

    def create_client(self, config: ModelConfig) -> BaseLLMClient:
        """为模型配置创建LLM客户端

        Args:
            config: 模型配置

        Returns:
            LLM客户端实例
        """
        llm_config = LLMConfig(
            provider=config.provider,
            model=config.model_id,
            max_tokens=config.max_tokens,
            vl_model=config.model_id if config.is_vl else "",
        )
        return create_llm_client(llm_config)

    def list_models(self) -> list[ModelConfig]:
        """列出所有已注册的模型

        Returns:
            模型配置列表
        """
        return list(self._models.values())

    def set_default_models(self) -> None:
        """设置默认模型配置

        默认模型:
        - ui-tars-7b: LOCATE, ASSERT（VL模型，优先级10）
        - qwen-plus: PLAN, EXPLORE, HEAL（LLM，优先级20）
        - qwen-turbo: EXTRACT（轻量模型，优先级30，最便宜）
        """
        defaults = [
            ModelConfig(
                model_id="ui-tars-7b",
                provider="dashscope",
                capabilities=frozenset({IntentType.LOCATE, IntentType.ASSERT}),
                priority=10,
                max_tokens=2048,
                cost_per_1k=0.008,
                is_vl=True,
            ),
            ModelConfig(
                model_id="qwen-plus",
                provider="dashscope",
                capabilities=frozenset({IntentType.PLAN, IntentType.EXPLORE, IntentType.HEAL}),
                priority=20,
                max_tokens=8192,
                cost_per_1k=0.004,
                is_vl=False,
            ),
            ModelConfig(
                model_id="qwen-turbo",
                provider="dashscope",
                capabilities=frozenset({IntentType.EXTRACT}),
                priority=30,
                max_tokens=4096,
                cost_per_1k=0.002,
                is_vl=False,
            ),
        ]
        for config in defaults:
            self.register_model(config)
        logger.info("已设置默认模型配置")

    def _get_candidates(self, intent: IntentType) -> list[ModelConfig]:
        """获取支持指定意图的模型列表"""
        return [
            m for m in self._models.values()
            if intent in m.capabilities
        ]

    @staticmethod
    def _sort_candidates(
        candidates: list[ModelConfig],
        prefer_vl: bool = False,
        prefer_cheapest: bool = False,
    ) -> list[ModelConfig]:
        """对候选模型排序

        排序规则:
        1. 若 prefer_vl=True，VL模型排在前面
        2. 若 prefer_cheapest=True，按成本升序
        3. 按优先级升序（priority越小越优先）
        """
        def sort_key(config: ModelConfig) -> tuple:
            vl_priority = 0 if (prefer_vl and config.is_vl) else 1
            cost = config.cost_per_1k if prefer_cheapest else 0.0
            return (vl_priority, cost, config.priority)

        return sorted(candidates, key=sort_key)
