"""LLM统一接口 - 支持多模型提供商"""
from __future__ import annotations
import logging
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from uiai.config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    """LLM消息"""
    role: str  # system / user / assistant
    content: str
    images: list[bytes] | None = None


class BaseLLMClient(ABC):
    """LLM客户端基类"""

    @abstractmethod
    async def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        """文本对话"""

    @abstractmethod
    async def chat_with_images(self, messages: list[LLMMessage], images: list[bytes], **kwargs) -> str:
        """多模态对话（文本+图片）"""

    @abstractmethod
    async def analyze_image(self, image: bytes, prompt: str) -> str:
        """分析单张图片"""


class OpenAIClient(BaseLLMClient):
    """OpenAI兼容客户端（支持OpenAI/DeepSeek/自定义endpoint）"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                kwargs = {"api_key": self.config.api_key}
                if self.config.base_url:
                    kwargs["base_url"] = self.config.base_url
                self._client = AsyncOpenAI(**kwargs)
            except ImportError:
                raise ImportError("openai package is required. Install: pip install openai")
        return self._client

    async def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        client = self._get_client()
        formatted = [{"role": m.role, "content": m.content} for m in messages]
        response = await client.chat.completions.create(
            model=kwargs.get("model", self.config.model),
            messages=formatted,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        return response.choices[0].message.content

    async def chat_with_images(self, messages: list[LLMMessage], images: list[bytes], **kwargs) -> str:
        client = self._get_client()
        formatted = []
        for m in messages:
            if m.role == "user" and images:
                content = [{"type": "text", "text": m.content}]
                for img in images:
                    b64 = base64.b64encode(img).decode()
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    })
                formatted.append({"role": m.role, "content": content})
            else:
                formatted.append({"role": m.role, "content": m.content})

        model = kwargs.get("vl_model", self.config.vl_model) or self.config.model
        response = await client.chat.completions.create(
            model=model,
            messages=formatted,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        return response.choices[0].message.content

    async def analyze_image(self, image: bytes, prompt: str) -> str:
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_with_images(messages, [image])


class DashScopeClient(BaseLLMClient):
    """阿里DashScope客户端（Qwen-VL）"""

    def __init__(self, config: LLMConfig):
        self.config = config

    async def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        try:
            import dashscope
            dashscope.api_key = self.config.api_key
            response = dashscope.Generation.call(
                model=kwargs.get("model", self.config.model),
                messages=[{"role": m.role, "content": m.content} for m in messages],
                result_format="message",
            )
            return response.output.choices[0].message.content
        except ImportError:
            raise ImportError("dashscope package is required for Qwen models")

    async def chat_with_images(self, messages: list[LLMMessage], images: list[bytes], **kwargs) -> str:
        try:
            import dashscope
            dashscope.api_key = self.config.api_key
            formatted = []
            for m in messages:
                content = [{"text": m.content}]
                if m.role == "user" and images:
                    for img in images:
                        b64 = base64.b64encode(img).decode()
                        content.append({"image": f"data:image/png;base64,{b64}"})
                formatted.append({"role": m.role, "content": content})

            model = kwargs.get("vl_model", self.config.vl_model) or "qwen-vl-max"
            response = dashscope.MultiModalConversation.call(
                model=model,
                messages=formatted,
            )
            return response.output.choices[0].message.content[0]["text"]
        except ImportError:
            raise ImportError("dashscope package is required for Qwen-VL")

    async def analyze_image(self, image: bytes, prompt: str) -> str:
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_with_images(messages, [image])


class OllamaClient(BaseLLMClient):
    """Ollama本地模型客户端"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url or "http://localhost:11434"

    async def chat(self, messages: list[LLMMessage], **kwargs) -> str:
        import aiohttp
        formatted = [{"role": m.role, "content": m.content} for m in messages]
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": kwargs.get("model", self.config.model),
                    "messages": formatted,
                    "stream": False,
                }
            ) as resp:
                data = await resp.json()
                return data["message"]["content"]

    async def chat_with_images(self, messages: list[LLMMessage], images: list[bytes], **kwargs) -> str:
        import aiohttp
        formatted = []
        for m in messages:
            content = m.content
            if m.role == "user" and images:
                # Ollama支持图片
                image_list = [base64.b64encode(img).decode() for img in images]
                formatted.append({"role": m.role, "content": content, "images": image_list})
            else:
                formatted.append({"role": m.role, "content": content})

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": kwargs.get("vl_model", self.config.vl_model) or "llava",
                    "messages": formatted,
                    "stream": False,
                }
            ) as resp:
                data = await resp.json()
                return data["message"]["content"]

    async def analyze_image(self, image: bytes, prompt: str) -> str:
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_with_images(messages, [image])


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """根据配置创建LLM客户端"""
    provider = config.provider.lower()
    if provider in ("openai", "deepseek", "custom"):
        return OpenAIClient(config)
    elif provider in ("dashscope", "qwen", "aliyun"):
        return DashScopeClient(config)
    elif provider in ("ollama", "local"):
        return OllamaClient(config)
    else:
        # 默认使用OpenAI兼容接口
        logger.warning(f"Unknown provider '{provider}', falling back to OpenAI compatible")
        return OpenAIClient(config)
