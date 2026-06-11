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
    """执行模式"""
    HEADED = "headed"
    HEADLESS = "headless"
