"""环境管理 - 多环境配置管理"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from uiai.config import UIAIConfig

logger = logging.getLogger(__name__)


@dataclass
class Environment:
    """环境配置"""
    name: str
    base_url: str = ""
    api_url: str = ""
    db_config: dict[str, Any] = field(default_factory=dict)
    custom_config: dict[str, Any] = field(default_factory=dict)
    description: str = ""


class EnvironmentManager:
    """环境管理器

    管理多环境配置（dev/test/staging/prod），
    支持YAML配置文件和环境变量覆盖。
    """

    def __init__(self):
        self._environments: dict[str, Environment] = {}
        self._current: str = ""

    def register(self, env: Environment) -> None:
        """注册环境"""
        self._environments[env.name] = env
        logger.debug(f"Environment registered: {env.name}")

    def get(self, name: str) -> Environment | None:
        """获取环境配置"""
        return self._environments.get(name)

    def set_current(self, name: str) -> None:
        """设置当前环境"""
        if name not in self._environments:
            raise ValueError(f"Environment not found: {name}")
        self._current = name
        logger.info(f"Current environment set to: {name}")

    @property
    def current(self) -> Environment | None:
        """获取当前环境"""
        if self._current:
            return self._environments.get(self._current)
        return None

    @property
    def current_name(self) -> str:
        return self._current

    def list_environments(self) -> list[str]:
        """列出所有环境"""
        return list(self._environments.keys())

    @classmethod
    def from_yaml(cls, path: str | Path) -> EnvironmentManager:
        """从YAML文件加载环境配置"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Environment config not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        manager = cls()
        for name, env_data in data.items():
            if isinstance(env_data, dict):
                env = Environment(
                    name=name,
                    base_url=env_data.get("base_url", ""),
                    api_url=env_data.get("api_url", ""),
                    db_config=env_data.get("db_config", {}),
                    custom_config=env_data.get("custom_config", {}),
                    description=env_data.get("description", ""),
                )
                manager.register(env)

        # 设置默认环境
        if "default_env" in data:
            manager.set_current(data["default_env"])
        elif manager._environments:
            manager.set_current(list(manager._environments.keys())[0])

        return manager

    def to_uiai_config(self, env_name: str | None = None) -> UIAIConfig:
        """将环境配置转为UIAIConfig"""
        env = self.get(env_name or self._current)
        if not env:
            return UIAIConfig()

        config = UIAIConfig(base_url=env.base_url, env=env.name)
        return config
