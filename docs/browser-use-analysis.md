# Browser-Use 开源项目深度分析报告

> 基于 browser-use v0.13.1 源码分析 | 分析日期：2026-06-11

---

## 1. 项目概述

### 1.1 项目定位

Browser-Use 是一个 **AI 驱动的浏览器自动化 Agent 框架**，其核心理念是"告诉计算机要做什么，它就会完成"（Tell your computer what to do, and it gets it done）。项目通过 LLM（大语言模型）理解用户任务，自主操控浏览器完成网页交互、数据提取、表单填写等复杂操作。

项目在 GitHub 上拥有极高的关注度，核心架构为：

```
Python API → Agent Loop → LLM Decision → Browser Action → Web Task Done
```

v0.13 版本引入了基于 Rust 核心的 Beta Agent，架构变为：

```
Python API → Rust Core → Browser Harness → Web Task Done
```

### 1.2 核心特性

- **自然语言驱动**：用户只需描述任务，Agent 自主规划并执行
- **多 LLM 支持**：ChatBrowserUse、OpenAI、Anthropic、Google Gemini、DeepSeek、Groq、Ollama 等
- **视觉理解**：支持截图分析，AI 可"看到"页面内容
- **智能元素定位**：基于 DOM 序列化 + Accessibility Tree，而非脆弱的 CSS 选择器
- **MCP 协议集成**：可接入外部 MCP Server 扩展工具能力
- **安全机制**：敏感数据保护、域名过滤、循环检测
- **生产就绪**：Cloud 浏览器、Sandbox 部署、代理轮换

### 1.3 许可证

MIT License，开源免费使用。

---

## 2. 核心架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                      User Task                          │
│                    (自然语言描述)                         │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    Agent (核心)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ SystemPrompt │  │MessageManager│  │  AgentState  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ LoopDetector │  │   Planner    │  │    Judge     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└──────────┬────────────────┬────────────────────────────┘
           │                │
           ▼                ▼
┌──────────────────┐  ┌──────────────────────────────────┐
│   LLM (决策层)   │  │         Tools (执行层)            │
│  - ChatBrowserUse│  │  - search / navigate / click     │
│  - ChatOpenAI    │  │  - input / scroll / extract      │
│  - ChatAnthropic │  │  - evaluate / screenshot         │
│  - ChatGoogle    │  │  - write_file / read_file        │
│  - ...           │  │  - MCP Tools / Custom Tools      │
└──────────────────┘  └──────────┬───────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────┐
│              BrowserSession (浏览器控制层)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  DomService  │  │  Watchdogs   │  │  EventBus    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ CDP Session  │  │ Screenshot   │  │  FileSystem  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│              Chromium Browser (CDP 协议)                │
│         cdp-use 库 → Chrome DevTools Protocol           │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Agent 循环机制（感知-决策-执行）

Agent 的核心运行循环遵循经典的 **感知-决策-执行（Perceive-Reason-Act）** 模式，实现在 `Agent.run()` 和 `Agent.step()` 方法中：

```
run(max_steps=500)
  │
  ├── 初始化: 启动浏览器、注册 Watchdog、执行 initial_actions
  │
  └── while n_steps <= max_steps:
        │
        ├── Phase 1: _prepare_context()  ← 感知
        │   ├── 获取浏览器状态 (BrowserStateSummary)
        │   │   ├── DOM 树序列化
        │   │   ├── 截图
        │   │   └── 标签页信息
        │   ├── 更新 Action 模型（页面特定动作）
        │   ├── 构建消息上下文 (MessageManager)
        │   ├── 消息压缩 (可选)
        │   └── 注入循环检测/规划提示
        │
        ├── Phase 2: _get_next_action()  ← 决策
        │   ├── 调用 LLM (带超时和重试)
        │   ├── 解析 AgentOutput
        │   │   ├── thinking (思考)
        │   │   ├── evaluation_previous_goal (评估上一步)
        │   │   ├── memory (记忆)
        │   │   ├── next_goal (下一步目标)
        │   │   └── action[] (动作列表)
        │   └── 回调处理
        │
        ├── Phase 2b: _execute_actions() ← 执行
        │   └── multi_act() → 逐个执行动作
        │       ├── 通过 EventBus 分发事件
        │       ├── Watchdog 监控执行
        │       └── 返回 ActionResult
        │
        └── Phase 3: _post_process()     ← 后处理
            ├── 检查下载文件
            ├── 更新规划状态
            ├── 循环检测
            ├── 失败计数
            └── 记录历史
```

**关键设计要点**：

1. **每步多动作**：`max_actions_per_step`（默认 5）允许 LLM 在一步中输出多个动作，特别适合表单填写场景
2. **Flash Mode**：跳过 evaluation_previous_goal 和 next_goal，仅保留 memory 和 action，速度更快
3. **循环检测**：`ActionLoopDetector` 跟踪动作重复和页面停滞，提供递进式提示
4. **消息压缩**：`MessageCompactionSettings` 在历史过长时自动压缩旧消息
5. **规划系统**：`PlanItem` 支持任务分解，当连续失败或无计划探索时触发重新规划

### 2.3 AgentOutput 数据模型

```python
class AgentOutput(BaseModel):
    thinking: str | None = None           # 内部思考
    evaluation_previous_goal: str | None  # 评估上一步结果
    memory: str | None                    # 跨步记忆
    next_goal: str | None                 # 下一步目标
    current_plan_item: int | None         # 当前计划项
    plan_update: list[str] | None         # 计划更新
    action: list[ActionModel]             # 动作列表（至少1个）
```

三种模式对应不同的 Output Schema：
- **标准模式**：包含 thinking + evaluation + memory + next_goal + action
- **No Thinking 模式**：去掉 thinking 字段
- **Flash Mode**：仅保留 memory + action，大幅减少 token 消耗

---

## 3. 技术栈与依赖

### 3.1 核心依赖

| 类别 | 依赖 | 版本 | 用途 |
|------|------|------|------|
| **LLM SDK** | openai | 2.16.0 | OpenAI/兼容 API 调用 |
| | anthropic | 0.76.0 | Claude 模型调用 |
| | google-genai | 1.65.0 | Gemini 模型调用 |
| | groq | 1.0.0 | Groq 快速推理 |
| | ollama | 0.6.1 | 本地模型调用 |
| **浏览器控制** | cdp-use | 1.4.5 | Chrome DevTools Protocol 客户端 |
| **数据模型** | pydantic | 2.12.5 | 数据验证与序列化 |
| **MCP** | mcp | 1.26.0 | Model Context Protocol 集成 |
| **事件系统** | bubus | 1.5.6 | EventBus 事件总线 |
| **遥测** | posthog | 7.7.0 | 匿名使用数据收集 |
| **文件处理** | pypdf | 6.10.2 | PDF 读取 |
| | reportlab | 4.4.9 | PDF 生成 |
| | python-docx | 1.2.0 | Word 文档处理 |
| | markdownify | 1.2.2 | HTML 转 Markdown |
| **图像** | pillow | 12.2.0 | 截图处理与缩放 |
| **安全** | pyotp | 2.9.0 | 2FA 验证码生成 |
| **序列化** | cloudpickle | 3.1.2 | Sandbox 函数序列化 |

### 3.2 可选依赖

| 类别 | 依赖 | 用途 |
|------|------|------|
| **Rust Core** | browser-use-core==0.13.1 | Beta Agent 的 Rust 运行时 |
| **AWS** | boto3 | Bedrock Claude 调用 |
| **OCI** | oci | Oracle Cloud 模型调用 |
| **视频** | imageio[ffmpeg] + numpy | 录制执行视频 |
| **CLI TUI** | textual | 终端 UI 界面 |

### 3.3 Python 版本要求

Python >= 3.11, < 4.0

---

## 4. Agent 系统深度分析

### 4.1 Agent 初始化流程

`Agent.__init__()` 执行以下关键初始化：

1. **LLM 配置**：默认使用 `ChatBrowserUse`，自动检测模型类型设置 flash_mode
2. **浏览器会话**：创建 `BrowserSession`，支持本地/远程/Cloud 浏览器
3. **工具注册**：创建 `Tools` 实例，注册所有默认浏览器动作
4. **坐标点击**：根据模型名称自动启用坐标点击（Claude Sonnet 4、Gemini 3 Pro 等）
5. **技能集成**：可选的 `SkillService` 从 Browser Use API 加载预定义技能
6. **结构化输出**：支持 `output_model_schema` 定义输出格式
7. **消息管理器**：`MessageManager` 管理对话历史和上下文构建
8. **安全验证**：检查 `sensitive_data` 与 `allowed_domains` 的匹配性

### 4.2 Agent 状态管理

```python
class AgentState(BaseModel):
    agent_id: str                    # UUID 唯一标识
    n_steps: int = 1                 # 当前步数
    consecutive_failures: int = 0    # 连续失败次数
    last_result: list[ActionResult]  # 上一步执行结果
    plan: list[PlanItem]             # 任务计划
    current_plan_item_index: int     # 当前计划项索引
    last_model_output: AgentOutput   # 上一步模型输出
    paused: bool = False             # 暂停状态
    stopped: bool = False            # 停止状态
    loop_detector: ActionLoopDetector # 循环检测器
    message_manager_state: ...       # 消息管理器状态
    file_system_state: ...           # 文件系统状态
```

### 4.3 循环检测机制

`ActionLoopDetector` 是一个软检测系统，不阻止动作执行，而是通过提示引导 LLM 改变策略：

- **动作重复检测**：滚动窗口（默认 20 步）内跟踪动作哈希，在重复 5/8/12 次时递进式提醒
- **页面停滞检测**：通过 `PageFingerprint`（URL + 元素数 + 文本哈希）检测页面无变化
- **动作哈希归一化**：对搜索动作排序关键词、对点击忽略索引、对导航使用完整 URL

### 4.4 规划系统

Agent 内置了轻量级规划系统：

- **PlanItem**：每个计划项有 `pending/current/done/skipped` 状态
- **自动规划**：LLM 可在输出中包含 `plan_update` 和 `current_plan_item`
- **重新规划触发**：连续失败 `planning_replan_on_stall`（默认 3）步后触发
- **探索限制**：无计划探索 `planning_exploration_limit`（默认 5）步后触发

### 4.5 Judge 评估系统

Agent 完成任务后可使用 Judge LLM 评估执行轨迹：

```python
class JudgementResult(BaseModel):
    reasoning: str | None       # 评判理由
    verdict: bool               # 是否成功
    failure_reason: str | None  # 失败原因
    impossible_task: bool       # 任务是否不可能完成
    reached_captcha: bool       # 是否遇到验证码
```

### 4.6 消息压缩

`MessageCompactionSettings` 在对话历史过长时自动压缩：

- 默认每 25 步压缩一次
- 触发阈值：40000 字符（约 10k tokens）
- 保留最近 6 步完整历史
- 压缩摘要最多 6000 字符
- 可使用独立的 `compaction_llm` 降低成本

---

## 5. 浏览器控制机制

### 5.1 架构概览

Browser-Use 不使用 Playwright，而是通过 **cdp-use** 库直接使用 **Chrome DevTools Protocol (CDP)** 控制浏览器。这提供了更底层的控制和更高效的通信。

```
BrowserSession
  ├── BrowserProfile (配置)
  ├── SessionManager (标签页管理)
  ├── EventBus (事件分发)
  ├── Watchdogs (监控守卫)
  └── DomService (DOM 处理)
```

### 5.2 BrowserProfile 配置

核心配置参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `headless` | 自动检测 | 无头模式 |
| `allowed_domains` | None | 域名白名单 |
| `prohibited_domains` | None | 域名黑名单 |
| `highlight_elements` | True | 高亮可交互元素 |
| `minimum_wait_page_load_time` | 0.25s | 最小页面加载等待 |
| `wait_for_network_idle_page_load_time` | 0.5s | 网络空闲等待 |
| `wait_between_actions` | 0.5s | 动作间等待 |
| `paint_order_filtering` | True | 绘制顺序过滤 |
| `cross_origin_iframes` | False | 跨域 iframe 支持 |
| `use_cloud` | False | 使用 Cloud 浏览器 |
| `proxy` | None | 代理设置 |

### 5.3 Watchdog 守卫系统

Browser-Use 实现了丰富的 Watchdog 模式来监控和增强浏览器行为：

| Watchdog | 功能 |
|----------|------|
| `AboutBlankWatchdog` | 处理 about:blank 页面 |
| `CaptchaWatchdog` | CAPTCHA 检测与处理 |
| `CrashWatchdog` | 浏览器崩溃恢复 |
| `DefaultActionWatchdog` | 默认动作处理 |
| `DomWatchdog` | DOM 变更监控 |
| `DownloadsWatchdog` | 下载文件追踪 |
| `HarRecordingWatchdog` | HAR 网络录制 |
| `LocalBrowserWatchdog` | 本地浏览器管理 |
| `PermissionsWatchdog` | 权限管理 |
| `PopupsWatchdog` | 弹窗自动关闭 |
| `RecordingWatchdog` | 视频录制 |
| `ScreenshotWatchdog` | 截图管理 |
| `SecurityWatchdog` | 安全检查（域名过滤） |
| `StorageStateWatchdog` | 存储状态管理 |

### 5.4 EventBus 事件驱动架构

所有浏览器操作通过 `EventBus`（bubus 库）分发事件，Watchdog 监听并处理：

```python
# 点击事件分发
event = browser_session.event_bus.dispatch(ClickElementEvent(node=node))
await event
click_metadata = await event.event_result(raise_if_any=True)
```

这种设计实现了：
- **解耦**：动作触发与执行分离
- **可扩展**：Watchdog 可独立添加/移除
- **可观测**：所有操作都有事件记录

### 5.5 Cloud 浏览器

通过 `use_cloud=True` 可自动配置远程 Cloud 浏览器：

- 自动配置代理轮换
- 内置 CAPTCHA 绕过
- 支持认证 Profile 同步
- 支持国家代码选择代理位置

---

## 6. DOM 处理与元素定位

### 6.1 DOM 序列化流程

Browser-Use 的元素定位策略是其核心创新之一，完全不同于传统的 CSS 选择器/XPath 方式：

```
CDP DOMSnapshot.captureSnapshot()
       │
       ├── DOM.getDocument(depth=-1, pierce=True)
       ├── Accessibility.getFullAXTree() (所有 frames)
       └── Page.getLayoutMetrics() (视口信息)
       │
       ▼
Enhanced DOM Tree 构建
  ├── 合并 DOM + AX + Snapshot 数据
  ├── 计算元素可见性（CSS + 视口阈值）
  ├── 处理 iframe（同源 + 跨源）
  ├── 处理 Shadow DOM（open + closed）
  └── 检测 JS 事件监听器
       │
       ▼
DOMTreeSerializer.serialize_accessible_elements()
  ├── ClickableElementDetector 识别可交互元素
  ├── Paint Order 过滤（移除被遮挡元素）
  ├── 分配元素索引号
  └── 生成 LLM 可读的文本表示
       │
       ▼
SerializedDOMState
  ├── selector_map: {index: EnhancedDOMTreeNode}
  └── llm_representation: 文本化的元素列表
```

### 6.2 元素可见性判断

`DomService.is_element_visible_according_to_all_parents()` 实现了多层可见性检查：

1. **CSS 可见性**：`display: none`、`visibility: hidden`、`opacity: 0`
2. **视口阈值**：元素是否在视口 + 阈值范围（默认 1000px）内
3. **iframe 坐标变换**：递归检查所有父级 iframe 的可见性和滚动偏移
4. **绘制顺序过滤**：`paint_order_filtering` 移除被其他元素遮挡的元素

### 6.3 可交互元素检测

`ClickableElementDetector` 通过以下方式识别可交互元素：

- **Accessibility Tree**：AX 角色判断（button、link、textbox 等）
- **HTML 标签**：`<a>`、`<button>`、`<input>`、`<select>` 等
- **JS 事件监听器**：通过 `getEventListeners()` 检测 click/mousedown 事件
- **ARIA 属性**：`role="button"`、`tabindex` 等

### 6.4 LLM 可读的 DOM 表示

序列化后的 DOM 以索引化的文本格式呈现给 LLM：

```
[1]<button>Submit</button>
[2]<input type="text" placeholder="Search"/>
[3]<a href="/about">About Us</a>
...
```

LLM 通过索引号（如 `[1]`）引用元素，而非 CSS 选择器。这种方式的优势：
- **抗变化**：不依赖具体的 CSS 类名或 XPath
- **语义化**：LLM 理解元素类型和内容
- **简洁**：只展示可交互元素，减少 token 消耗

### 6.5 iframe 与 Shadow DOM 处理

- **同源 iframe**：递归获取 contentDocument，合并到主 DOM 树
- **跨源 iframe**：通过 `Page.getFrameTree()` 获取 frame target，单独构建 DOM 树
- **Shadow DOM**：支持 open 和 closed 两种模式，序列化 shadow root 内容
- **深度限制**：`max_iframe_depth`（默认 5）防止无限递归
- **数量限制**：`max_iframes`（默认 100）防止 iframe 爆炸

### 6.6 Markdown 提取

`markdown_extractor` 模块提供页面内容提取：

- HTML → Markdown 转换（使用 markdownify）
- 噪声过滤（广告、导航等）
- 结构感知分块（`chunk_markdown_by_structure`）
- 支持链接和图片提取

---

## 7. LLM 集成体系

### 7.1 BaseChatModel 协议

所有 LLM 实现必须满足 `BaseChatModel` Protocol：

```python
class BaseChatModel(Protocol):
    model: str
    
    @property
    def provider(self) -> str: ...
    
    async def ainvoke(
        self, messages: list[BaseMessage], 
        output_format: type[T] | None = None
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]: ...
```

### 7.2 支持的 LLM 提供商

| 提供商 | 实现类 | 特殊处理 |
|--------|--------|----------|
| **Browser Use** | `ChatBrowserUse` | 默认推荐，自动 flash_mode |
| **OpenAI** | `ChatOpenAI` | 支持 Responses API 序列化 |
| **Anthropic** | `ChatAnthropic` | Prompt Caching，4.5 模型需 4096+ token |
| **Google** | `ChatGoogle` | Gemini 系列 |
| **DeepSeek** | `ChatDeepSeek` | 不支持 vision，自动禁用 |
| **Groq** | `ChatGroq` | 快速推理 |
| **Ollama** | `ChatOllama` | 本地模型 |
| **AWS Bedrock** | `ChatBedrock` | AWS 托管 Claude |
| **Azure OpenAI** | `ChatAzureOpenAI` | Azure 托管 |
| **Cerebras** | `ChatCerebras` | 快速推理 |
| **Mistral** | `ChatMistral` | Mistral 系列 |
| **LiteLLM** | `ChatLiteLLM` | 统一代理 |
| **OpenRouter** | `ChatOpenRouter` | 模型路由 |
| **Vercel** | `ChatVercel` | AI Gateway |
| **OCI** | `ChatOCI` | Oracle Cloud |

### 7.3 LLM 序列化器

每个 LLM 提供商都有独立的序列化器（serializer），负责：
- 将统一的 `BaseMessage` 转换为提供商特定格式
- 处理 tool calling / function calling 的差异
- 处理 structured output 的 schema 转换
- 支持 Prompt Caching（Anthropic）

### 7.4 Fallback LLM

Agent 支持配置 `fallback_llm`，当主 LLM 调用失败时自动切换：

```python
agent = Agent(
    task="...",
    llm=ChatOpenAI(model='gpt-4.1'),
    fallback_llm=ChatAnthropic(model='claude-sonnet-4-0'),
)
```

### 7.5 页面提取 LLM

`page_extraction_llm` 专门用于 `extract` 动作的内容提取，可使用更小更快的模型：

```python
agent = Agent(
    task="...",
    llm=ChatBrowserUse(),
    page_extraction_llm=ChatOpenAI(model='gpt-4.1-mini'),
)
```

### 7.6 自动配置

- **超时**：根据模型自动设置（Gemini 75-90s、Groq 30s、Claude/O3 90s）
- **截图尺寸**：Claude Sonnet 自动配置 1400x850
- **Vision**：DeepSeek 和部分 Grok 模型自动禁用
- **坐标点击**：Claude Sonnet 4、Gemini 3 Pro 等自动启用

---

## 8. 工具与动作系统

### 8.1 Tools 架构

```
Tools
  ├── Registry (动作注册表)
  │   ├── actions: dict[str, RegistryAction]  # 所有注册的动作
  │   ├── create_action_model()               # 动态创建 ActionModel
  │   └── execute_action()                    # 执行动作
  └── 默认动作实现
```

### 8.2 内置动作列表

| 类别 | 动作 | 说明 |
|------|------|------|
| **导航** | `search` | 搜索引擎查询（DuckDuckGo/Google/Bing） |
| | `navigate` | 导航到 URL |
| | `go_back` | 浏览器后退 |
| | `wait` | 等待指定秒数 |
| **页面交互** | `click` | 点击元素（索引或坐标） |
| | `input` | 输入文本（支持清除/追加） |
| | `upload_file` | 上传文件 |
| | `scroll` | 滚动页面 |
| | `find_text` | 滚动到指定文本 |
| | `send_keys` | 发送特殊按键 |
| **JavaScript** | `evaluate` | 执行自定义 JavaScript |
| **标签页** | `switch` | 切换标签页 |
| | `close` | 关闭标签页 |
| **内容提取** | `extract` | LLM 驱动的结构化数据提取 |
| **视觉** | `screenshot` | 截图 |
| **表单** | `dropdown_options` | 获取下拉选项 |
| | `select_dropdown` | 选择下拉选项 |
| **文件** | `write_file` | 写入文件 |
| | `read_file` | 读取文件 |
| | `replace_file` | 替换文件内容 |
| **搜索** | `search_page` | 页面文本搜索（零 LLM 成本） |
| | `find_elements` | CSS 选择器查询（零 LLM 成本） |
| **PDF** | `save_as_pdf` | 保存为 PDF |
| **完成** | `done` | 完成任务 |

### 8.3 自定义动作

通过 `@tools.action()` 装饰器注册自定义动作：

```python
tools = Tools()

@tools.action(description='Ask human for help with a question')
async def ask_human(question: str, browser_session: BrowserSession) -> ActionResult:
    answer = input(f'{question} > ')
    return ActionResult(extracted_content=f'The human responded with: {answer}')

agent = Agent(task='...', llm=llm, tools=tools)
```

**参数注入机制**：Agent 通过名称匹配自动注入特殊参数：
- `browser_session: BrowserSession` — 当前浏览器会话
- `page_extraction_llm: BaseChatModel` — 提取用 LLM
- `file_system: FileSystem` — 文件系统
- `available_file_paths: list[str]` — 可用文件路径
- `sensitive_data: dict` — 敏感数据
- `extraction_schema: dict` — 提取 schema

### 8.4 ActionResult

所有动作返回 `ActionResult`：

```python
class ActionResult(BaseModel):
    is_done: bool | None = False          # 是否完成任务
    success: bool | None = None           # 是否成功
    error: str | None = None              # 错误信息
    extracted_content: str | None = None  # 提取的内容
    long_term_memory: str | None = None   # 长期记忆
    include_extracted_content_only_once: bool = False  # 仅在下一步展示
    attachments: list[str] | None = None  # 附件文件
    images: list[dict] | None = None      # 图片数据
    metadata: dict | None = None          # 元数据
```

### 8.5 动作执行保护

- **全局超时**：`BROWSER_USE_ACTION_TIMEOUT_S`（默认 180s）防止动作挂起
- **BrowserError 处理**：统一的浏览器错误处理，提取 long_term_memory
- **敏感数据检测**：`_detect_sensitive_key_name()` 在输入时识别敏感字段

### 8.6 动作排除

```python
tools = Tools(exclude_actions=['search', 'wait'])
```

---

## 9. MCP 协议集成

### 9.1 MCPClient

`MCPClient` 负责连接外部 MCP Server 并将其工具注册为 Browser-Use 动作：

```python
from browser_use.mcp.client import MCPClient

mcp_client = MCPClient(
    server_name="playwright",
    command="npx",
    args=["@playwright/mcp@latest"]
)

await mcp_client.register_to_tools(tools)
```

### 9.2 工作流程

1. **连接**：通过 stdio 启动 MCP Server 进程
2. **发现**：调用 `session.list_tools()` 获取工具列表
3. **转换**：将 MCP Tool 的 JSON Schema 转换为 Pydantic Model
4. **注册**：为每个 MCP Tool 创建异步包装函数，注册到 Registry
5. **执行**：当 LLM 调用对应动作时，通过 `session.call_tool()` 调用 MCP Server

### 9.3 MCPServer

Browser-Use 也内置了 MCP Server，允许其他 MCP 客户端调用 Browser-Use 的浏览器能力：

```python
from browser_use.mcp.server import MCPServer
```

### 9.4 类型转换

`_json_schema_to_python_type()` 实现了完整的 JSON Schema → Python 类型映射：
- 基本类型：string→str, number→float, integer→int, boolean→bool
- 复杂类型：object→嵌套 Pydantic Model, array→list[item_type]
- 枚举、可空类型等

---

## 10. 安全机制

### 10.1 敏感数据保护

```python
sensitive_data = {
    'httpbin.org': {
        'telephone': '9123456789',
        'email': 'user@example.com'
    }
}

agent = Agent(
    task='Fill the form...',
    llm=llm,
    sensitive_data=sensitive_data,
)
```

**工作原理**：
- LLM 看到的是键名（如 `telephone`、`email`），而非实际值
- 实际值在执行 `input` 动作时自动替换
- 历史记录中自动脱敏（`redact_sensitive_string`）
- 支持域名绑定凭证，限制数据只在特定域名使用

**安全警告**：如果提供了 `sensitive_data` 但未设置 `allowed_domains`，Agent 会发出安全警告。

### 10.2 域名过滤

```python
browser = Browser(
    allowed_domains=['*.github.com', 'https://example.com'],
    prohibited_domains=['*.gambling-site.net'],
)
```

- **allowed_domains**：白名单，支持通配符（`*.example.com`）
- **prohibited_domains**：黑名单，两者同时设置时白名单优先
- **安全限制**：不允许 TLD 级别通配符（如 `example.*`）
- **性能优化**：100+ 域名列表自动优化为 Set 查找

### 10.3 循环检测

`ActionLoopDetector` 防止 Agent 陷入无限循环：
- 动作重复检测（5/8/12 次递进提醒）
- 页面停滞检测（5 步无变化提醒）
- 不阻止执行，仅通过提示引导 LLM

### 10.4 文件系统安全

- **路径遍历防护**：`FileSystem` 验证文件路径不超出数据目录
- **上传安全**：`upload_file` 动作检查文件是否在 `available_file_paths` 中
- **远程浏览器**：本地文件不会意外上传到远程浏览器

### 10.5 弹窗处理

`PopupsWatchdog` 自动关闭 JavaScript 对话框（alert/confirm/prompt），并将消息传递给 Agent 上下文。

---

## 11. 在 UI-AI 自动化测试中的应用价值

> 本章是本报告的重点，详细分析 Browser-Use 在 UI-AI 自动化测试场景的应用潜力。

### 11.1 AI 驱动的元素定位 vs 传统选择器定位

#### 传统方式的痛点

传统 UI 自动化测试（Selenium、Playwright、Cypress）依赖 CSS 选择器、XPath 或 ID 定位元素：

```python
# 传统方式 — 脆弱、易碎
page.click('#login-form > div:nth-child(3) > button.submit-btn')
page.fill('input[name="email"]', 'user@example.com')
```

**痛点**：
1. **UI 变更即失败**：开发者调整布局/类名，测试立刻失败
2. **动态 ID/类名**：框架生成的随机类名（如 `css-a1b2c3`）无法稳定定位
3. **Shadow DOM**：传统选择器无法穿透 Shadow DOM
4. **iframe**：跨域 iframe 操作复杂
5. **国际化**：多语言场景下文本匹配困难

#### Browser-Use 的 AI 定位方式

Browser-Use 通过 **DOM 序列化 + Accessibility Tree + LLM 理解** 实现语义化定位：

```python
# Browser-Use 方式 — 语义化、自愈
agent = Agent(
    task='Click the submit button on the login form',
    llm=ChatBrowserUse(),
)
```

**LLM 看到的元素表示**：
```
[1]<button type="submit">Sign In</button>
[2]<input type="email" placeholder="Enter your email"/>
[3]<input type="password" placeholder="Password"/>
```

LLM 理解 `[1]` 是"登录表单的提交按钮"，即使：
- CSS 类名从 `submit-btn` 改为 `primary-btn`
- 按钮位置从第 3 个子元素移到第 5 个
- 按钮文本从 "Submit" 改为 "Sign In"

#### 对比总结

| 维度 | 传统选择器 | Browser-Use AI 定位 |
|------|-----------|-------------------|
| **定位方式** | CSS/XPath/ID | 语义理解 + 索引引用 |
| **抗 UI 变更** | ❌ 极脆弱 | ✅ 高度自愈 |
| **Shadow DOM** | ❌ 需特殊处理 | ✅ 自动穿透 |
| **跨域 iframe** | ❌ 复杂 | ✅ 自动处理 |
| **动态内容** | ❌ 等待策略复杂 | ✅ LLM 自适应理解 |
| **可维护性** | ❌ 大量选择器维护 | ✅ 自然语言描述 |
| **执行速度** | ✅ 毫秒级 | ❌ 秒级（LLM 调用） |
| **确定性** | ✅ 完全确定 | ⚠️ 有一定随机性 |
| **成本** | ✅ 零 | ❌ LLM API 费用 |

### 11.2 自愈测试能力

自愈测试（Self-Healing Tests）是 AI 测试工具的核心卖点。Browser-Use 具备以下自愈能力：

#### 11.2.1 元素定位自愈

当页面结构变化时，传统测试会因选择器失效而失败。Browser-Use 的 LLM 能理解元素语义，自动找到等价元素：

```
原始页面: [5]<button class="btn-primary">Submit</button>
变更后:   [12]<button class="css-xyz123" data-testid="submit">提交</button>
```

LLM 仍能理解这是"提交按钮"，因为：
- Accessibility Tree 提供了 role=button
- 按钮文本/ARIA 标签提供了语义信息
- 上下文（表单内的按钮）提供了位置语义

#### 11.2.2 流程自愈

当页面流程变化时（如增加了一个中间步骤），LLM 能自适应：

```
原始流程: 首页 → 登录页 → 仪表盘
变更后:   首页 → Cookie 同意 → 登录页 → 2FA → 仪表盘
```

Agent 会自动处理新增的 Cookie 同意弹窗和 2FA 步骤。

#### 11.2.3 错误恢复

```python
# Agent 内置的错误恢复机制
task = """
Login to the website:
1. If CAPTCHA appears, wait for it to be solved
2. If 2FA is required, use get_2fa_code action
3. If navigation fails, try alternative approach
"""
```

### 11.3 视觉理解与截图分析

#### 11.3.1 Vision 模式

Browser-Use 支持三种 Vision 模式：

```python
# 自动模式：包含截图工具，LLM 按需使用
agent = Agent(task='...', use_vision='auto')

# 始终包含截图
agent = Agent(task='...', use_vision=True)

# 不使用截图
agent = Agent(task='...', use_vision=False)
```

#### 11.3.2 视觉验证场景

```python
# 验证页面布局是否正确
agent = Agent(
    task='Navigate to the homepage and verify that the navigation bar is at the top, the hero image is centered, and the footer is at the bottom',
    llm=ChatBrowserUse(),
    use_vision=True,
)

# 验证视觉回归
agent = Agent(
    task='Take a screenshot of the product page and describe the layout. Check if the product image, title, price, and add-to-cart button are all visible and properly aligned.',
    llm=ChatAnthropic(model='claude-sonnet-4-0'),
)
```

#### 11.3.3 截图动作

```python
# 在测试中主动截图
@tools.action(description='Take screenshot and save with test name')
async def test_screenshot(test_name: str, browser_session: BrowserSession, file_system: FileSystem) -> ActionResult:
    screenshot_bytes = await browser_session.take_screenshot(full_page=False)
    file_name = f'{test_name}.png'
    file_path = file_system.get_dir() / file_name
    file_path.write_bytes(screenshot_bytes)
    return ActionResult(extracted_content=f'Screenshot saved: {file_name}')
```

### 11.4 多步骤复杂测试流程编排

#### 11.4.1 端到端测试

```python
agent = Agent(
    task="""
    Complete the following e2e test:
    1. Navigate to https://shop.example.com
    2. Search for 'wireless headphones'
    3. Add the first result to cart
    4. Go to checkout
    5. Fill shipping info: name=John Doe, address=123 Main St, city=Springfield
    6. Select standard shipping
    7. Verify total is calculated correctly
    8. Do NOT actually place the order - stop at payment page
    9. Extract the order summary as structured data
    """,
    llm=ChatBrowserUse(),
    sensitive_data={
        'shop.example.com': {'email': 'test@example.com', 'password': 'testpass123'}
    },
)
```

#### 11.4.2 结构化输出验证

```python
from pydantic import BaseModel

class TestResult(BaseModel):
    test_name: str
    passed: bool
    page_url: str
    assertions: list[dict]
    error_message: str | None = None

agent = Agent(
    task='Verify the login functionality works correctly',
    llm=ChatBrowserUse(),
    output_model_schema=TestResult,
)

history = await agent.run()
result = history.structured_output
print(f"Test {result.test_name}: {'PASS' if result.passed else 'FAIL'}")
```

#### 11.4.3 初始动作

`initial_actions` 允许在 LLM 循环前执行确定性动作：

```python
agent = Agent(
    task='Test the dashboard after login',
    llm=ChatBrowserUse(),
    initial_actions=[
        {'navigate': {'url': 'https://app.example.com/login'}},
        {'input': {'index': 1, 'text': 'testuser'}},
        {'input': {'index': 2, 'text': 'testpass'}},
        {'click': {'index': 3}},  # Login button
    ],
)
```

### 11.5 与 CI/CD 集成可能性

#### 11.5.1 Headless 模式

```python
browser = Browser(headless=True)
agent = Agent(task='...', llm=ChatBrowserUse(), browser=browser)
```

#### 11.5.2 远程浏览器

```python
# CDP URL 连接
browser = Browser(cdp_url="http://browser-grid:9222")

# Cloud 浏览器
browser = Browser(use_cloud=True)
```

#### 11.5.3 结果提取与断言

```python
history = await agent.run()

# 获取执行结果
result = history.final_result()
is_done = history.is_done()
is_successful = history.is_successful()
has_errors = history.has_errors()

# 获取访问的 URL 列表
urls = history.urls()

# 获取所有截图
screenshots = history.screenshots()

# 获取动作名称
actions = history.action_names()

# 获取提取的内容
content = history.extracted_content()

# 获取错误
errors = history.errors()

# 获取执行步数
steps = history.number_of_steps()

# 获取总耗时
duration = history.total_duration_seconds()
```

#### 11.5.4 CI/CD 集成示例

```python
import asyncio
import json
import sys

async def run_test():
    agent = Agent(
        task='Verify user can add item to cart on https://shop.example.com',
        llm=ChatBrowserUse(),
        browser=Browser(headless=True),
        max_failures=3,
    )
    
    history = await agent.run(max_steps=20)
    
    # 生成测试报告
    report = {
        'test_name': 'add_to_cart',
        'status': 'PASS' if history.is_successful() else 'FAIL',
        'steps': history.number_of_steps(),
        'duration': history.total_duration_seconds(),
        'errors': [e for e in history.errors() if e is not None],
        'urls_visited': history.urls(),
    }
    
    print(json.dumps(report, indent=2))
    sys.exit(0 if history.is_successful() else 1)

asyncio.run(run_test())
```

#### 11.5.5 Sandbox 生产部署

```python
from browser_use import Browser, sandbox, ChatBrowserUse
from browser_use.agent.service import Agent

@sandbox(cloud_proxy_country_code='us')
async def production_test(browser: Browser):
    agent = Agent(
        task='Run smoke tests on the staging environment',
        browser=browser,
        llm=ChatBrowserUse(),
    )
    history = await agent.run()
    return {
        'passed': history.is_successful(),
        'steps': history.number_of_steps(),
    }
```

### 11.6 测试数据提取与验证

#### 11.6.1 结构化数据提取

```python
agent = Agent(
    task="""
    Go to the products page and extract all product information:
    - Product name
    - Price
    - Availability status
    - Rating
    """,
    llm=ChatBrowserUse(),
)

history = await agent.run()
extracted = history.extracted_content()
```

#### 11.6.2 extract 动作

`extract` 动作使用独立的 LLM 从页面 Markdown 中提取结构化数据：

```python
# 在 Agent 任务中指定
task = """
1. Navigate to https://example.com/products
2. Use extract action with query "all product names and prices"
3. Use extract action with query "product categories" and output_schema for structured output
"""
```

支持的高级功能：
- `output_schema`：JSON Schema 定义输出格式
- `already_collected`：分页去重
- `start_from_char`：长内容分块提取
- `extract_links`：提取链接 URL
- `extract_images`：提取图片 URL

#### 11.6.3 页面搜索验证

`search_page` 和 `find_elements` 提供零 LLM 成本的即时验证：

```python
task = """
1. Navigate to https://example.com
2. Use search_page to verify "Welcome" text exists
3. Use find_elements with selector "button.add-to-cart" to verify add-to-cart buttons exist
4. Use extract to get the product count from the page header
"""
```

### 11.7 应用场景总结

| 场景 | 适用性 | 说明 |
|------|--------|------|
| **冒烟测试** | ⭐⭐⭐⭐⭐ | 快速验证核心流程 |
| **探索性测试** | ⭐⭐⭐⭐⭐ | AI 自主探索发现缺陷 |
| **回归测试** | ⭐⭐⭐⭐ | 自愈能力强，但速度较慢 |
| **视觉回归** | ⭐⭐⭐⭐ | Vision 模式支持视觉验证 |
| **跨浏览器测试** | ⭐⭐⭐ | 需配置不同浏览器实例 |
| **性能测试** | ⭐⭐ | 非设计目标 |
| **单元测试** | ⭐ | 不适用 |
| **API 测试** | ⭐⭐ | 可通过 evaluate 动作间接实现 |
| **数据验证** | ⭐⭐⭐⭐⭐ | extract 动作非常强大 |
| **表单测试** | ⭐⭐⭐⭐⭐ | 多动作步骤特别适合 |
| **兼容性测试** | ⭐⭐⭐ | 需手动配置不同环境 |

---

## 12. 优势与局限

### 12.1 核心优势

1. **语义化操作**：LLM 理解页面语义，不依赖脆弱的选择器
2. **自愈能力**：UI 变更后仍能正确操作，大幅降低维护成本
3. **自然语言驱动**：测试用例即自然语言描述，降低编写门槛
4. **视觉理解**：支持截图分析，可验证视觉层面的问题
5. **丰富的工具集**：20+ 内置动作 + 自定义动作 + MCP 扩展
6. **多 LLM 支持**：15+ LLM 提供商，灵活选择
7. **Shadow DOM/iframe 支持**：自动穿透，无需特殊处理
8. **安全机制**：敏感数据保护、域名过滤、循环检测
9. **生产就绪**：Cloud 浏览器、Sandbox 部署、代理轮换
10. **活跃生态**：MIT 开源、活跃社区、持续迭代

### 12.2 核心局限

1. **执行速度**：每步需要 LLM 调用（1-5 秒），远慢于传统自动化
2. **成本**：LLM API 调用产生持续费用，大规模测试成本显著
3. **确定性**：LLM 输出有随机性，同一任务可能产生不同执行路径
4. **可靠性**：复杂页面/动态内容可能导致 Agent 迷失
5. **调试困难**：AI 决策过程不透明，失败原因难以定位
6. **Token 限制**：长对话历史可能超出上下文窗口
7. **并发限制**：每个 Agent 需要独立浏览器实例，资源消耗大
8. **CAPTCHA**：开源版本 CAPTCHA 处理能力有限，需 Cloud 服务
9. **网络依赖**：依赖 LLM API 可用性，离线场景受限（Ollama 除外）
10. **测试断言**：缺乏内置的断言机制，需通过结构化输出间接实现

### 12.3 与竞品对比

| 维度 | Browser-Use | Playwright | Selenium | Cypress |
|------|-------------|-----------|----------|---------|
| **定位方式** | AI 语义 | CSS/XPath | CSS/XPath | CSS/XPath |
| **自愈能力** | ✅ 强 | ❌ 无 | ❌ 无 | ❌ 无 |
| **学习曲线** | 低 | 中 | 中 | 中 |
| **执行速度** | 慢 | 快 | 中 | 快 |
| **确定性** | 中 | 高 | 高 | 高 |
| **视觉验证** | ✅ AI | 需插件 | 需插件 | 需插件 |
| **成本** | 高 | 低 | 低 | 低 |
| **Shadow DOM** | ✅ 自动 | ✅ 手动 | ❌ | ❌ |
| **跨域 iframe** | ✅ 自动 | ✅ 手动 | ❌ | ❌ |
| **多语言支持** | Python | 多语言 | 多语言 | JS/TS |

---

## 13. 框架搭建参考建议

### 13.1 架构建议：混合模式

对于 UI-AI 自动化测试框架，建议采用 **传统自动化 + AI 增强** 的混合架构：

```
┌─────────────────────────────────────────────────┐
│              Test Orchestrator                   │
│  (测试调度、结果收集、报告生成)                    │
└──────────┬──────────────────┬───────────────────┘
           │                  │
           ▼                  ▼
┌──────────────────┐  ┌──────────────────────────┐
│  Fast Path       │  │  AI Path                 │
│  (Playwright)    │  │  (Browser-Use)           │
│                  │  │                          │
│  - 确定性测试    │  │  - 探索性测试             │
│  - 高频回归      │  │  - 自愈测试               │
│  - 性能测试      │  │  - 视觉验证               │
│  - API 测试      │  │  - 复杂流程编排           │
│                  │  │  - 数据提取验证           │
└──────────────────┘  └──────────────────────────┘
```

### 13.2 分层策略

| 层级 | 工具 | 场景 | 原因 |
|------|------|------|------|
| **L1 冒烟测试** | Browser-Use | 核心流程验证 | 自愈 + 快速编写 |
| **L2 功能测试** | 混合 | 详细功能验证 | 关键路径 AI + 细节传统 |
| **L3 回归测试** | Playwright | 高频回归 | 速度 + 确定性 |
| **L4 探索测试** | Browser-Use | 发现未知缺陷 | AI 自主探索 |

### 13.3 关键技术建议

1. **结构化输出**：使用 `output_model_schema` 定义测试结果格式，便于自动化断言
2. **初始动作**：对确定性步骤（如登录）使用 `initial_actions`，减少 LLM 调用
3. **Flash Mode**：对简单任务启用 `flash_mode=True`，减少 token 消耗
4. **页面提取 LLM**：使用便宜模型做内容提取，贵模型做决策
5. **消息压缩**：启用 `message_compaction` 控制长对话成本
6. **循环检测**：保持 `loop_detection_enabled=True`，防止 Agent 陷入循环
7. **域名限制**：始终设置 `allowed_domains`，防止 Agent 访问意外网站
8. **回调机制**：使用 `register_new_step_callback` 实现实时监控
9. **历史重放**：使用 `history.save_to_file()` 保存执行轨迹，便于调试
10. **并行执行**：使用 `parallel_agents` 模式加速大规模测试

### 13.4 成本优化建议

```python
# 成本优化配置示例
agent = Agent(
    task='...',
    llm=ChatBrowserUse(model='bu-3'),           # 专用模型，性价比最高
    page_extraction_llm=ChatOpenAI(model='gpt-4.1-mini'),  # 便宜模型做提取
    flash_mode=True,                             # 减少输出 token
    use_vision='auto',                           # 按需使用截图
    max_actions_per_step=3,                      # 限制每步动作数
    message_compaction=MessageCompactionSettings( # 自动压缩历史
        enabled=True,
        compact_every_n_steps=15,
    ),
    max_history_items=10,                        # 限制历史长度
)
```

### 13.5 可靠性提升建议

1. **重试机制**：利用 `max_failures` 和 `final_response_after_failure` 自动重试
2. **Fallback LLM**：配置备用模型，主模型失败时自动切换
3. **步骤超时**：设置合理的 `step_timeout` 和 `llm_timeout`
4. **Judge 评估**：启用 `use_judge=True`，让 LLM 评估执行结果
5. **敏感数据**：使用 `sensitive_data` 保护凭证，避免 LLM 泄露
6. **初始 URL**：启用 `directly_open_url=True`，自动从任务中提取 URL

### 13.6 集成建议

```python
# 与 pytest 集成示例
import pytest
from browser_use import Agent, Browser, ChatBrowserUse

@pytest.fixture
def browser():
    b = Browser(headless=True)
    yield b
    # cleanup

@pytest.mark.asyncio
async def test_login_flow(browser):
    agent = Agent(
        task='Login to https://app.example.com with email test@example.com and verify dashboard loads',
        llm=ChatBrowserUse(),
        browser=browser,
        sensitive_data={'app.example.com': {'email': 'test@example.com', 'password': 'testpass'}},
        max_failures=3,
    )
    history = await agent.run(max_steps=15)
    assert history.is_successful(), f"Test failed: {history.errors()}"
```

---

## 附录 A：关键源码文件索引

| 文件路径 | 功能 |
|----------|------|
| `browser_use/agent/service.py` | Agent 核心循环逻辑 |
| `browser_use/agent/views.py` | Agent 数据模型（AgentOutput, ActionResult 等） |
| `browser_use/agent/prompts.py` | System Prompt 和 User Message 构建 |
| `browser_use/agent/message_manager/service.py` | 消息历史管理 |
| `browser_use/agent/judge.py` | Judge 评估系统 |
| `browser_use/agent/system_prompts/` | 系统提示词模板（多模型适配） |
| `browser_use/browser/session.py` | 浏览器会话管理 |
| `browser_use/browser/watchdogs/` | Watchdog 守卫系统 |
| `browser_use/dom/service.py` | DOM 树获取与序列化 |
| `browser_use/dom/serializer/` | DOM 序列化器（元素检测、过滤） |
| `browser_use/dom/enhanced_snapshot.py` | CDP Snapshot 数据增强 |
| `browser_use/dom/markdown_extractor.py` | Markdown 内容提取 |
| `browser_use/tools/service.py` | 工具/动作系统 |
| `browser_use/tools/registry/service.py` | 动作注册表 |
| `browser_use/llm/base.py` | LLM 基类 Protocol |
| `browser_use/llm/openai/chat.py` | OpenAI 实现 |
| `browser_use/llm/anthropic/chat.py` | Anthropic 实现 |
| `browser_use/llm/browser_use/chat.py` | ChatBrowserUse 实现 |
| `browser_use/mcp/client.py` | MCP 客户端集成 |
| `browser_use/mcp/server.py` | MCP 服务端 |
| `browser_use/sandbox/sandbox.py` | Sandbox 部署装饰器 |
| `browser_use/skills/service.py` | 技能服务 |
| `browser_use/config.py` | 配置系统 |
| `browser_use/telemetry/service.py` | 遥测服务 |
| `browser_use/tokens/service.py` | Token 成本计算 |

## 附录 B：系统提示词模板

Browser-Use 根据模型类型和模式选择不同的系统提示词：

| 模板文件 | 适用场景 |
|----------|----------|
| `system_prompt.md` | 标准模式（含 thinking） |
| `system_prompt_no_thinking.md` | 无 thinking 模式 |
| `system_prompt_flash.md` | Flash 模式 |
| `system_prompt_flash_anthropic.md` | Anthropic Flash 模式 |
| `system_prompt_anthropic_flash.md` | Anthropic 4.5 Flash 模式 |
| `system_prompt_browser_use.md` | Browser-Use 专用模型 |
| `system_prompt_browser_use_flash.md` | Browser-Use Flash 模式 |
| `system_prompt_browser_use_no_thinking.md` | Browser-Use 无 thinking |

## 附录 C：Agent 历史记录 API

```python
history = await agent.run()

# 基础查询
history.final_result()              # 最终结果文本
history.is_done()                   # 是否完成
history.is_successful()             # 是否成功
history.has_errors()                # 是否有错误
history.number_of_steps()           # 步数
history.total_duration_seconds()    # 总耗时

# 数据提取
history.urls()                      # 访问的 URL 列表
history.screenshots()               # 截图列表（base64）
history.screenshot_paths()          # 截图路径列表
history.action_names()              # 动作名称列表
history.extracted_content()         # 提取的内容列表
history.errors()                    # 错误列表
history.model_actions()             # 所有动作及参数
history.model_outputs()             # 所有模型输出
history.model_thoughts()            # Agent 思考过程
history.action_results()            # 所有 ActionResult
history.action_history()            # 截断的动作历史

# 结构化输出
history.structured_output           # 解析后的结构化输出
history.get_structured_output(Schema) # 使用指定 Schema 解析

# Judge 评估
history.judgement()                 # Judge 评判结果
history.is_judged()                 # 是否已评判
history.is_validated()              # Judge 是否验证通过

# 持久化
history.save_to_file('path.json')   # 保存到文件
AgentHistoryList.load_from_file('path.json', output_model)  # 从文件加载
```
