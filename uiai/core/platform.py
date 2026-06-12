"""平台枚举与类型定义"""
from enum import Enum

class Platform(Enum):
    """支持的平台类型"""
    WEB = "web"
    H5 = "h5"
    ANDROID = "android"
    IOS = "ios"
    MINI_PROGRAM = "mini_program"
    DESKTOP = "desktop"

class BrowserType(Enum):
    """浏览器类型"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"

class ExecutionMode(Enum):
    """运行模式（有头/无头）"""
    HEADED = "headed"
    HEADLESS = "headless"

class PerceptionMode(Enum):
    """感知模式 — Agent如何感知页面状态"""
    A11Y_SNAPSHOT = "a11y_snapshot"      # Accessibility Tree快照，Token高效
    DOM_SERIALIZE = "dom_serialize"      # DOM序列化，信息完整
    VISUAL_SCREENSHOT = "visual_screenshot"  # 纯视觉截图+VL模型，不依赖DOM
    HYBRID = "hybrid"                    # 混合模式：DOM优先，视觉降级

class RunTier(Enum):
    """四层运行模式（R1-R3）"""
    R1_SCRIPT = "r1_script"          # 确定性脚本（60-90%），手写/录制的Python代码
    R2_AGENT = "r2_agent"            # 智能Agent辅助（10-25%），Agent感知+LLM决策+执行循环
    R3_LOCAL_DEV = "r3_local_dev"    # 本地开发（按需），MCP Server + Claude Code CLI
