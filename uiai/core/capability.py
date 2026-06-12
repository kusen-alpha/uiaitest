"""能力系统定义

参考 playwright-mcp 的 Capability 系统设计，
提供能力组枚举、能力配置与能力管理器，
支持按需启用/禁用能力组及限制特定操作。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Capability(Enum):
    """能力组枚举

    每个 Capability 代表一组相关功能的集合，
    可独立启用或禁用，实现细粒度的权限控制。
    """
    BROWSER_CONTROL = "browser_control"        # 导航、标签页、历史记录
    ELEMENT_INTERACTION = "element_interaction"  # 点击、输入、填充、选择
    VISUAL_PERCEPTION = "visual_perception"     # 截图、视觉定位、无障碍快照
    NETWORK_CONTROL = "network_control"         # 拦截、模拟、屏蔽资源
    FILE_OPERATION = "file_operation"           # 下载、上传
    COOKIE_STORAGE = "cookie_storage"           # Cookie、localStorage、存储状态
    ASSERTION = "assertion"                     # 视觉、文本、语义断言
    HEALING = "healing"                         # 自愈、回退策略
    AI_AGENT = "ai_agent"                       # LLM 调用、Agent 循环
    CODE_GENERATION = "code_generation"         # 代码录制、代码生成
    KNOWLEDGE = "knowledge"                     # 知识库、RAG
    DISTRIBUTED = "distributed"                 # 分布式执行、Worker 管理


@dataclass
class CapabilityConfig:
    """能力配置

    管理能力组的启用状态及操作级别的限制。
    默认启用所有能力组。
    """
    enabled_capabilities: set[Capability] = field(
        default_factory=lambda: set(Capability)
    )
    restricted_actions: dict[Capability, list[str]] = field(
        default_factory=dict
    )


class CapabilityManager:
    """能力管理器

    提供能力组的启用/禁用、操作级别的限制检查，
    以及预设配置的创建。
    """

    # 预设配置定义
    _PRESETS: dict[str, set[Capability]] = {
        "full": set(Capability),
        "safe": {
            Capability.BROWSER_CONTROL,
            Capability.ELEMENT_INTERACTION,
            Capability.VISUAL_PERCEPTION,
            Capability.NETWORK_CONTROL,
            Capability.FILE_OPERATION,
            Capability.COOKIE_STORAGE,
            Capability.ASSERTION,
            Capability.HEALING,
            Capability.KNOWLEDGE,
        },
        "local_dev": {
            Capability.BROWSER_CONTROL,
            Capability.ELEMENT_INTERACTION,
            Capability.VISUAL_PERCEPTION,
            Capability.ASSERTION,
            Capability.AI_AGENT,
        },
        "ci": set(Capability) - {Capability.DISTRIBUTED, Capability.KNOWLEDGE},
        "readonly": {
            Capability.VISUAL_PERCEPTION,
            Capability.ASSERTION,
            Capability.KNOWLEDGE,
        },
    }

    def __init__(self, config: Optional[CapabilityConfig] = None) -> None:
        """初始化能力管理器

        Args:
            config: 能力配置，为 None 时使用默认配置（全部启用）
        """
        self._config = config if config is not None else CapabilityConfig()

    def enable(self, capability: Capability) -> None:
        """启用指定能力组

        Args:
            capability: 要启用的能力组
        """
        self._config.enabled_capabilities.add(capability)

    def disable(self, capability: Capability) -> None:
        """禁用指定能力组

        Args:
            capability: 要禁用的能力组
        """
        self._config.enabled_capabilities.discard(capability)

    def is_enabled(self, capability: Capability) -> bool:
        """检查指定能力组是否已启用

        Args:
            capability: 要检查的能力组

        Returns:
            是否已启用
        """
        return capability in self._config.enabled_capabilities

    def restrict_action(self, capability: Capability, action: str) -> None:
        """限制指定能力组内的特定操作

        Args:
            capability: 操作所属的能力组
            action: 要限制的操作名称
        """
        if capability not in self._config.restricted_actions:
            self._config.restricted_actions[capability] = []
        if action not in self._config.restricted_actions[capability]:
            self._config.restricted_actions[capability].append(action)

    def is_action_allowed(self, capability: Capability, action: str) -> bool:
        """检查指定操作是否被允许

        需同时满足：能力组已启用且操作未被限制。

        Args:
            capability: 操作所属的能力组
            action: 操作名称

        Returns:
            操作是否被允许
        """
        if not self.is_enabled(capability):
            return False
        restricted = self._config.restricted_actions.get(capability, [])
        return action not in restricted

    def get_enabled_capabilities(self) -> set[Capability]:
        """获取所有已启用的能力组

        Returns:
            已启用的能力组集合
        """
        return set(self._config.enabled_capabilities)

    def get_disabled_capabilities(self) -> set[Capability]:
        """获取所有已禁用的能力组

        Returns:
            已禁用的能力组集合
        """
        return set(Capability) - self._config.enabled_capabilities

    def create_preset(self, preset_name: str) -> CapabilityConfig:
        """创建预设能力配置

        支持的预设：
        - "full": 全部能力启用
        - "safe": 排除 AI_AGENT、CODE_GENERATION、DISTRIBUTED
        - "local_dev": BROWSER_CONTROL + ELEMENT_INTERACTION + VISUAL_PERCEPTION + ASSERTION + AI_AGENT
        - "ci": 排除 DISTRIBUTED 和 KNOWLEDGE
        - "readonly": 仅 VISUAL_PERCEPTION + ASSERTION + KNOWLEDGE

        Args:
            preset_name: 预设名称

        Returns:
            对应的 CapabilityConfig 实例

        Raises:
            ValueError: 当预设名称不存在时
        """
        if preset_name not in self._PRESETS:
            available = ", ".join(self._PRESETS.keys())
            raise ValueError(f"未知预设 '{preset_name}'，可用预设: {available}")
        return CapabilityConfig(enabled_capabilities=set(self._PRESETS[preset_name]))
