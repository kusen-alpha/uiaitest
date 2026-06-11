# Playwright-Python 深度分析报告

> 基于 playwright-python 源码的深度技术分析，聚焦于 UI-AI 自动化测试场景的应用价值。

---

## 1. 项目概述

### 1.1 基本信息

| 属性 | 值 |
|------|-----|
| 项目名称 | playwright-python |
| 开发者 | Microsoft Corporation |
| 许可证 | Apache-2.0 |
| Python 版本要求 | >= 3.9 |
| 包名 | `playwright` |
| 官方文档 | https://playwright.dev/python/docs/intro |
| 仓库地址 | https://github.com/Microsoft/playwright-python |
| 描述 | A high-level API to automate web browsers |

### 1.2 项目定位

Playwright-Python 是 Microsoft 开发的跨浏览器自动化库的 Python 绑定，支持通过**单一 API** 自动化 Chromium、Firefox 和 WebKit 三大浏览器引擎。其核心设计理念是 **ever-green**（始终跟进最新浏览器版本）、**capable**（功能完备）、**reliable**（可靠稳定）和 **fast**（快速执行）。

当前版本支持的浏览器版本：
- Chromium 148.0.7778.96
- WebKit 26.4
- Firefox 150.0.2

### 1.3 核心特性

- **跨浏览器**：一套 API 驱动 Chromium/Firefox/WebKit
- **跨平台**：支持 Linux/macOS/Windows
- **双模式 API**：同步 API (`sync_api`) 和异步 API (`async_api`)
- **自动等待**：内置智能等待机制，无需手动 sleep
- **网络拦截**：完整的请求/响应拦截与 Mock 能力
- **多 Context 隔离**：BrowserContext 实现会话隔离
- **Trace Viewer**：强大的执行追踪与调试工具
- **HAR 回放**：基于 HAR 文件的网络请求录制与回放
- **代码生成**：支持录制用户操作生成代码（Codegen）

---

## 2. 核心架构

### 2.1 整体架构

Playwright-Python 采用**客户端-服务器**架构，Python 端作为客户端，通过管道（Pipe）与 Playwright Node.js 驱动进程通信：

```
┌─────────────────────────────────────────────────────┐
│                   用户代码                            │
│          (sync_api / async_api)                      │
├─────────────────────────────────────────────────────┤
│           API 层 (Generated)                         │
│    sync_api._generated / async_api._generated       │
├─────────────────────────────────────────────────────┤
│         Impl-to-API 映射层                           │
│       _impl_to_api_mapping.ImplToApiMapping          │
├─────────────────────────────────────────────────────┤
│          实现层 (_impl)                              │
│   _page / _frame / _locator / _browser / ...        │
├─────────────────────────────────────────────────────┤
│          通信层 (Connection)                         │
│   _connection.Connection / Channel / ChannelOwner    │
├─────────────────────────────────────────────────────┤
│          传输层 (Transport)                          │
│   _transport.PipeTransport / JsonPipeTransport       │
├─────────────────────────────────────────────────────┤
│     Playwright Node.js 驱动进程                      │
│   (driver/package/cli.js run-driver)                 │
├─────────────────────────────────────────────────────┤
│     浏览器引擎 (Chromium/Firefox/WebKit)             │
└─────────────────────────────────────────────────────┘
```

### 2.2 通信机制

Python 客户端与 Node.js 驱动进程之间通过 **PipeTransport** 通信：

- **传输方式**：标准输入/输出管道（stdin/stdout），子进程模式
- **消息格式**：JSON，前 4 字节为消息长度（little-endian），后跟 JSON 消息体
- **缓冲区大小**：32768 字节
- **消息流**：
  1. Python 端通过 `Connection._send_message_to_server()` 发送请求
  2. 请求通过 `PipeTransport.send()` 序列化并写入子进程 stdin
  3. Node.js 端处理后返回响应
  4. `PipeTransport.run()` 循环读取 stdout，反序列化后通过 `Connection.dispatch()` 分发

关键源码位置：
- `_transport.py`：PipeTransport 实现，包含 `connect()`、`run()`、`send()` 方法
- `_connection.py`：Connection 类，管理消息收发、对象生命周期、回调映射
- `_driver.py`：驱动进程启动逻辑，定位 `node.exe` 和 `cli.js`

### 2.3 对象模型

Playwright 的核心对象通过 `ChannelOwner` 基类实现远程对象映射：

```
Playwright (入口)
├── chromium: BrowserType
├── firefox: BrowserType
├── webkit: BrowserType
├── selectors: Selectors
├── request: APIRequest
└── devices: Dict

BrowserType
├── launch() → Browser
├── launch_persistent_context() → BrowserContext
├── connect() → Browser (WebSocket)
└── connect_over_cdp() → Browser (CDP)

Browser
├── new_context() → BrowserContext
├── new_page() → Page
├── contexts: List[BrowserContext]
├── start_tracing() / stop_tracing()
└── bind() / unbind() (远程浏览器绑定)

BrowserContext
├── new_page() → Page
├── pages: List[Page]
├── tracing: Tracing
├── request: APIRequestContext
├── clock: Clock
├── debugger: Debugger
├── route() / unroute() (网络拦截)
├── storage_state() (状态持久化)
└── cookies 管理

Page
├── main_frame: Frame
├── frames: List[Frame]
├── keyboard / mouse / touchscreen
├── locator() → Locator
├── get_by_*() → Locator
├── screenshot() / pdf()
├── route() / unroute()
├── expect_*() (事件等待)
└── screencast: Screencast

Frame
├── locator() → Locator
├── get_by_*() → Locator
├── evaluate() / evaluate_handle()
├── wait_for_selector() / wait_for_load_state()
└── click / fill / type / press 等

Locator
├── click / fill / type / check 等
├── get_by_*() → Locator (链式)
├── filter() / nth() / first / last
├── or_() / and_() (逻辑组合)
├── frame_locator() → FrameLocator
├── expect() (断言)
├── aria_snapshot()
└── wait_for()

ElementHandle (继承自 JSHandle)
├── bounding_box() / screenshot()
├── query_selector() / query_selector_all()
├── dispatch_event()
└── select_text() / scroll_into_view_if_needed()
```

### 2.4 同步/异步 API 设计

Playwright-Python 独创性地通过 **greenlet** 协程库实现同步 API，核心设计如下：

#### 异步 API (`async_api`)

直接基于 Python asyncio，所有方法均为 `async`：

```python
# async_api/_context_manager.py
class PlaywrightContextManager:
    async def __aenter__(self) -> AsyncPlaywright:
        loop = asyncio.get_running_loop()
        self._connection = Connection(
            None, create_remote_object, PipeTransport(loop), loop,
        )
        loop.create_task(self._connection.run())
        # 等待 Playwright 对象初始化完成
        playwright = AsyncPlaywright(next(iter(done)).result())
        return playwright
```

#### 同步 API (`sync_api`)

通过 **greenlet** 实现同步阻塞语义，核心机制：

```python
# sync_api/_context_manager.py
class PlaywrightContextManager:
    def __enter__(self) -> SyncPlaywright:
        # 创建 dispatcher fiber（greenlet 协程）
        def greenlet_main():
            self._loop.run_until_complete(self._connection.run_as_sync())
        dispatcher_fiber = MainGreenlet(greenlet_main)

        # 切换到 dispatcher fiber，等待初始化完成
        self._connection.call_on_object_with_known_name("Playwright", callback_wrapper)
        dispatcher_fiber.switch()  # 阻塞直到 Playwright 对象就绪
        return self._playwright
```

**关键实现细节**：
- 同步 API 在独立的 greenlet 中运行事件循环（`dispatcher_fiber`）
- 每次等待异步操作时，通过 `greenlet.switch()` 将控制权交给 dispatcher
- 异步操作完成后，通过回调将控制权切回用户代码的 greenlet
- 事件处理器在同步模式下通过 `EventGreenlet` 执行
- Route 处理器在同步模式下通过 `RouteGreenlet` 执行
- Locator 处理器在同步模式下通过 `LocatorHandlerGreenlet` 执行

#### Impl-to-API 映射层

`ImplToApiMapping` 类负责将内部实现对象（`_impl` 层）映射为用户可见的 API 对象：

- 内部实现类（如 `_locator.Locator`）通过 `API_ATTR` 缓存对应的 API 包装实例
- 事件处理器的参数自动从 impl 对象转换为 API 对象
- 使用 `Map` 类处理循环引用

---

## 3. 技术栈与依赖

### 3.1 核心依赖

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| `pyee` | >=13, <14 | 事件发射器，用于 ChannelOwner 的事件系统 |
| `greenlet` | >=3.1.1, <4.0.0 | 协程库，实现同步 API 的核心机制 |

### 3.2 开发依赖

| 依赖 | 用途 |
|------|------|
| `setuptools` | 构建系统 |
| `setuptools-scm` | 版本管理（从 git tag 自动生成版本号） |
| `pytest` | 测试框架 |
| `pytest-asyncio` | 异步测试支持 |
| `Pillow` / `pixelmatch` | 截图对比（golden 测试） |

### 3.3 构建与打包

- 构建系统：`setuptools` + `setuptools-scm`
- 版本策略：动态版本，通过 `setuptools_scm` 从 git tag 生成，写入 `playwright/_repo_version.py`
- 包结构：
  - `playwright` - 顶层包
  - `playwright._impl` - 内部实现
  - `playwright.async_api` - 异步 API
  - `playwright.sync_api` - 同步 API
  - `playwright._impl.__pyinstaller` - PyInstaller 支持
- CLI 入口：`playwright.__main__:main`，支持 `playwright install` 等命令
- PyInstaller 集成：通过 `hook-dirs` 入口点支持打包

### 3.4 驱动管理

Playwright 的 Node.js 驱动打包在 `playwright/driver/` 目录下：

- **可执行文件**：`driver/node` (Linux/macOS) 或 `driver/node.exe` (Windows)
- **CLI 入口**：`driver/package/cli.js`
- **环境变量**：
  - `PLAYWRIGHT_NODEJS_PATH`：自定义 Node.js 路径
  - `PW_LANG_NAME`：设为 "python"
  - `PW_LANG_NAME_VERSION`：Python 主次版本号
  - `PLAYWRIGHT_BROWSERS_PATH`：浏览器安装路径（PyInstaller 模式下默认为 "0"）

---

## 4. 浏览器自动化核心能力

### 4.1 导航

```python
# 基本导航
page.goto("https://example.com")

# 带等待条件
page.goto("https://example.com", waitUntil="networkidle")

# 前进/后退
page.go_back()
page.go_forward()

# 等待导航
with page.expect_navigation() as response_info:
    page.click("a.link")
```

**源码实现**：`_frame.py` 中的 `goto()` 方法通过 Channel 发送 `goto` 命令到服务端，使用 `_navigation_timeout` 计算超时。`expect_navigation()` 通过 `Waiter` 机制监听 `navigated` 事件，支持 URL 匹配谓词。

### 4.2 交互操作

Page/Frame/Locator 三层均提供完整的交互 API：

| 操作 | 方法 | 说明 |
|------|------|------|
| 点击 | `click()` | 支持 position、modifiers、button、clickCount |
| 双击 | `dblclick()` | 同 click 参数 |
| 填充 | `fill()` | 模拟用户输入，自动清空并输入 |
| 清空 | `clear()` | 清空输入框 |
| 勾选 | `check()` / `uncheck()` | 复选框操作 |
| 选择 | `select_option()` | 下拉选择 |
| 悬停 | `hover()` | 鼠标悬停 |
| 拖拽 | `drag_and_drop()` / `drag_to()` | 拖拽操作 |
| 按键 | `press()` / `type()` | 键盘操作 |
| 上传 | `set_input_files()` | 文件上传 |
| 触摸 | `tap()` | 触摸屏操作 |

**关键设计**：
- 所有交互操作默认自动等待元素可操作（可见、可点击等）
- `force=True` 可跳过可操作性检查
- `trial=True` 仅执行可操作性检查而不实际操作
- `noWaitAfter=True` 跳过操作后的自动等待

### 4.3 等待机制

```python
# 等待元素状态
page.wait_for_selector("#element", state="visible")

# 等待加载状态
page.wait_for_load_state("networkidle")

# 等待 URL
page.wait_for_url("**/dashboard")

# 等待自定义条件
page.wait_for_function("() => document.querySelector('.status').textContent === 'done'")

# 等待超时（不推荐）
page.wait_for_timeout(1000)
```

### 4.4 截图与 PDF

**截图**（Page 和 Locator 均支持）：

```python
# 整页截图
page.screenshot(path="full.png", fullPage=True)

# 元素截图
page.locator(".card").screenshot(path="card.png")

# 带遮罩截图
page.screenshot(path="masked.png", mask=[page.locator(".sensitive")])
```

截图参数：`type`（png/jpeg）、`quality`、`omitBackground`、`clip`、`animations`（allow/disabled）、`caret`（hide/initial）、`scale`（css/device）、`mask`、`maskColor`、`style`

**PDF 生成**（仅 Chromium）：

```python
page.pdf(path="output.pdf", format="A4", print_background=True)
```

PDF 参数：`scale`、`displayHeaderFooter`、`headerTemplate`、`footerTemplate`、`printBackground`、`landscape`、`pageRanges`、`format`、`width`、`height`、`preferCSSPageSize`、`margin`、`outline`、`tagged`

### 4.5 JavaScript 执行

```python
# 执行表达式
result = page.evaluate("() => document.title")

# 带参数执行
result = page.evaluate("(x, y) => x + y", 1, 2)

# 获取 JSHandle
handle = page.evaluate_handle("() => document.querySelector('.item')")

# 在选择器匹配元素上执行
page.eval_on_selector(".item", "el => el.textContent")

# 在所有匹配元素上执行
page.eval_on_selector_all(".item", "els => els.map(e => e.textContent)")
```

### 4.6 录制与回放

**视频录制**：

```python
context = browser.new_context(record_video_dir="videos/")
page = context.new_page()
# ... 操作 ...
context.close()  # 视频在 context 关闭时保存
```

**Screencast（实时录屏）**：

```python
# 录屏到文件
page.screencast.start(path="recording.webm")

# 实时帧回调
page.screencast.start(onFrame=lambda frame: process(frame["data"]))

# 显示操作叠加层
page.screencast.show_actions()
page.screencast.show_overlay("<div>标注</div>")
page.screencast.show_chapter("步骤1", "点击登录按钮")
```

**Codegen（代码生成）**：

通过 CLI 命令 `playwright codegen` 启动交互式录制器，自动生成 Python 代码。

### 4.7 其他能力

- **Cookie 管理**：`context.add_cookies()`、`context.cookies()`、`context.clear_cookies()`
- **存储状态**：`context.storage_state()` 保存/恢复 localStorage 和 cookies
- **地理定位**：`context.grant_permissions(["geolocation"])` + `page.set_geolocation()`
- **设备模拟**：`playwright.devices["iPhone 13"]` 预置设备参数
- **媒体模拟**：`page.emulate_media(colorScheme="dark")`
- **视口设置**：`page.set_viewport_size({"width": 1280, "height": 720})`
- **Clock 控制**：`context.clock.install()`、`context.clock.fast_forward()`、`context.clock.pause_at()`
- **Dialog 处理**：`page.on("dialog", handler)`
- **文件下载**：`page.expect_download()` / `download.path()`
- **弹窗处理**：`page.expect_popup()`
- **暴露函数**：`page.expose_binding("handler", callback)` 将 Python 函数暴露给浏览器

---

## 5. 元素定位体系

### 5.1 定位策略概览

Playwright 提供了多层次的元素定位策略，从推荐到不推荐依次为：

| 策略 | 方法 | 推荐度 | 说明 |
|------|------|--------|------|
| 角色 | `get_by_role()` | ★★★★★ | 基于 ARIA role，最接近用户感知 |
| 文本 | `get_by_text()` | ★★★★☆ | 基于可见文本内容 |
| 标签 | `get_by_label()` | ★★★★☆ | 基于 aria-label 或关联 label |
| 占位符 | `get_by_placeholder()` | ★★★☆☆ | 基于 placeholder 属性 |
| Alt 文本 | `get_by_alt_text()` | ★★★☆☆ | 基于 alt 属性 |
| 标题 | `get_by_title()` | ★★★☆☆ | 基于 title 属性 |
| Test ID | `get_by_test_id()` | ★★★★☆ | 基于 data-testid（可自定义属性名） |
| CSS | `locator("css=...")` | ★★☆☆☆ | CSS 选择器 |
| XPath | `locator("xpath=...")` | ★☆☆☆☆ | XPath 表达式 |

### 5.2 内部选择器引擎

Locator 的选择器在内部被转换为引擎链式语法（`>>` 分隔）：

```python
# 用户代码
page.get_by_role("button", name="Submit")

# 内部选择器
# internal:role=button[name="Submit"]
```

**内部引擎类型**（从 `_locator.py` 源码分析）：

| 引擎 | 前缀 | 示例 |
|------|------|------|
| `internal:role` | ARIA 角色 | `internal:role=button[name="Submit"]` |
| `internal:text` | 文本匹配 | `internal:text="Hello"` |
| `internal:label` | 标签关联 | `internal:label="Username"` |
| `internal:attr` | 属性匹配 | `internal:attr=[alt="Logo"]` |
| `internal:testid` | 测试 ID | `internal:testid=[data-testid=submit-btn]` |
| `internal:has-text` | 包含文本 | `internal:has-text="Hello"` |
| `internal:has-not-text` | 不包含文本 | `internal:has-not-text="Error"` |
| `internal:has` | 包含子元素 | `internal:has=...` |
| `internal:has-not` | 不包含子元素 | `internal:has-not=...` |
| `internal:or` | 逻辑或 | `internal:or=...` |
| `internal:and` | 逻辑与 | `internal:and=...` |
| `internal:chain` | 链式定位 | `internal:chain=...` |
| `internal:control=enter-frame` | 进入 iframe | `internal:control=enter-frame` |
| `internal:describe` | 描述标注 | `internal:describe="登录按钮"` |
| `nth` | 索引选择 | `nth=0` / `nth=-1` |
| `visible` | 可见性过滤 | `visible=true` |

### 5.3 Locator 链式组合

Locator 支持丰富的组合操作：

```python
# 过滤
page.locator(".item").filter(has_text="Product A")
page.locator(".list").filter(has=page.get_by_role("button", name="Delete"))

# 逻辑组合
page.locator(".btn").or_(page.locator(".button"))
page.locator(".visible").and_(page.locator(".enabled"))

# 索引
page.locator(".item").first
page.locator(".item").last
page.locator(".item").nth(3)

# 子定位
page.locator(".list").locator(".item")
page.locator(".list").get_by_text("Item")

# iframe 定位
page.frame_locator("iframe").locator(".button")
page.locator("iframe").content_frame.locator(".button")

# 描述（用于 Trace 和错误信息）
page.locator(".btn").describe("提交按钮").click()
```

### 5.4 自定义选择器引擎

```python
# 注册自定义选择器引擎
await playwright.selectors.register(
    name="tag",
    script="""
    {
        queryAll: (root, selector) => root.querySelectorAll(selector),
    }
    """
)

# 使用自定义引擎
page.locator("tag=div.my-class")
```

### 5.5 Test ID 属性自定义

```python
# 全局自定义 test ID 属性名
playwright.selectors.set_test_id_attribute("data-my-testid")

# 使用
page.get_by_test_id("submit-btn")
```

### 5.6 Aria Snapshot

Playwright 新增了 `aria_snapshot()` 方法，可获取页面的 ARIA 树快照，支持 `mode="ai"` 模式：

```python
# 获取 ARIA 快照
snapshot = page.aria_snapshot()
# - tree
#   heading "Welcome" [level=1]
#   textbox "Username"
#   textbox "Password"
#   button "Log in"

# AI 模式（为 AI 优化的精简快照）
snapshot = page.aria_snapshot(mode="ai")

# Locator 级别的 ARIA 快照
snapshot = page.locator(".form").aria_snapshot()
```

---

## 6. 自动等待与同步机制

### 6.1 自动等待原理

Playwright 的所有交互操作（click、fill、check 等）在执行前都会自动执行**可操作性检查**（Actionability Check），确保元素满足以下条件：

1. **Attached**：元素已挂载到 DOM
2. **Visible**：元素可见
3. **Stable**：元素稳定（不在动画中）
4. **Receives Events**：元素能接收事件（不被其他元素遮挡）
5. **Enabled**：元素未禁用

如果检查不通过，Playwright 会持续重试直到超时。

### 6.2 Waiter 机制

`_waiter.py` 中的 `Waiter` 类是 Playwright 等待机制的核心：

```python
class Waiter:
    def __init__(self, channel_owner, event):
        self._result = asyncio.Future()
        self._logs = []

    def reject_on_timeout(self, timeout, message):
        # 超时后抛出 TimeoutError

    def reject_on_event(self, emitter, event, error, predicate=None):
        # 监听事件，匹配时拒绝（抛出错误）

    def wait_for_event(self, emitter, event, predicate=None):
        # 监听事件，匹配时完成

    def log(self, message):
        # 记录等待日志（用于 Trace 和错误信息）
```

**Waiter 的典型使用模式**：

1. 创建 Waiter 实例
2. 注册拒绝条件（`reject_on_timeout`、`reject_on_event`）
3. 注册等待条件（`wait_for_event`）
4. 等待 `result()` Future 完成
5. 自动清理所有监听器

### 6.3 超时配置层级

```python
# 全局默认超时：30 秒
# 导航超时：30 秒

# 层级覆盖
browser_context.set_default_timeout(10000)      # Context 级别
browser_context.set_default_navigation_timeout(15000)
page.set_default_timeout(5000)                   # Page 级别
page.set_default_navigation_timeout(8000)

# 单次操作超时
page.click("#btn", timeout=3000)
page.goto("https://example.com", timeout=10000)
```

**源码实现**：`TimeoutSettings` 类维护父子层级关系，Page 的 `TimeoutSettings` 以 BrowserContext 的为父级，Context 的以 None 为父级。

### 6.4 加载状态等待

```python
# 三种加载状态
page.wait_for_load_state("domcontentloaded")  # DOM 解析完成
page.wait_for_load_state("load")               # 所有资源加载完成
page.wait_for_load_state("networkidle")        # 网络空闲（无请求超过 500ms）
```

**源码实现**：Frame 维护 `_load_states` 集合，通过 `loadstate` 事件更新。`wait_for_load_state()` 如果目标状态已满足则立即返回。

### 6.5 Expect 断言

Playwright 提供了内置的断言系统，支持自动等待和重试：

```python
# Locator 断言（自动等待）
expect(page.locator(".status")).to_have_text("Success")
expect(page.locator("#btn")).to_be_visible()
expect(page.locator("#input")).to_be_enabled()

# Page 断言
expect(page).to_have_title("Dashboard")
expect(page).to_have_url("**/dashboard")

# API Response 断言
expect(response).to_be_ok()

# 反向断言
expect(page.locator(".error")).not_to_be_visible()

# Soft 断言（不中断测试）
expect.soft(page.locator(".status")).to_have_text("OK")

# 自定义超时
expect(page.locator("#btn")).to_be_visible(timeout=10000)
```

**源码实现**：`_assertions.py` 中的 `AssertionsBase` 通过 `_expect_impl()` 调用 Frame 的 `_expect()` 方法，服务端执行断言逻辑并返回结果。Soft 断言通过 `_soft_scope` 上下文管理器收集错误，需要 pytest-playwright 插件支持。

---

## 7. 网络拦截与 Mock

### 7.1 路由拦截

Playwright 提供了强大的网络请求拦截能力，支持 Page 级别和 BrowserContext 级别：

```python
# 拦截请求
page.route("**/api/**", handler=lambda route: route.fulfill(
    status=200,
    content_type="application/json",
    body='{"status": "ok"}'
))

# 修改请求
page.route("**/api/**", handler=lambda route: route.continue_(
    headers={**route.request.headers, "Authorization": "Bearer token"}
))

# 中止请求
page.route("**/ads.js", handler=lambda route: route.abort())

# 有限次拦截
page.route("**/api/**", handler=handler, times=1)
```

### 7.2 Route 处理器

`Route` 类提供三种处理方式：

| 方法 | 说明 |
|------|------|
| `route.fulfill()` | 直接返回 Mock 响应 |
| `route.continue_()` | 修改后继续请求 |
| `route.abort()` | 中止请求 |
| `route.fallback()` | 传递给下一个路由处理器 |
| `route.fetch()` | 发送请求获取真实响应 |

**fulfill 参数**：`status`、`headers`、`body`（str/bytes）、`json`、`path`（文件路径）、`contentType`、`response`（APIResponse）

**continue_ 参数**：`url`、`method`、`headers`、`postData`

**fetch 参数**：`url`、`method`、`headers`、`postData`、`maxRedirects`、`maxRetries`、`timeout`

### 7.3 路由处理器链

路由处理器按注册顺序的**逆序**匹配（后注册的先匹配），形成处理链：

```python
page.route("**", handler1)  # 第二个匹配
page.route("**/api/**", handler2)  # 第一个匹配
```

`route.fallback()` 将请求传递给下一个匹配的处理器。

### 7.4 WebSocket 拦截

```python
page.route_web_socket("**/ws", handler=lambda ws: ...)
```

`WebSocketRoute` 支持拦截 WebSocket 连接，可 Mock 消息或转发到真实服务器。

### 7.5 HAR 录制与回放

```python
# 录制 HAR
context = browser.new_context(record_har_path="api.har")

# 回放 HAR
page.route_from_har("api.har")

# 回放时未匹配的请求处理
page.route_from_har("api.har", not_found="fallback")  # 继续真实请求

# 更新 HAR
page.route_from_har("api.har", update=True)
```

**HAR 路由实现**：`HarRouter` 类通过 `LocalUtils.har_lookup()` 查找匹配的 HAR 条目，支持 redirect、fulfill、abort 三种动作。

### 7.6 APIRequest（独立 HTTP 客户端）

```python
# 创建独立的 API 请求上下文
api_request_context = await playwright.request.new_context(
    base_url="https://api.example.com",
    extra_http_headers={"Authorization": "Bearer token"}
)

# 发送请求
response = await api_request_context.get("/users")
response = await api_request_context.post("/users", data={"name": "John"})
response = await api_request_context.put("/users/1", form={"name": "Jane"})

# 也可通过 BrowserContext 发送
response = await context.request.get("/api/data")
```

`FormData` 类支持构建 multipart 表单数据。

### 7.7 事件监听

```python
# 监听请求
page.on("request", lambda request: print(f">> {request.method} {request.url}"))

# 监听响应
page.on("response", lambda response: print(f"<< {response.status} {response.url}"))

# 等待特定请求/响应
with page.expect_request("**/api/users") as req_info:
    page.click("#load-users")
request = req_info.value

with page.expect_response("**/api/users") as res_info:
    page.click("#load-users")
response = res_info.value
```

---

## 8. 多浏览器支持

### 8.1 三大浏览器引擎

| 引擎 | BrowserType | 版本 | 特点 |
|------|-------------|------|------|
| Chromium | `playwright.chromium` | 148.0.7778.96 | 最完整功能支持（PDF、Tracing、CDP） |
| Firefox | `playwright.firefox` | 150.0.2 | 独立实现，非 Marionette |
| WebKit | `playwright.webkit` | 26.4 | 独立实现，非 WebDriver |

### 8.2 浏览器启动

```python
# 基本启动
browser = playwright.chromium.launch()

# 有头模式
browser = playwright.chromium.launch(headless=False)

# 指定通道（Chrome/Edge）
browser = playwright.chromium.launch(channel="chrome")
browser = playwright.chromium.launch(channel="msedge")

# 慢动作
browser = playwright.chromium.launch(slow_mo=100)

# 自定义可执行文件
browser = playwright.chromium.launch(executable_path="/path/to/chrome")

# 启动参数
browser = playwright.chromium.launch(args=["--disable-web-security"])
```

### 8.3 远程连接

```python
# 通过 WebSocket 连接
browser = await playwright.chromium.connect("ws://localhost:3000")

# 通过 CDP 连接（仅 Chromium）
browser = await playwright.chromium.connect_over_cdp("http://localhost:9222")

# 连接时选项
browser = await playwright.chromium.connect(
    "ws://...",
    headers={"Authorization": "Bearer token"},
    slow_mo=100,
    timeout=30000
)
```

**源码实现**：`connect()` 方法通过 `JsonPipeTransport` 建立新的 Connection，支持远程浏览器的完整操作。`connect_over_cdp()` 通过 Chrome DevTools Protocol 连接。

### 8.4 BrowserContext 隔离

```python
# 创建隔离的 Context
context1 = browser.new_context()
context2 = browser.new_context()

# 每个 Context 有独立的 Cookie、localStorage、权限等
# 适合并行测试和会话隔离

# 持久化 Context
context = playwright.chromium.launch_persistent_context(
    user_data_dir="/path/to/profile",
    headless=False
)
```

### 8.5 设备模拟

```python
# 使用预置设备参数
iphone = playwright.devices["iPhone 13"]
context = browser.new_context(**iphone)

# 自定义视口和设备参数
context = browser.new_context(
    viewport={"width": 375, "height": 812},
    device_scale_factor=3,
    is_mobile=True,
    has_touch=True,
    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)..."
)
```

---

## 9. 调试与诊断工具

### 9.1 Trace Viewer

Trace Viewer 是 Playwright 最强大的调试工具，可记录测试执行的完整过程：

```python
# 开始追踪
context.tracing.start(name="test-trace", screenshots=True, snapshots=True, sources=True)

# 开始新 chunk
context.tracing.start_chunk(title="Login Step")

# 停止追踪并保存
context.tracing.stop(path="trace.zip")

# 停止 chunk
context.tracing.stop_chunk(path="trace-chunk.zip")

# 分组
context.tracing.group("Login Flow")
# ... 操作 ...
context.tracing.group_end()
```

**追踪内容**：
- **Snapshots**：DOM 快照，可查看每个操作时的页面状态
- **Screenshots**：截图，可回放操作过程
- **Sources**：源代码，可查看调用栈
- **Action Log**：操作日志，包含等待、执行、结果
- **Network**：网络请求日志
- **Console**：控制台输出

**查看追踪**：`playwright show-trace trace.zip` 或上传到 https://trace.playwright.dev

**源码实现**：`_tracing.py` 中的 `Tracing` 类管理追踪生命周期。`start()` 发送 `tracingStart` + `tracingStartChunk` 命令，`stop()` 发送 `tracingStopChunk` + `tracingStop`。本地模式直接写入文件，远程模式通过 Artifact 传输。支持 live 模式（实时追踪）。

### 9.2 Debugger

```python
# 访问调试器
context.debugger.request_pause()  # 请求暂停
context.debugger.resume()         # 继续
context.debugger.next()           # 单步执行
context.debugger.run_to(location) # 运行到指定位置

# 获取暂停详情
details = context.debugger.paused_details
```

### 9.3 page.pause()

```python
# 暂停执行，打开 Playwright Inspector
page.pause()
```

`pause()` 临时将超时设为 0（无限等待），打开 Inspector 界面供交互式调试。

### 9.4 Console 与 Page Error

```python
# 获取所有控制台消息
messages = page.console_messages()
errors = page.page_errors()

# 清空
page.clear_console_messages()
page.clear_page_errors()
```

### 9.5 Pick Locator

```python
# 交互式元素选择器
locator = page.pick_locator()  # 打开选择器，用户点击元素后返回 Locator
page.cancel_pick_locator()     # 取消选择
```

### 9.6 Highlight

```python
# 高亮元素
page.locator(".btn").highlight()
page.locator(".btn").hide_highlight()
```

### 9.7 环境变量调试

- `DEBUG=pw:api`：打印 API 调用日志
- `DEBUGP`：打印所有通信消息（PipeTransport 序列化/反序列化时）
- `PWDEBUG=1`：启用调试模式

---

## 10. 测试框架集成

### 10.1 pytest-playwright

Playwright 官方提供 `pytest-playwright` 插件，提供以下 fixture：

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `playwright` | session | Playwright 实例 |
| `browser` | session | 浏览器实例 |
| `browser_context` | function | 浏览器上下文（每个测试独立） |
| `page` | function | 页面实例（每个测试独立） |
| `context` | function | 同 browser_context |
| `new_page` | function | 创建新页面 |

**CLI 选项**：
- `--browser chromium/firefox/webkit`：指定浏览器
- `--headed`：有头模式
- `--browser-channel`：浏览器通道

### 10.2 测试架构（本项目）

项目自有的测试架构（`tests/` 目录）：

- **测试服务器**：`tests/server.py` 提供本地 HTTP/HTTPS 服务器
- **conftest.py**：
  - `pytest_generate_tests`：自动参数化浏览器类型
  - `browser_name` fixture：从 CLI 选项获取
  - `headless` fixture：控制有头/无头模式
  - `skip_by_browser` / `skip_by_platform`：条件跳过
  - `assert_to_be_golden`：截图对比
  - `RemoteServer`：远程浏览器服务器
- **测试分类**：
  - `tests/async/`：异步 API 测试（约 80+ 测试文件）
  - `tests/sync/`：同步 API 测试（约 50+ 测试文件）
  - `tests/common/`：通用测试
- **测试标记**：`skip_browser`、`only_browser`、`skip_platform`、`only_platform`
- **CI 重试**：CI 环境下自动重试 3 次

### 10.3 并行测试

```bash
# 使用 pytest-xdist 并行
pytest --numprocesses 4

# 使用 pytest-playwright 的并行 worker
pytest --browser chromium --browser firefox  # 多浏览器并行
```

BrowserContext 的隔离性天然支持并行测试——每个测试使用独立的 Context，互不干扰。

---

## 11. 在 UI-AI 自动化测试中的应用价值

> 本章是本报告的重点章节，详细分析 Playwright-Python 在 AI 驱动的 UI 自动化测试场景中的应用价值。

### 11.1 作为 AI 测试框架的底层浏览器驱动

#### 11.1.1 完备的浏览器控制能力

Playwright 提供了浏览器自动化的**完整能力栈**，是构建 AI 测试框架的理想底层驱动：

| 能力维度 | Playwright 支持 | AI 测试框架需求 |
|----------|----------------|----------------|
| 页面导航 | `goto`、`go_back`、`go_forward`、`reload` | ✅ 完全匹配 |
| 元素交互 | click、fill、type、check、select 等 20+ 操作 | ✅ 完全匹配 |
| 等待同步 | 自动等待、`wait_for_*`、`expect` 断言 | ✅ 完全匹配 |
| 网络控制 | route、fulfill、continue、abort、HAR | ✅ 完全匹配 |
| 多标签页 | `expect_popup`、`pages` 属性 | ✅ 完全匹配 |
| iframe | `frame_locator`、`content_frame` | ✅ 完全匹配 |
| 文件操作 | 上传、下载、截图、PDF | ✅ 完全匹配 |
| 设备模拟 | viewport、touch、geolocation、locale | ✅ 完全匹配 |
| 执行 JS | `evaluate`、`evaluate_handle`、`expose_binding` | ✅ 完全匹配 |

#### 11.1.2 双模式 API 适配不同 AI 架构

```python
# 同步模式：适合简单的线性 AI Agent
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    # AI Agent 顺序执行测试步骤
    page.goto("https://example.com")
    page.click("#login")
    page.fill("#username", "test_user")
    page.click("#submit")

# 异步模式：适合并发 AI Agent
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch()
    # 多个 AI Agent 并发操作不同页面
    page1 = await browser.new_page()
    page2 = await browser.new_page()
    await asyncio.gather(
        agent1.run(page1),
        agent2.run(page2)
    )
```

#### 11.1.3 Context 隔离实现测试并行

```python
# 每个 AI Agent 使用独立的 BrowserContext
async def ai_test_agent(playwright, test_config):
    context = await playwright.chromium.new_context(
        storage_state=test_config.auth_state,  # 独立登录态
        viewport={"width": 1920, "height": 1080},
    )
    page = await context.new_page()
    # Agent 在隔离环境中执行测试
    result = await agent.execute(page, test_config)
    await context.close()
    return result

# 并行执行多个 Agent
results = await asyncio.gather(*[
    ai_test_agent(playwright, config)
    for config in test_configs
])
```

### 11.2 元素定位能力与 AI 视觉定位的互补

#### 11.2.1 语义化定位与视觉定位的互补

| 定位方式 | 优势 | 劣势 | AI 互补价值 |
|----------|------|------|-------------|
| `get_by_role()` | 语义化、接近用户感知 | 依赖 ARIA 实现 | AI 可补充缺失的 ARIA |
| `get_by_text()` | 自然语言匹配 | 文本变化时脆弱 | AI 可理解语义等价文本 |
| CSS/XPath | 精确、灵活 | 依赖 DOM 结构 | AI 可处理结构变化 |
| AI 视觉定位 | 不依赖 DOM 结构 | 精度有限、速度慢 | 补充传统定位的盲区 |

#### 11.2.2 Aria Snapshot 与 AI 的结合

```python
# 获取页面的 ARIA 树
snapshot = page.aria_snapshot(mode="ai")
# 输出示例：
# - heading "登录" [level=1]
# - textbox "用户名"
# - textbox "密码"
# - button "登录"
# - link "忘记密码"

# AI 可基于 ARIA 快照理解页面结构
# 1. 将 ARIA 快照发送给 LLM
# 2. LLM 生成定位策略
# 3. 执行定位和操作
```

**`aria_snapshot(mode="ai")`** 是 Playwright 专门为 AI 场景设计的功能，输出精简的 ARIA 树，非常适合作为 LLM 的输入。

#### 11.2.3 混合定位策略

```python
class AIHybridLocator:
    """AI + Playwright 混合定位器"""

    async def locate(self, page, description: str):
        # 策略 1：尝试语义化定位
        locator = page.get_by_role("button", name=description)
        if await locator.count() > 0:
            return locator

        # 策略 2：尝试文本定位
        locator = page.get_by_text(description)
        if await locator.count() > 0:
            return locator

        # 策略 3：AI 视觉定位（截图 + AI 推理）
        screenshot = await page.screenshot()
        coordinates = await ai_model.locate_element(screenshot, description)
        return page.locator(f"//body/*[contains(@style, 'left:{coordinates.x}')]")


        # 策略 4：ARIA 快照 + LLM 推理
        snapshot = await page.aria_snapshot(mode="ai")
        selector = await llm.generate_selector(snapshot, description)
        return page.locator(selector)
```

#### 11.2.4 pick_locator 与 AI 交互

```python
# pick_locator 可用于 AI 辅助的交互式元素选择
selector = await page.pick_locator()
# AI 可利用此功能让用户在训练阶段标注元素
```

### 11.3 网络拦截在测试 Mock 中的应用

#### 11.3.1 AI 测试中的 Mock 策略

```python
class AIMockController:
    """AI 测试 Mock 控制器"""

    def __init__(self, page):
        self.page = page
        self.mock_scenarios = {}

    async def mock_api(self, endpoint: str, response_data: dict, scenario: str = "default"):
        """Mock API 端点"""
        self.mock_scenarios[endpoint] = scenario

        async def handler(route):
            # AI 可根据场景动态调整响应
            if scenario == "error":
                await route.fulfill(status=500, json={"error": "Internal Server Error"})
            elif scenario == "delayed":
                await asyncio.sleep(2)  # 模拟延迟
                await route.fulfill(status=200, json=response_data)
            else:
                await route.fulfill(status=200, json=response_data)

        await self.page.route(f"**/api/{endpoint}", handler)

    async def mock_with_ai_judgment(self, endpoint: str):
        """AI 判断是否需要 Mock"""
        async def handler(route):
            request = route.request
            # AI 分析请求，决定是否 Mock
            should_mock = await ai_model.should_mock(request.url, request.method)
            if should_mock:
                mock_response = await ai_model.generate_mock_response(request)
                await route.fulfill(status=200, json=mock_response)
            else:
                await route.continue_()

        await self.page.route(f"**/api/{endpoint}", handler)
```

#### 11.3.2 HAR 回放在 AI 测试中的价值

```python
# 1. 录制真实 API 交互
context = browser.new_context(record_har_path="baseline.har")
# ... 执行测试操作 ...
context.close()

# 2. AI 测试时回放 HAR，确保稳定的测试环境
page.route_from_har("baseline.har", not_found="fallback")

# 3. AI 可对比 HAR 与实际响应的差异
page.route("**/api/**", handler=lambda route: compare_with_har(route, "baseline.har"))
```

#### 11.3.3 网络条件模拟

```python
# 模拟慢速网络（通过 route.fetch + 延迟）
async def slow_network_handler(route):
    start = time.time()
    response = await route.fetch()
    elapsed = time.time() - start
    if elapsed < 3000:  # 确保至少 3 秒延迟
        await asyncio.sleep(3000 - elapsed)
    await route.fulfill(
        status=response.status,
        headers=response.headers,
        body=await response.body()
    )

page.route("**/api/**", slow_network_handler)
```

### 11.4 Trace 在测试诊断中的价值

#### 11.4.1 AI 测试失败诊断

```python
class AITestRunner:
    """AI 测试运行器，集成 Trace 诊断"""

    async def run_test(self, context, test_fn):
        # 开始追踪
        await context.tracing.start(
            name=test_fn.__name__,
            screenshots=True,
            snapshots=True,
            sources=True
        )

        try:
            await test_fn(context)
        except Exception as e:
            # 测试失败时保存 Trace
            trace_path = f"traces/{test_fn.__name__}_failure.zip"
            await context.tracing.stop(path=trace_path)

            # AI 分析 Trace
            diagnosis = await ai_model.analyze_trace(trace_path, str(e))
            return {"status": "failed", "error": str(e), "diagnosis": diagnosis}
        else:
            # 测试成功时丢弃 Trace
            await context.tracing.stop()
            return {"status": "passed"}
```

#### 11.4.2 Trace 分组与 AI 步骤标注

```python
# AI 可为每个测试步骤创建 Trace 分组
async def ai_test_with_tracing(context):
    tracing = context.tracing

    await tracing.group("1. 打开登录页")
    page = await context.new_page()
    await page.goto("https://example.com/login")
    await tracing.group_end()

    await tracing.group("2. 输入凭据")
    await page.fill("#username", "test_user")
    await page.fill("#password", "test_pass")
    await tracing.group_end()

    await tracing.group("3. 提交登录")
    await page.click("#submit")
    await tracing.group_end()
```

#### 11.4.3 Screencast 在 AI 测试中的价值

```python
# 实时录屏 + AI 实时分析
frames = []

def on_frame(frame):
    frames.append(frame["data"])
    # AI 实时分析帧
    if len(frames) % 30 == 0:  # 每秒分析一次（30fps）
        ai_model.analyze_frame(frame["data"])

page.screencast.start(onFrame=on_frame, quality=80)

# Screencast 还支持叠加层标注
page.screencast.show_overlay("<div style='color:red'>AI 检测到异常</div>")
page.screencast.show_chapter("异常检测", "AI 发现页面加载超时")
```

### 11.5 录制回放能力

#### 11.5.1 Codegen 与 AI 测试用例生成

```bash
# 录制用户操作生成 Python 代码
playwright codegen https://example.com --target python-async
```

AI 测试框架可利用 Codegen 的能力：
1. 用户手动操作 → Codegen 录制 → 生成测试脚本
2. AI 分析测试脚本 → 优化定位策略 → 生成更健壮的测试
3. AI 基于录制数据 → 泛化测试场景 → 生成更多测试变体

#### 11.5.2 视频录制与 AI 回归检测

```python
# 录制视频用于视觉回归
context = browser.new_context(record_video_dir="videos/")

# AI 对比视频帧
baseline_frames = extract_frames("videos/baseline.webm")
current_frames = extract_frames("videos/current.webm")
diff = ai_model.compare_visual_regression(baseline_frames, current_frames)
```

### 11.6 并行测试支持

#### 11.6.1 多 Context 并行

```python
async def parallel_ai_tests(playwright, test_cases):
    """并行执行 AI 测试"""
    browser = await playwright.chromium.launch()

    async def run_single(test_case):
        context = await browser.new_context(
            storage_state=test_case.get("auth_state"),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        try:
            result = await ai_agent.execute(page, test_case)
            return result
        finally:
            await context.close()

    # 并行执行（每个测试独立 Context）
    results = await asyncio.gather(*[
        run_single(tc) for tc in test_cases
    ])

    await browser.close()
    return results
```

#### 11.6.2 多浏览器并行

```python
async def cross_browser_ai_test(playwright, test_case):
    """跨浏览器 AI 测试"""
    results = {}
    for browser_type in [playwright.chromium, playwright.firefox, playwright.webkit]:
        browser = await browser_type.launch()
        context = await browser.new_context()
        page = await context.new_page()
        result = await ai_agent.execute(page, test_case)
        results[browser_type.name] = result
        await browser.close()
    return results
```

### 11.7 与 AI Agent 结合的可能性

#### 11.7.1 Playwright 作为 AI Agent 的 "手" 和 "眼"

```
┌──────────────────────────────────────────────┐
│              AI Agent (大脑)                   │
│  - 理解测试意图                               │
│  - 生成操作策略                               │
│  - 分析执行结果                               │
│  - 自适应调整                                 │
├──────────────────────────────────────────────┤
│          Playwright (手 + 眼)                  │
│  - 执行浏览器操作 (手)                        │
│  - 获取页面状态 (眼)                          │
│  - 截图/ARIA 快照 (眼)                        │
│  - 网络拦截 (环境控制)                        │
│  - Trace 记录 (记忆)                          │
├──────────────────────────────────────────────┤
│          浏览器引擎 (执行环境)                  │
│  - Chromium / Firefox / WebKit                │
└──────────────────────────────────────────────┘
```

#### 11.7.2 AI Agent 集成模式

**模式一：AI 生成 + Playwright 执行**

```python
class AITestGenerator:
    """AI 生成测试代码，Playwright 执行"""

    async def generate_and_run(self, page, test_description: str):
        # 1. AI 获取页面状态
        snapshot = await page.aria_snapshot(mode="ai")
        screenshot = await page.screenshot()

        # 2. AI 生成操作序列
        actions = await llm.generate_actions(
            description=test_description,
            page_snapshot=snapshot,
            page_screenshot=screenshot
        )

        # 3. Playwright 执行操作
        for action in actions:
            await self._execute_action(page, action)

    async def _execute_action(self, page, action):
        match action["type"]:
            case "click":
                locator = page.get_by_role(action["role"], name=action.get("name"))
                await locator.click()
            case "fill":
                locator = page.get_by_role(action["role"], name=action.get("name"))
                await locator.fill(action["value"])
            case "navigate":
                await page.goto(action["url"])
```

**模式二：AI 观察 + Playwright 验证**

```python
class AITestObserver:
    """AI 观察执行过程，实时验证"""

    async def observe_and_verify(self, page, test_steps):
        tracing = page.context.tracing
        await tracing.start(screenshots=True, snapshots=True)

        for step in test_steps:
            await step.execute(page)

            # AI 验证每一步的结果
            snapshot = await page.aria_snapshot(mode="ai")
            is_valid = await ai_model.verify_step(snapshot, step.expected)

            if not is_valid:
                # AI 诊断失败原因
                diagnosis = await ai_model.diagnose(snapshot, step)
                raise AssertionError(f"Step failed: {diagnosis}")
```

**模式三：AI 自愈测试**

```python
class SelfHealingTest:
    """AI 自愈测试：定位失败时自动修复"""

    async def smart_click(self, page, description: str, **kwargs):
        # 尝试多种定位策略
        strategies = [
            lambda: page.get_by_role("button", name=description),
            lambda: page.get_by_text(description),
            lambda: page.locator(f'[aria-label="{description}"]'),
            lambda: page.locator(f'text="{description}"'),
        ]

        for strategy in strategies:
            locator = strategy()
            if await locator.count() > 0:
                await locator.click(**kwargs)
                return

        # 所有策略失败，AI 视觉定位
        screenshot = await page.screenshot()
        coords = await ai_model.locate_element(screenshot, description)
        await page.mouse.click(coords["x"], coords["y"])
```

#### 11.7.3 expose_binding 与 AI 的双向通信

```python
# 将 AI 能力暴露给浏览器页面
async def ai_assist(source, query):
    """页面内 JS 可调用 AI"""
    return await ai_model.query(query)

await page.expose_binding("aiAssist", ai_assist)

# 页面内 JS 调用
result = await page.evaluate("""async () => {
    return await window.aiAssist('这个按钮的用途是什么？');
}""")
```

#### 11.7.4 Clock 控制与 AI 时间场景测试

```python
# AI 测试时间相关功能
await context.clock.install(time="2024-01-01")
await context.clock.fast_forward("02:00")  # 快进 2 小时
await context.clock.pause_at("2024-01-01T12:00:00")  # 暂停到中午
# AI 可测试不同时间点的页面行为
```

#### 11.7.5 Debugger 与 AI 步进调试

```python
# AI 可利用 Debugger 进行智能调试
debugger = context.debugger
await debugger.request_pause()

# 获取暂停详情
details = debugger.paused_details
# AI 分析暂停位置，决定下一步操作
if details and details.get("reason") == "breakpoint":
    await debugger.run_to({"file": "app.js", "line": 42})
else:
    await debugger.resume()
```

### 11.8 关键 API 速查（AI 测试场景）

| 场景 | API | 说明 |
|------|-----|------|
| 获取页面结构 | `page.aria_snapshot(mode="ai")` | AI 友好的 ARIA 树 |
| 获取页面视觉 | `page.screenshot()` | 截图供 AI 分析 |
| 获取元素视觉 | `locator.screenshot()` | 元素级截图 |
| 获取元素位置 | `locator.bounding_box()` | AI 视觉定位坐标 |
| 获取元素文本 | `locator.text_content()` / `locator.inner_text()` | 文本验证 |
| 获取元素属性 | `locator.get_attribute()` | 属性验证 |
| 获取元素数量 | `locator.count()` | 列表验证 |
| 获取元素状态 | `locator.is_visible()` / `is_enabled()` 等 | 状态验证 |
| 执行 JS | `page.evaluate()` | 自定义提取 |
| 网络拦截 | `page.route()` / `route.fulfill()` | Mock API |
| HAR 回放 | `page.route_from_har()` | 稳定测试环境 |
| 追踪记录 | `context.tracing.start/stop()` | 失败诊断 |
| 实时录屏 | `page.screencast.start()` | 实时监控 |
| 暴露函数 | `page.expose_binding()` | AI 与页面通信 |
| 时钟控制 | `context.clock.*` | 时间场景测试 |
| 调试器 | `context.debugger.*` | 智能调试 |

---

## 12. 优势与局限

### 12.1 优势

1. **跨浏览器一致性**：一套 API 驱动三大引擎，减少维护成本
2. **自动等待**：内置智能等待，大幅减少 flaky test
3. **网络拦截**：比 Selenium 更强大的网络控制能力
4. **Context 隔离**：天然支持并行测试，无需额外配置
5. **Trace Viewer**：业界领先的调试诊断工具
6. **双模式 API**：同步/异步自由选择
7. **ARIA 优先定位**：更接近用户感知的定位策略
8. **持续更新**：Microsoft 团队维护，跟进最新浏览器版本
9. **代码生成**：降低编写测试的门槛
10. **HAR 回放**：简化 Mock 数据管理
11. **Screencast**：实时录屏与标注能力
12. **Clock 控制**：时间相关测试的完整支持
13. **Debugger**：内置 JavaScript 调试器
14. **aria_snapshot(mode="ai")**：专门为 AI 场景优化

### 12.2 局限

1. **依赖 Node.js 驱动**：Python 端通过管道与 Node.js 进程通信，增加了启动开销和部署复杂度
2. **同步 API 基于 greenlet**：在 asyncio 事件循环中无法使用同步 API，限制了集成场景
3. **PDF 仅 Chromium**：PDF 生成功能仅 Chromium 支持
4. **CDP 仅 Chromium**：Chrome DevTools Protocol 连接仅 Chromium 支持
5. **Tracing 性能开销**：开启 screenshots 和 snapshots 的 Tracing 会显著影响执行速度
6. **选择器引擎不可跨 Context 共享**：注册的自定义选择器引擎需要为每个 Context 重新注册
7. **无内置视觉对比**：截图对比需要额外工具（如 pixelmatch）
8. **移动端限制**：仅模拟移动浏览器，无法驱动真实移动设备
9. **学习曲线**：Locator 链式语法和内部引擎概念有一定学习成本
10. **调试信息**：同步 API 的错误堆栈可能被 greenlet 干扰

---

## 13. 框架搭建参考建议

### 13.1 推荐架构

```
┌─────────────────────────────────────────────────────┐
│                    测试管理层                         │
│  - 测试用例管理（YAML/JSON 定义）                     │
│  - 测试调度与编排                                    │
│  - 结果收集与报告                                    │
├─────────────────────────────────────────────────────┤
│                    AI 决策层                          │
│  - LLM 集成（意图理解、操作生成、结果验证）           │
│  - 视觉模型集成（元素定位、视觉回归）                 │
│  - 自适应策略（定位自愈、重试策略）                   │
├─────────────────────────────────────────────────────┤
│                   Playwright 适配层                   │
│  - 统一封装 Playwright 操作                          │
│  - 混合定位策略（语义 + 视觉 + AI）                   │
│  - Mock 管理（HAR + 动态 Mock）                      │
│  - Trace/Screencast 集成                             │
├─────────────────────────────────────────────────────┤
│                   Playwright 核心层                   │
│  - Browser/Context/Page 管理                         │
│  - Locator 定位与交互                                │
│  - 网络拦截与 HAR                                    │
│  - 截图/PDF/视频                                     │
└─────────────────────────────────────────────────────┘
```

### 13.2 核心模块设计

#### 13.2.1 浏览器管理器

```python
class BrowserManager:
    """浏览器生命周期管理"""

    def __init__(self):
        self._playwright = None
        self._browsers = {}

    async def start(self, browser_type="chromium", **kwargs):
        self._playwright = await async_playwright().start()
        browser = await getattr(self._playwright, browser_type).launch(**kwargs)
        self._browsers[browser_type] = browser
        return browser

    async def create_isolated_context(self, browser_type="chromium", **kwargs):
        """创建隔离的 BrowserContext"""
        browser = self._browsers[browser_type]
        return await browser.new_context(**kwargs)

    async def stop(self):
        for browser in self._browsers.values():
            await browser.close()
        await self._playwright.stop()
```

#### 13.2.2 智能定位器

```python
class SmartLocator:
    """混合定位策略"""

    def __init__(self, page, ai_model=None):
        self.page = page
        self.ai_model = ai_model

    async def locate(self, description: str, **kwargs):
        """多策略定位"""
        # 1. ARIA 角色定位
        if role := kwargs.get("role"):
            locator = self.page.get_by_role(role, name=description)
            if await locator.count() > 0:
                return locator

        # 2. 文本定位
        locator = self.page.get_by_text(description, exact=kwargs.get("exact", False))
        if await locator.count() > 0:
            return locator

        # 3. Test ID 定位
        if test_id := kwargs.get("test_id"):
            locator = self.page.get_by_test_id(test_id)
            if await locator.count() > 0:
                return locator

        # 4. AI 视觉定位（兜底）
        if self.ai_model:
            return await self._ai_locate(description)

        raise LocatorError(f"Cannot locate: {description}")

    async def _ai_locate(self, description):
        screenshot = await self.page.screenshot()
        coords = await self.ai_model.locate_element(screenshot, description)
        # 使用坐标点击
        await self.page.mouse.click(coords["x"], coords["y"])
```

#### 13.2.3 Mock 管理器

```python
class MockManager:
    """网络 Mock 管理"""

    def __init__(self, context):
        self.context = context
        self._mocks = {}

    async def mock_api(self, url_pattern, response, **kwargs):
        """注册 API Mock"""
        async def handler(route):
            await route.fulfill(
                status=response.get("status", 200),
                headers=response.get("headers", {}),
                json=response.get("body", {})
            )
        await self.context.route(url_pattern, handler)
        self._mocks[url_pattern] = handler

    async def mock_from_har(self, har_path, **kwargs):
        """从 HAR 文件加载 Mock"""
        page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await page.route_from_har(har_path, **kwargs)

    async def cleanup(self):
        """清理所有 Mock"""
        await self.context.unroute_all()
```

#### 13.2.4 诊断管理器

```python
class DiagnosticsManager:
    """测试诊断管理"""

    def __init__(self, context):
        self.context = context
        self._tracing_active = False

    async def start_tracing(self, name="test", **kwargs):
        await self.context.tracing.start(
            name=name,
            screenshots=kwargs.get("screenshots", True),
            snapshots=kwargs.get("snapshots", True),
            sources=kwargs.get("sources", True),
        )
        self._tracing_active = True

    async def stop_tracing(self, path=None):
        if self._tracing_active:
            if path:
                await self.context.tracing.stop(path=path)
            else:
                await self.context.tracing.stop()
            self._tracing_active = False

    async def capture_failure_state(self, test_name, error):
        """捕获失败状态用于 AI 诊断"""
        trace_path = f"traces/{test_name}_failure.zip"
        await self.stop_tracing(path=trace_path)

        page = self.context.pages[0] if self.context.pages else None
        state = {
            "error": str(error),
            "trace_path": trace_path,
            "url": page.url if page else None,
            "aria_snapshot": await page.aria_snapshot(mode="ai") if page else None,
            "console_errors": await page.page_errors() if page else [],
        }
        return state
```

### 13.3 最佳实践建议

1. **优先使用 Locator API**：Locator 具有自动等待和严格模式，比 ElementHandle 更可靠
2. **使用 get_by_role 优先**：语义化定位最接近用户感知，也最稳定
3. **合理使用 Trace**：开发调试时全量 Trace，CI 中仅失败时保存
4. **Context 隔离**：每个测试使用独立 Context，避免状态污染
5. **HAR 回放**：对外部依赖的 API 使用 HAR 回放，确保测试稳定性
6. **aria_snapshot(mode="ai")**：AI 场景下优先使用 AI 模式的 ARIA 快照
7. **避免硬编码等待**：使用 `wait_for_*` 和 `expect` 替代 `wait_for_timeout`
8. **利用 expose_binding**：将 AI 能力暴露给浏览器，实现双向通信
9. **Screencast 标注**：利用 show_overlay 和 show_chapter 为 AI 分析提供上下文
10. **Clock 控制**：时间相关测试使用 Clock API 而非等待真实时间

---

## 附录：源码文件索引

| 文件 | 行数 | 核心职责 |
|------|------|---------|
| `_connection.py` | 667 | 通信核心：Connection、Channel、ChannelOwner、消息收发 |
| `_page.py` | 1613 | Page 类：页面操作、事件、路由、截图、PDF |
| `_locator.py` | 996 | Locator/FrameLocator：定位器、选择器引擎、get_by_* |
| `_frame.py` | 952 | Frame 类：帧操作、导航等待、元素查询 |
| `_browser.py` | 293 | Browser 类：浏览器管理、Context 创建、Tracing |
| `_browser_type.py` | 370 | BrowserType：启动、连接、参数处理 |
| `_browser_context.py` | ~800 | BrowserContext：Context 管理、路由、存储状态 |
| `_network.py` | ~600 | Request/Response/Route：网络请求拦截与 Mock |
| `_waiter.py` | 200 | Waiter：等待机制核心 |
| `_tracing.py` | 281 | Tracing：追踪录制与管理 |
| `_transport.py` | 184 | PipeTransport：管道通信传输 |
| `_assertions.py` | ~300 | Assertions：断言系统（Locator/Page/APIResponse） |
| `_sync_base.py` | ~200 | SyncBase：同步 API 基类、greenlet 集成 |
| `_impl_to_api_mapping.py` | 158 | ImplToApiMapping：impl→API 对象映射 |
| `_greenlets.py` | 48 | Greenlet 类型定义：Main/Route/Event/LocatorHandler |
| `_object_factory.py` | 108 | create_remote_object：远程对象工厂 |
| `_selectors.py` | 67 | Selectors：选择器引擎注册、test ID 配置 |
| `_fetch.py` | ~400 | APIRequest/APIRequestContext：HTTP 客户端 |
| `_har_router.py` | 122 | HarRouter：HAR 回放路由 |
| `_screencast.py` | 144 | Screencast：实时录屏与标注 |
| `_clock.py` | 104 | Clock：时间控制 |
| `_debugger.py` | 54 | Debugger：JavaScript 调试器 |
| `_driver.py` | 41 | 驱动进程管理 |
| `_api_structures.py` | ~200 | TypedDict 定义：Cookie、StorageState 等 |
