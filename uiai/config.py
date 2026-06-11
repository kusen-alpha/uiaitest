"""配置体系 - 支持多环境、多平台配置"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
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
