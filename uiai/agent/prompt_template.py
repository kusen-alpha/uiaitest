"""提示词模板管理器。

根据架构设计文档 23.3 节，提供不同推理模式下的系统提示词模板管理，
支持模板注册、渲染和列表查询。
"""

from dataclasses import dataclass, field
from enum import Enum


class PromptMode(Enum):
    """提示词模式枚举。"""

    STANDARD = "standard"
    FLASH = "flash"
    VISUAL = "visual"
    NO_THINKING = "no_thinking"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass
class SystemPrompt:
    """系统提示词模板数据类。

    Attributes:
        template: 包含 {placeholders} 占位符的模板字符串
        mode: 提示词模式
        description: 模板描述
        required_fields: 必需的占位符字段列表
    """

    template: str
    mode: PromptMode
    description: str
    required_fields: list[str] = field(default_factory=list)


class PromptTemplateManager:
    """提示词模板管理器。

    管理不同推理模式下的系统提示词模板，支持默认模板注册、
    自定义模板扩展以及模板变量渲染。
    """

    def __init__(self) -> None:
        """初始化模板管理器并注册默认模板。"""
        self._templates: dict[str, SystemPrompt] = {}
        self._register_defaults()

    def get_template(self, mode: PromptMode) -> SystemPrompt:
        """根据模式获取模板。

        Args:
            mode: 提示词模式

        Returns:
            对应模式的 SystemPrompt 实例

        Raises:
            KeyError: 当指定模式未注册时
        """
        name = mode.value
        if name not in self._templates:
            raise KeyError(f"未注册的模板模式: {mode.value}")
        return self._templates[name]

    def register_template(self, name: str, template: SystemPrompt) -> None:
        """注册自定义模板。

        若模板名称已存在则覆盖。

        Args:
            name: 模板名称，用作唯一标识
            template: SystemPrompt 实例
        """
        self._templates[name] = template

    def render(self, mode: PromptMode, **kwargs: str) -> str:
        """使用给定变量渲染模板。

        Args:
            mode: 提示词模式
            **kwargs: 模板占位符对应的变量值

        Returns:
            渲染后的提示词字符串

        Raises:
            KeyError: 当指定模式未注册时
            ValueError: 当缺少必需的占位符字段时
        """
        template_obj = self.get_template(mode)

        missing = [f for f in template_obj.required_fields if f not in kwargs]
        if missing:
            raise ValueError(
                f"模板 '{mode.value}' 缺少必需字段: {', '.join(missing)}"
            )

        return template_obj.template.format(**kwargs)

    def list_templates(self) -> list[str]:
        """列出所有已注册的模板名称。

        Returns:
            模板名称列表
        """
        return list(self._templates.keys())

    def _register_defaults(self) -> None:
        """注册默认模板。"""

        # STANDARD: 适用于 GPT-4o / Qwen-Plus + 复杂任务
        self.register_template(
            "standard",
            SystemPrompt(
                template=(
                    "你是一个专业的UI自动化测试Agent。你的任务是分析当前页面状态并决定下一步操作。\n"
                    "\n"
                    "请以JSON格式输出：\n"
                    "{{\n"
                    '  "thinking": "内部思考过程",\n'
                    '  "evaluation_previous_goal": "评估上一步操作结果",\n'
                    '  "memory": "跨步记忆，记住关键信息",\n'
                    '  "next_goal": "下一步目标",\n'
                    '  "action": [{{"action_type": "操作类型", "params": {{"参数": "值"}}, "description": "操作描述"}}],\n'
                    '  "is_done": false,\n'
                    '  "current_plan_item": 1,\n'
                    '  "plan_update": null\n'
                    "}}\n"
                    "\n"
                    "可用操作：navigate, click, input, scroll, press_key, select_option, wait, extract, go_back, done"
                ),
                mode=PromptMode.STANDARD,
                description="标准模式，适用于 GPT-4o / Qwen-Plus 等强推理模型处理复杂任务",
                required_fields=[],
            ),
        )

        # FLASH: 适用于轻量级模型 + 简单任务
        self.register_template(
            "flash",
            SystemPrompt(
                template=(
                    "你是UI测试Agent。以JSON输出：\n"
                    '{{"memory": "记忆", "action": [{{"action_type": "操作", "params": {{}}}}], "is_done": false}}'
                ),
                mode=PromptMode.FLASH,
                description="快速模式，适用于轻量级模型处理简单任务",
                required_fields=[],
            ),
        )

        # VISUAL: 适用于 VL 视觉语言模型 + 视觉定位
        self.register_template(
            "visual",
            SystemPrompt(
                template=(
                    "你是UI视觉定位Agent。分析截图定位目标元素。\n"
                    "\n"
                    "以JSON输出：\n"
                    '{{"region": {{"x": 0, "y": 0, "width": 100, "height": 100}}, '
                    '"center": {{"x": 50, "y": 50}}, '
                    '"confidence": 0.9}}'
                ),
                mode=PromptMode.VISUAL,
                description="视觉定位模式，适用于 VL 模型进行元素视觉定位",
                required_fields=[],
            ),
        )

        # NO_THINKING: 适用于快速推理模型
        self.register_template(
            "no_thinking",
            SystemPrompt(
                template=(
                    "你是UI测试Agent。直接输出动作：\n"
                    '{{"action": [{{"action_type": "操作", "params": {{}}}}], "is_done": false}}'
                ),
                mode=PromptMode.NO_THINKING,
                description="无思考模式，适用于快速推理模型直接输出动作",
                required_fields=[],
            ),
        )

        # ANTHROPIC: 适用于 Anthropic Claude 系列
        self.register_template(
            "anthropic",
            SystemPrompt(
                template=(
                    "你是一个专业的UI自动化测试Agent。你的任务是分析当前页面状态并决定下一步操作。\n"
                    "\n"
                    "请以JSON格式输出：\n"
                    "{{\n"
                    '  "thinking": "内部思考过程",\n'
                    '  "evaluation_previous_goal": "评估上一步操作结果",\n'
                    '  "memory": "跨步记忆，记住关键信息",\n'
                    '  "next_goal": "下一步目标",\n'
                    '  "action": [{{"action_type": "操作类型", "params": {{"参数": "值"}}, "description": "操作描述"}}],\n'
                    '  "is_done": false,\n'
                    '  "current_plan_item": 1,\n'
                    '  "plan_update": null\n'
                    "}}\n"
                    "\n"
                    "可用操作：navigate, click, input, scroll, press_key, select_option, wait, extract, go_back, done"
                ),
                mode=PromptMode.ANTHROPIC,
                description="Anthropic 模式，适用于 Claude 系列模型",
                required_fields=[],
            ),
        )

        # LOCAL: 适用于 Ollama 本地模型
        self.register_template(
            "local",
            SystemPrompt(
                template=(
                    "你是UI测试Agent。分析页面并操作。\n"
                    "输出JSON：{{\"action\": [{{\"action_type\": \"操作\", \"params\": {{}}}}], \"is_done\": false}}\n"
                    "可用操作：navigate, click, input, scroll, wait, done"
                ),
                mode=PromptMode.LOCAL,
                description="本地模式，适用于 Ollama 等本地部署模型",
                required_fields=[],
            ),
        )
