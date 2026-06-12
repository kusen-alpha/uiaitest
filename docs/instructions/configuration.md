# 配置详解

本文档详细介绍 UIAI 的所有配置选项。

---

## 目录

1. [配置文件结构](#一配置文件结构)
2. [浏览器配置](#二浏览器配置)
3. [Appium 配置](#三appium-配置)
4. [LLM 配置](#四llm-配置)
5. [自愈配置](#五自愈配置)
6. [报告配置](#六报告配置)
7. [Watchdog 配置](#七watchdog-配置)
8. [全局配置](#八全局配置)
9. [环境配置](#九环境配置)
10. [配置管理](#十配置管理)

---

## 一、配置文件结构

### 1.1 多级配置合并

UIAI 支持多级配置合并，优先级从低到高：

```
defaults（内置默认） → ~/.uiai/config.yaml（用户全局） → uiai.yaml（项目） → uiai.{env}.yaml（环境）
```

### 1.2 配置文件位置

| 配置文件 | 位置 | 说明 |
|---------|------|------|
| 内置默认 | uiai/config/defaults.yaml | 框架默认配置 |
| 用户全局 | ~/.uiai/config.yaml | 用户级配置 |
| 项目配置 | ./uiai.yaml | 项目级配置 |
| 环境配置 | ./uiai.{env}.yaml | 环境特定配置 |

### 1.3 完整配置示例

```yaml
# 浏览器配置
browser:
  browser_type: chromium
  headless: true
  slow_mo: 0.0
  viewport:
    width: 1280
    height: 720
  ignore_https_errors: true
  record_video: false
  record_trace: true
  test_id_attribute: "data-testid"
  allowed_domains: []
  prohibited_domains: []

# Appium 配置
appium:
  server_url: "http://127.0.0.1:4723"
  platform_name: Android
  automation_name: UiAutomator2
  device_name: ""
  app: ""
  app_package: ""
  app_activity: ""
  no_reset: true
  capabilities: {}

# LLM 配置
llm:
  provider: openai
  model: gpt-4o
  api_key: ""
  base_url: ""
  temperature: 0.1
  max_tokens: 4096
  vl_model: ""
  vl_provider: ""
  fallback_model: ""
  locate_model: ""
  extract_model: ""

# 自愈配置
healing:
  enabled: true
  max_retries: 3
  auto_apply: false
  strategies:
    - selector_fallback
    - dom_neighbor_search
    - visual_ocr
    - ai_code_fix
  screenshot_on_failure: true

# 报告配置
report:
  output_dir: ./reports
  format: html
  include_screenshots: true
  include_trace: true
  include_video: false

# Watchdog 配置
watchdog:
  popup:
    enabled: true
    default_action: accept
  captcha:
    enabled: true
    totp_secret: ""
  crash:
    enabled: true
    max_restarts: 3
  network:
    enabled: true
    timeout: 30000
  storage:
    enabled: true
    save_cookies: true
  download:
    enabled: true
    download_dir: ./downloads
  dom:
    enabled: true
  visual_anomaly:
    enabled: true

# 缓存配置
cache:
  enabled: true
  storage_dir: ./.uiai_cache
  max_entries: 1000
  ttl: 3600

# 知识库配置
knowledge:
  enabled: true
  storage_dir: ./.uiai_knowledge
  max_entries: 500

# 检查点配置
checkpoint:
  enabled: true
  interval: 5
  storage_dir: ./checkpoints
  max_checkpoints: 10

# 全局配置
base_url: ""
timeout: 30000
retry_count: 2
parallel_workers: 1
env: test
```

---

## 二、浏览器配置

### 2.1 BrowserConfig

```yaml
browser:
  browser_type: chromium    # 浏览器类型
  headless: true            # 无头模式
  slow_mo: 0.0              # 操作延迟（秒）
  viewport:                 # 视口大小
    width: 1280
    height: 720
  ignore_https_errors: true # 忽略 HTTPS 错误
  record_video: false       # 录制视频
  record_trace: true        # 录制 Playwright Trace
  test_id_attribute: "data-testid"  # TestID 属性名
  allowed_domains: []       # 域名白名单
  prohibited_domains: []    # 域名黑名单
```

### 2.2 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| browser_type | str | chromium | 浏览器类型：chromium / firefox / safari |
| headless | bool | true | 无头模式，调试时设为 false |
| slow_mo | float | 0.0 | 操作延迟秒数，调试时可设置 0.5 |
| viewport | dict | {width:1280, height:720} | 视口大小 |
| ignore_https_errors | bool | true | 忽略 HTTPS 证书错误 |
| record_video | bool | false | 录制视频，存储在 reports 目录 |
| record_trace | bool | true | 录制 Playwright Trace，便于调试 |
| test_id_attribute | str | data-testid | TestID 属性名，影响 Locator.by_test_id |
| allowed_domains | list | [] | 域名白名单，SecurityWatchdog 使用 |
| prohibited_domains | list | [] | 域名黑名单，SecurityWatchdog 使用 |

### 2.3 浏览器类型

| 类型 | 说明 | 支持平台 |
|------|------|---------|
| chromium | Chromium 浏览器 | Windows / macOS / Linux |
| firefox | Firefox 浏览器 | Windows / macOS / Linux |
| safari | Safari 浏览器 | macOS |

### 2.4 使用示例

```python
from uiai.config import UIAIConfig, BrowserConfig

# 创建浏览器配置
browser_config = BrowserConfig(
    browser_type="chromium",
    headless=False,  # 调试模式
    slow_mo=0.5,     # 每步延迟 0.5 秒
    viewport={"width": 1920, "height": 1080},
    record_trace=True
)

# 创建主配置
config = UIAIConfig(browser=browser_config)
```

---

## 三、Appium 配置

### 3.1 AppiumConfig

```yaml
appium:
  server_url: "http://127.0.0.1:4723"  # Appium Server 地址
  platform_name: Android               # 平台名称
  automation_name: UiAutomator2        # 自动化框架
  device_name: ""                      # 设备名称
  app: ""                              # APP 路径
  app_package: ""                      # APP 包名
  app_activity: ""                     # APP Activity
  no_reset: true                       # 不重置 APP
  capabilities: {}                     # 额外 Capabilities
```

### 3.2 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| server_url | str | http://127.0.0.1:4723 | Appium Server 地址 |
| platform_name | str | Android | 平台：Android / iOS |
| automation_name | str | UiAutomator2 | 自动化框架：UiAutomator2 / XCUITest |
| device_name | str | "" | 设备名称或 UDID |
| app | str | "" | APP 安装包路径 |
| app_package | str | "" | APP 包名（Android） |
| app_activity | str | "" | APP 启动 Activity（Android） |
| no_reset | bool | true | 不重置 APP 状态 |
| capabilities | dict | {} | 额外 Capabilities |

### 3.3 Android 配置示例

```yaml
appium:
  server_url: "http://127.0.0.1:4723"
  platform_name: Android
  automation_name: UiAutomator2
  device_name: "emulator-5554"
  app_package: "com.example.app"
  app_activity: "com.example.app.MainActivity"
  no_reset: false
  capabilities:
    autoGrantPermissions: true
    ignoreUnimportantViews: true
```

### 3.4 iOS 配置示例

```yaml
appium:
  server_url: "http://127.0.0.1:4723"
  platform_name: iOS
  automation_name: XCUITest
  device_name: "iPhone 14"
  app: "/path/to/app.app"
  capabilities:
    platformVersion: "16.0"
    autoAcceptAlerts: true
```

---

## 四、LLM 配置

### 4.1 LLMConfig

```yaml
llm:
  provider: openai           # 提供商
  model: gpt-4o              # 主模型
  api_key: ""                # API Key
  base_url: ""               # 自定义 endpoint
  temperature: 0.1           # 温度参数
  max_tokens: 4096           # 最大输出 tokens
  vl_model: ""               # 视觉语言模型
  vl_provider: ""            # VL 模型提供商
  fallback_model: ""         # 备用模型
  locate_model: ""           # 定位专用模型
  extract_model: ""          # 轻量提取模型
```

### 4.2 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| provider | str | openai | LLM 提供商 |
| model | str | gpt-4o | 主模型名称 |
| api_key | str | "" | API Key，建议使用环境变量 |
| base_url | str | "" | 自定义 API endpoint |
| temperature | float | 0.1 | 温度参数，0-1 |
| max_tokens | int | 4096 | 最大输出 tokens |
| vl_model | str | "" | 视觉语言模型 |
| vl_provider | str | "" | VL 模型提供商 |
| fallback_model | str | "" | 备用模型，主模型失败时切换 |
| locate_model | str | "" | 定位专用模型 |
| extract_model | str | "" | 轻量提取模型 |

### 4.3 支持的提供商

| 提供商 | 说明 | 推荐模型 |
|--------|------|---------|
| openai | OpenAI API | GPT-4o / GPT-4-Vision |
| dashscope | 阿里云 DashScope | Qwen-Plus / Qwen-VL-Plus |
| volcengine | 火山引擎 | Doubao-Pro |
| ollama | Ollama 本地部署 | Llama3 / Qwen2 |

### 4.4 OpenAI 配置示例

```yaml
llm:
  provider: openai
  model: gpt-4o
  api_key: "${OPENAI_API_KEY}"
  vl_model: "gpt-4-vision-preview"
  fallback_model: "gpt-3.5-turbo"
  temperature: 0.1
  max_tokens: 4096
```

### 4.5 阿里云 DashScope 配置示例

```yaml
llm:
  provider: dashscope
  model: qwen-plus
  api_key: "${DASHSCOPE_API_KEY}"
  vl_model: "qwen-vl-plus"
  fallback_model: "qwen-turbo"
  temperature: 0.1
  max_tokens: 4096
```

### 4.6 火山引擎配置示例

```yaml
llm:
  provider: volcengine
  model: doubao-pro
  api_key: "${VOLCENGINE_API_KEY}"
  temperature: 0.1
  max_tokens: 4096
```

### 4.7 Ollama 本地部署配置示例

```yaml
llm:
  provider: ollama
  model: llama3
  base_url: "http://localhost:11434"
  temperature: 0.1
  max_tokens: 4096
```

### 4.8 多模型配置示例

```yaml
llm:
  provider: openai
  model: gpt-4o              # 主模型（PLAN/HEAL）
  vl_model: gpt-4-vision-preview  # 视觉模型（LOCATE/ASSERT）
  extract_model: gpt-3.5-turbo    # 轻量模型（EXTRACT）
  locate_model: ui-tars-7b        # 定位模型（LOCATE）
  fallback_model: gpt-3.5-turbo   # 备用模型
```

---

## 五、自愈配置

### 5.1 HealingConfig

```yaml
healing:
  enabled: true              # 是否启用自愈
  max_retries: 3             # 最大重试次数
  auto_apply: false          # 是否自动应用修复
  strategies:                # 自愈策略顺序
    - selector_fallback
    - dom_neighbor_search
    - visual_ocr
    - ai_code_fix
  screenshot_on_failure: true # 失败时截图
```

### 5.2 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| enabled | bool | true | 是否启用自愈功能 |
| max_retries | int | 3 | 每步最大重试次数 |
| auto_apply | bool | false | 是否自动应用修复，建议 false |
| strategies | list | [...] | 自愈策略列表，按顺序尝试 |
| screenshot_on_failure | bool | true | 失败时自动截图 |

### 5.3 自愈策略

| 策略 | 说明 | 自动化程度 |
|------|------|-----------|
| selector_fallback | 选择器降级 | 自动 |
| dom_neighbor_search | DOM 邻近搜索 | 自动 |
| visual_ocr | 视觉定位兜底 | 自动 |
| ai_code_fix | AI 修复建议 | 需人工审核 |

### 5.4 生产环境配置

```yaml
healing:
  enabled: true
  auto_apply: false  # 需人工审核
  max_retries: 3
  screenshot_on_failure: true
```

### 5.5 开发环境配置

```yaml
healing:
  enabled: true
  auto_apply: true   # 自动应用（谨慎使用）
  max_retries: 5
  screenshot_on_failure: true
```

---

## 六、报告配置

### 6.1 ReportConfig

```yaml
report:
  output_dir: ./reports      # 输出目录
  format: html               # 格式
  include_screenshots: true  # 包含截图
  include_trace: true        # 包含 Playwright Trace
  include_video: false       # 包含视频
```

### 6.2 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| output_dir | str | ./reports | 报告输出目录 |
| format | str | html | 报告格式：html / json / all |
| include_screenshots | bool | true | 包含截图 |
| include_trace | bool | true | 包含 Playwright Trace |
| include_video | bool | false | 包含视频 |

### 6.3 报告格式

| 格式 | 说明 |
|------|------|
| html | HTML 格式，可视化报告 |
| json | JSON 格式，便于解析 |
| all | 同时生成 HTML 和 JSON |

---

## 七、Watchdog 配置

### 7.1 PopupWatchdog 配置

```yaml
watchdog:
  popup:
    enabled: true
    default_action: accept  # accept / dismiss
    prompt_default: ""      # prompt 默认值
```

### 7.2 CaptchaWatchdog 配置

```yaml
watchdog:
  captcha:
    enabled: true
    totp_secret: ""         # TOTP 密钥
    hotp_secret: ""         # HOTP 密钥
    hotp_counter: 0         # HOTP 计数器
    notify_on_unknown: true # 未知验证码通知人工
```

### 7.3 CrashWatchdog 配置

```yaml
watchdog:
  crash:
    enabled: true
    max_restarts: 3         # 最大重启次数
    checkpoint_interval: 5  # 检查点间隔（步数）
```

### 7.4 NetworkWatchdog 配置

```yaml
watchdog:
  network:
    enabled: true
    timeout: 30000          # 超时时间（毫秒）
    retry_count: 3          # 重试次数
    retry_delay: 1000       # 重试延迟（毫秒）
```

### 7.5 StorageWatchdog 配置

```yaml
watchdog:
  storage:
    enabled: true
    save_cookies: true
    save_local_storage: true
    checkpoint_dir: "./checkpoints"
```

### 7.6 DownloadWatchdog 配置

```yaml
watchdog:
  download:
    enabled: true
    download_dir: "./downloads"
    timeout: 60000          # 下载超时（毫秒）
```

### 7.7 DomWatchdog 配置

```yaml
watchdog:
  dom:
    enabled: true
    debounce: 500           # 防抖时间（毫秒）
```

### 7.8 VisualAnomalyWatchdog 配置

```yaml
watchdog:
  visual_anomaly:
    enabled: true
    white_screen_threshold: 0.95  # 白屏阈值
    empty_image_threshold: 0.9    # 空图阈值
```

---

## 八、全局配置

### 8.1 全局参数

```yaml
base_url: ""                 # 应用基础 URL
timeout: 30000               # 默认超时（毫秒）
retry_count: 2               # 失败重试次数
parallel_workers: 1          # 并行 Worker 数
env: test                    # 环境：dev / test / staging / prod
```

### 8.2 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| base_url | str | "" | 应用基础 URL，用于 navigate |
| timeout | int | 30000 | 默认超时时间（毫秒） |
| retry_count | int | 2 | 失败重试次数 |
| parallel_workers | int | 1 | 并行 Worker 数量 |
| env | str | test | 运行环境 |

---

## 九、环境配置

### 9.1 环境配置文件

支持按环境加载不同配置：

```
config/
├── default.yaml      # 默认配置
├── dev.yaml          # 开发环境
├── test.yaml         # 测试环境
├── staging.yaml      # 预发布环境
└── prod.yaml         # 生产环境
```

### 9.2 开发环境配置示例

```yaml
# uiai.dev.yaml
browser:
  headless: false
  slow_mo: 0.5

llm:
  model: gpt-4o

healing:
  auto_apply: true

env: dev
```

### 9.3 测试环境配置示例

```yaml
# uiai.test.yaml
browser:
  headless: true

llm:
  model: gpt-4o

healing:
  auto_apply: false

base_url: "https://test.example.com"
env: test
```

### 9.4 生产环境配置示例

```yaml
# uiai.prod.yaml
browser:
  headless: true

llm:
  model: gpt-4o

healing:
  enabled: false  # 生产环境禁用自愈

base_url: "https://example.com"
env: prod
```

---

## 十、配置管理

### 10.1 加载配置

```python
from uiai.config import UIAIConfig

# 从 YAML 文件加载
config = UIAIConfig.from_yaml("uiai.yaml")

# 从字典创建
config = UIAIConfig.from_dict({
    "browser": {"headless": True},
    "llm": {"model": "gpt-4o"}
})

# 使用默认配置
config = UIAIConfig()
```

### 10.2 使用 ConfigProxy

```python
from uiai.config import ConfigProxy

# 创建配置代理
proxy = ConfigProxy()

# 加载配置
proxy.load()

# 加载特定环境
proxy.load(env="staging")

# 获取配置
config = proxy.config
```

### 10.3 环境变量

| 变量 | 说明 |
|------|------|
| OPENAI_API_KEY | OpenAI API Key |
| DASHSCOPE_API_KEY | 阿里云 DashScope API Key |
| VOLCENGINE_API_KEY | 火山引擎 API Key |
| UIAI_CONFIG_PATH | 配置文件路径 |
| UIAI_ENV | 运行环境 |

### 10.4 配置验证

```python
from uiai.config import UIAIConfig

config = UIAIConfig()

# 验证配置
errors = config.validate()
if errors:
    for error in errors:
        print(f"配置错误: {error}")
```

### 10.5 CLI 配置管理

```bash
# 显示当前配置
uiai config --show

# 验证配置文件
uiai config --validate

# 指定配置文件路径
uiai config --path /path/to/uiai.yaml
```

---

> **下一步**: 查看 [API 参考](./api-reference.md) 或 [CLI 命令参考](./cli-reference.md)。