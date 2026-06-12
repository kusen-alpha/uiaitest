"""配置体系 - 支持多环境、多平台配置"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
import yaml

@dataclass
class BrowserConfig:
    """浏览器配置"""
    browser_type: str = "chromium"
    headless: bool = True
    slow_mo: float = 0.0
    viewport: dict[str, int] = field(default_factory=lambda: {"width": 1280, "height": 720})
    ignore_https_errors: bool = True
    record_video: bool = False
    record_trace: bool = True
    test_id_attribute: str = "data-testid"
    allowed_domains: list[str] = field(default_factory=list)       # 域名白名单
    prohibited_domains: list[str] = field(default_factory=list)    # 域名黑名单

@dataclass
class AppiumConfig:
    """Appium配置"""
    server_url: str = "http://127.0.0.1:4723"
    platform_name: str = "Android"
    automation_name: str = "UiAutomator2"
    device_name: str = ""
    app: str = ""
    app_package: str = ""
    app_activity: str = ""
    no_reset: bool = True
    capabilities: dict[str, Any] = field(default_factory=dict)

@dataclass
class LLMConfig:
    """LLM模型配置"""
    provider: str = "openai"        # openai / dashscope / volcengine / ollama
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.1
    max_tokens: int = 4096
    vl_model: str = ""              # 视觉语言模型名称
    vl_provider: str = ""           # 视觉语言模型提供商
    fallback_model: str = ""        # 备用模型（FallbackLLM）
    locate_model: str = "ui-tars-7b"  # 定位专用模型
    extract_model: str = ""         # 轻量提取模型

@dataclass
class HealingConfig:
    """自愈配置"""
    enabled: bool = True
    max_retries: int = 3
    auto_apply: bool = False        # 是否自动应用修复（建议False，需人工审核）
    strategies: list[str] = field(default_factory=lambda: [
        "selector_fallback",    # 选择器降级
        "dom_neighbor_search",  # DOM邻近搜索
        "visual_ocr",           # 视觉OCR兜底
        "ai_code_fix",          # AI代码修复
    ])
    screenshot_on_failure: bool = True

@dataclass
class ReportConfig:
    """报告配置"""
    output_dir: str = "./reports"
    format: str = "html"            # html / json / all
    include_screenshots: bool = True
    include_trace: bool = True
    include_video: bool = False

@dataclass
class UIAIConfig:
    """UIAI全局配置"""
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    appium: AppiumConfig = field(default_factory=AppiumConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    healing: HealingConfig = field(default_factory=HealingConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    base_url: str = ""
    timeout: int = 30000            # 默认超时(ms)
    retry_count: int = 2            # 失败重试次数
    parallel_workers: int = 1       # 并行Worker数
    env: str = "test"               # 环境: dev/test/staging/prod

    @classmethod
    def from_yaml(cls, path: str | Path) -> UIAIConfig:
        """从YAML文件加载配置"""
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> UIAIConfig:
        """从字典构建配置"""
        config = cls()
        if "browser" in data:
            for k, v in data["browser"].items():
                if hasattr(config.browser, k):
                    setattr(config.browser, k, v)
        if "appium" in data:
            for k, v in data["appium"].items():
                if hasattr(config.appium, k):
                    setattr(config.appium, k, v)
        if "llm" in data:
            for k, v in data["llm"].items():
                if hasattr(config.llm, k):
                    setattr(config.llm, k, v)
        if "healing" in data:
            for k, v in data["healing"].items():
                if hasattr(config.healing, k):
                    setattr(config.healing, k, v)
        if "report" in data:
            for k, v in data["report"].items():
                if hasattr(config.report, k):
                    setattr(config.report, k, v)
        for k in ("base_url", "timeout", "retry_count", "parallel_workers", "env"):
            if k in data:
                setattr(config, k, data[k])
        return config

    def to_yaml(self, path: str | Path) -> None:
        """保存配置到YAML文件"""
        import dataclasses
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = dataclasses.asdict(self)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


class ConfigProxy:
    """统一配置管理器 — 支持多级配置合并与热更新"""

    def __init__(self):
        self._config: dict = {}
        self._watchers: dict[str, list[Callable]] = {}
        self._sources: dict[str, dict] = {}  # source_name -> config dict

    def load(self, env: str | None = None) -> None:
        """加载配置，按优先级合并：defaults → ~/.uiai/config.yaml → uiai.yaml → uiai.{env}.yaml"""
        # 1. Load defaults (built-in)
        defaults = {
            "browser": {
                "browser_type": "chromium",
                "headless": True,
                "slow_mo": 0.0,
                "viewport": {"width": 1280, "height": 720},
                "ignore_https_errors": True,
                "record_video": False,
                "record_trace": True,
                "test_id_attribute": "data-testid",
                "allowed_domains": [],
                "prohibited_domains": [],
            },
            "appium": {
                "server_url": "http://127.0.0.1:4723",
                "platform_name": "Android",
                "automation_name": "UiAutomator2",
                "device_name": "",
                "app": "",
                "app_package": "",
                "app_activity": "",
                "no_reset": True,
                "capabilities": {},
            },
            "llm": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "",
                "base_url": "",
                "temperature": 0.1,
                "max_tokens": 4096,
                "vl_model": "",
                "vl_provider": "",
                "fallback_model": "",
                "locate_model": "ui-tars-7b",
                "extract_model": "",
            },
            "healing": {
                "enabled": True,
                "max_retries": 3,
                "auto_apply": False,
                "strategies": [
                    "selector_fallback",
                    "dom_neighbor_search",
                    "visual_ocr",
                    "ai_code_fix",
                ],
                "screenshot_on_failure": True,
            },
            "report": {
                "output_dir": "./reports",
                "format": "html",
                "include_screenshots": True,
                "include_trace": True,
                "include_video": False,
            },
            "base_url": "",
            "timeout": 30000,
            "retry_count": 2,
            "parallel_workers": 1,
            "env": env or "test",
        }

        # 2. Load ~/.uiai/config.yaml (user global)
        home_config = self._load_yaml(str(Path.home() / ".uiai" / "config.yaml"))

        # 3. Load uiai.yaml (project)
        project_config = self._load_yaml("uiai.yaml")

        # 4. Load uiai.{env}.yaml (environment override)
        env_config = {}
        effective_env = env or defaults.get("env", "test")
        if effective_env:
            env_config = self._load_yaml(f"uiai.{effective_env}.yaml")

        # Merge with increasing priority
        merged = self._merge(defaults, home_config)
        merged = self._merge(merged, project_config)
        merged = self._merge(merged, env_config)

        self._config = merged

        # Track source of each key
        self._sources = {}
        self._sources["defaults"] = defaults
        if home_config:
            self._sources["~/.uiai/config.yaml"] = home_config
        if project_config:
            self._sources["uiai.yaml"] = project_config
        if env_config:
            self._sources[f"uiai.{effective_env}.yaml"] = env_config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号路径（如 llm.provider.model）"""
        parts = key.split(".")
        current = self._config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def set(self, key: str, value: Any) -> None:
        """运行时设置配置项，触发watchers"""
        old_value = self.get(key)
        parts = key.split(".")
        current = self._config
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        # Trigger watchers
        if key in self._watchers:
            for callback in self._watchers[key]:
                callback(key, old_value, value)

    def watch(self, key: str, callback: Callable) -> None:
        """监听配置变更"""
        if key not in self._watchers:
            self._watchers[key] = []
        self._watchers[key].append(callback)

    def validate(self) -> list[str]:
        """校验配置合法性，返回错误列表"""
        errors: list[str] = []
        # llm.api_key must be non-empty if llm.provider is set
        provider = self.get("llm.provider")
        api_key = self.get("llm.api_key")
        if provider and not api_key:
            errors.append("llm.api_key must be non-empty when llm.provider is set")
        # browser.viewport must have width and height > 0
        viewport = self.get("browser.viewport")
        if isinstance(viewport, dict):
            width = viewport.get("width", 0)
            height = viewport.get("height", 0)
            if not isinstance(width, (int, float)) or width <= 0:
                errors.append("browser.viewport.width must be > 0")
            if not isinstance(height, (int, float)) or height <= 0:
                errors.append("browser.viewport.height must be > 0")
        # parallel_workers must be > 0
        parallel_workers = self.get("parallel_workers")
        if not isinstance(parallel_workers, (int, float)) or parallel_workers <= 0:
            errors.append("parallel_workers must be > 0")
        # timeout must be > 0
        timeout = self.get("timeout")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            errors.append("timeout must be > 0")
        return errors

    def to_uiai_config(self) -> UIAIConfig:
        """转换为UIAIConfig对象"""
        return UIAIConfig._from_dict(self._config)

    def _merge(self, base: dict, override: dict) -> dict:
        """深度合并两个字典"""
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge(result[key], value)
            else:
                result[key] = value
        return result

    def _load_yaml(self, path: str) -> dict:
        """加载YAML文件"""
        try:
            p = Path(path)
            if not p.exists():
                return {}
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
