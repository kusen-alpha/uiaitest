# Playwright CLI 深度分析报告

> 基于 `@playwright/cli@0.1.14` 源码分析，分析日期：2026-06-11

---

## 1. 项目概述

### 1.1 项目定位

`@playwright/cli` 是由 Microsoft 开发的 Playwright 命令行工具，它将 Playwright 的浏览器自动化能力封装为 CLI 接口，专为 **Coding Agent（编码智能体）** 设计。项目核心目标是让 AI Agent（如 Claude Code、GitHub Copilot 等）能够通过简洁的命令行指令操控浏览器，实现 AI 驱动的 Web 自动化测试和浏览器交互。

### 1.2 与 Playwright MCP 的关系

项目 README 明确区分了 CLI 和 MCP 两种集成模式：

| 维度 | CLI + SKILLs | MCP |
|------|-------------|-----|
| **目标用户** | Coding Agent（编码智能体） | 自主循环 Agent |
| **Token 效率** | 高效，避免加载大型工具 Schema 和冗长的 Accessibility Tree | 较低，需要持续维护浏览器上下文 |
| **适用场景** | 高吞吐编码 Agent，需在有限上下文窗口中平衡浏览器自动化与代码推理 | 探索性自动化、自愈测试、长时间自主工作流 |
| **状态管理** | 无状态命令式，每次调用独立 | 持久状态，丰富内省能力 |
| **核心优势** | 简洁的专用命令，Token 消耗低 | 持续浏览器上下文，迭代推理 |

### 1.3 核心设计哲学

- **Token-efficient**：不强制将页面数据推入 LLM 上下文，通过 Snapshot 机制按需获取页面状态
- **命令式交互**：每个 CLI 命令对应一个明确的浏览器操作，Agent 无需理解复杂的 API Schema
- **SKILL 驱动**：通过 SKILL.md 文件向 AI Agent 提供操作指南，Agent 读取 SKILL 即可自主使用
- **代码生成**：每次操作自动生成对应的 Playwright TypeScript 代码，可直接用于测试文件

### 1.4 项目元信息

| 属性 | 值 |
|------|-----|
| 包名 | `@playwright/cli` |
| 版本 | `0.1.14` |
| 许可证 | Apache-2.0 |
| 作者 | Microsoft Corporation |
| 仓库 | https://github.com/microsoft/playwright-cli |
| 主页 | https://playwright.dev |
| Node.js 要求 | >= 18 |
| Playwright 版本 | 1.61.0-alpha-1781023400000 |

---

## 2. 核心架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                   AI Coding Agent                    │
│          (Claude Code / GitHub Copilot)              │
└──────────────┬──────────────────────┬───────────────┘
               │                      │
               │ 读取 SKILL.md        │ 执行 CLI 命令
               ▼                      ▼
┌──────────────────────┐  ┌───────────────────────────┐
│   SKILL 定义层        │  │   CLI 入口层               │
│  skills/playwright-  │  │   playwright-cli.js        │
│  cli/SKILL.md        │  │   (极简入口，委托给         │
│  + references/       │  │    playwright-core)        │
└──────────────────────┘  └──────────┬────────────────┘
                                     │ require
                                     ▼
                          ┌───────────────────────────┐
                          │   Playwright Core 层       │
                          │  playwright-core/lib/tools │
                          │  /cli-client/program       │
                          │  /cli-daemon/              │
                          │  /mcp/                     │
                          └──────────┬────────────────┘
                                     │
                                     ▼
                          ┌───────────────────────────┐
                          │   浏览器实例层              │
                          │  Chromium / Firefox /      │
                          │  WebKit                    │
                          └───────────────────────────┘
```

### 2.2 入口文件分析

`playwright-cli.js` 是整个项目的唯一入口文件，代码极其精简（仅 21 行有效代码）：

```javascript
const { program } = require('playwright-core/lib/tools/cli-client/program');
const packageJson = require('./package.json');

program({ embedderVersion: packageJson.version });
```

**关键发现**：
- 核心实现完全委托给 `playwright-core` 内部的 `cli-client/program` 模块
- `playwright-cli` 本质上是一个 **thin wrapper（薄封装）**，仅传递 `embedderVersion` 参数
- 真正的 CLI 逻辑、Daemon 进程管理、命令路由等均在 Playwright 主仓库中实现
- 源码位于 [Playwright monorepo](https://github.com/microsoft/playwright) 的 `packages/playwright/src/mcp/terminal` 目录

### 2.3 SKILL 系统架构

SKILL 是 playwright-cli 与 AI Agent 集成的核心机制：

```
skills/playwright-cli/
├── SKILL.md                          # 主 SKILL 定义文件
└── references/                       # 详细参考文档
    ├── element-attributes.md         # 元素属性检查
    ├── playwright-tests.md           # 测试运行与调试
    ├── request-mocking.md            # 请求模拟
    ├── running-code.md               # 自定义代码执行
    ├── session-management.md         # 会话管理
    ├── spec-driven-testing.md        # 规格驱动测试
    ├── storage-state.md              # 存储状态管理
    ├── test-generation.md            # 测试生成
    ├── tracing.md                    # 追踪
    └── video-recording.md            # 视频录制
```

SKILL.md 的 Front Matter 定义了 Agent 的工具权限：

```yaml
---
name: playwright-cli
description: Automate browser interactions, test web pages and work with Playwright tests.
allowed-tools: Bash(playwright-cli:*) Bash(npx:*) Bash(npm:*)
---
```

这意味着 AI Agent 被授权通过 Bash 执行 `playwright-cli`、`npx` 和 `npm` 命令。

### 2.4 Daemon 架构

playwright-cli 采用 **Client-Daemon** 架构：

- **Client**：每次 CLI 调用是一个短暂的 Node.js 进程，负责解析命令、与 Daemon 通信
- **Daemon**：长期运行的浏览器管理进程，维护浏览器实例、会话状态
- **通信**：Client 通过 IPC 与 Daemon 交互，Daemon 管理实际的 Playwright Browser 实例

这种架构使得多次 CLI 调用可以共享同一个浏览器实例，保持会话状态（cookies、localStorage 等）。

### 2.5 开发工作流 SKILL

`.claude/skills/dev/SKILL.md` 定义了仓库自身的开发工作流：

- **Roll 依赖**：更新 Playwright 版本并同步 SKILL 和 README
- **发布流程**：版本号递增、变更日志编写、PR 创建

`scripts/update.js` 是关键的自动化脚本，流程为：
1. 运行 `playwright-cli install --skills` 生成 SKILL 文件
2. 将生成的 SKILL 从 `.claude/skills/playwright-cli/` 复制到 `skills/playwright-cli/`
3. 清理临时生成目录

---

## 3. 技术栈与依赖

### 3.1 运行时依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `playwright` | 1.61.0-alpha-1781023400000 | Playwright 完整包，提供浏览器自动化能力 |
| `playwright-core` | 1.61.0-alpha-1781023400000 | Playwright 核心，提供 CLI Client/Daemon 程序模块 |

### 3.2 开发依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `@playwright/test` | 1.61.0-alpha-1781023400000 | Playwright 测试框架，用于集成测试 |
| `@types/node` | ^25.2.1 | Node.js 类型定义 |

### 3.3 技术栈特征

- **纯 JavaScript**：入口文件使用 CommonJS（`require`），无 TypeScript 编译步骤
- **极简依赖**：仅依赖 playwright 和 playwright-core 两个包
- **Alpha 版本绑定**：使用 Playwright 的 alpha 预发布版本，获取最新 CLI 功能
- **无构建步骤**：项目无需构建，直接运行 `playwright-cli.js`

### 3.4 发布配置

`.npmignore` 配置极其严格，仅发布以下文件：

```
!README.md
!LICENSE
!playwright-cli.js
!skills/**
```

这确保 npm 包体积最小，仅包含运行必需的文件。

---

## 4. CLI 功能分析

### 4.1 命令体系总览

playwright-cli 提供了完整的浏览器操控命令集，按功能分为以下类别：

#### 4.1.1 核心操作（Core）

| 命令 | 功能 | 示例 |
|------|------|------|
| `open [url]` | 打开浏览器，可选导航到 URL | `playwright-cli open https://example.com` |
| `goto <url>` | 导航到指定 URL | `playwright-cli goto https://playwright.dev` |
| `close` | 关闭页面 | `playwright-cli close` |
| `type <text>` | 在可编辑元素中输入文本 | `playwright-cli type "search query"` |
| `click <ref>` | 点击页面元素 | `playwright-cli click e15` |
| `dblclick <ref>` | 双击元素 | `playwright-cli dblclick e7` |
| `fill <ref> <text>` | 填充文本到可编辑元素 | `playwright-cli fill e5 "user@example.com"` |
| `drag <startRef> <endRef>` | 拖拽操作 | `playwright-cli drag e2 e8` |
| `drop <ref> --path=<file>` | 拖放文件到元素 | `playwright-cli drop e4 --path=./image.png` |
| `hover <ref>` | 悬停在元素上 | `playwright-cli hover e4` |
| `select <ref> <val>` | 选择下拉选项 | `playwright-cli select e9 "option-value"` |
| `upload <file>` | 上传文件 | `playwright-cli upload ./document.pdf` |
| `check <ref>` | 勾选复选框/单选按钮 | `playwright-cli check e12` |
| `uncheck <ref>` | 取消勾选 | `playwright-cli uncheck e12` |
| `snapshot` | 捕获页面快照获取元素 ref | `playwright-cli snapshot` |
| `eval <func> [ref]` | 执行 JavaScript 表达式 | `playwright-cli eval "document.title"` |
| `dialog-accept [prompt]` | 接受对话框 | `playwright-cli dialog-accept "ok"` |
| `dialog-dismiss` | 关闭对话框 | `playwright-cli dialog-dismiss` |
| `resize <w> <h>` | 调整浏览器窗口大小 | `playwright-cli resize 1920 1080` |

#### 4.1.2 导航操作（Navigation）

| 命令 | 功能 |
|------|------|
| `go-back` | 后退 |
| `go-forward` | 前进 |
| `reload` | 刷新页面 |

#### 4.1.3 键盘操作（Keyboard）

| 命令 | 功能 |
|------|------|
| `press <key>` | 按键（如 Enter、ArrowDown） |
| `keydown <key>` | 按下键 |
| `keyup <key>` | 释放键 |

#### 4.1.4 鼠标操作（Mouse）

| 命令 | 功能 |
|------|------|
| `mousemove <x> <y>` | 移动鼠标到指定位置 |
| `mousedown [button]` | 按下鼠标 |
| `mouseup [button]` | 释放鼠标 |
| `mousewheel <dx> <dy>` | 滚动鼠标滚轮 |

#### 4.1.5 保存操作（Save as）

| 命令 | 功能 |
|------|------|
| `screenshot [ref]` | 截图（整页或指定元素） |
| `pdf` | 保存为 PDF |

#### 4.1.6 标签页管理（Tabs）

| 命令 | 功能 |
|------|------|
| `tab-list` | 列出所有标签页 |
| `tab-new [url]` | 新建标签页 |
| `tab-close [index]` | 关闭标签页 |
| `tab-select <index>` | 选择标签页 |

#### 4.1.7 存储管理（Storage）

| 类别 | 命令 |
|------|------|
| **Storage State** | `state-save`、`state-load` |
| **Cookies** | `cookie-list`、`cookie-get`、`cookie-set`、`cookie-delete`、`cookie-clear` |
| **LocalStorage** | `localstorage-list`、`localstorage-get`、`localstorage-set`、`localstorage-delete`、`localstorage-clear` |
| **SessionStorage** | `sessionstorage-list`、`sessionstorage-get`、`sessionstorage-set`、`sessionstorage-delete`、`sessionstorage-clear` |

#### 4.1.8 网络操作（Network）

| 命令 | 功能 |
|------|------|
| `route <pattern> [opts]` | 模拟网络请求 |
| `route-list` | 列出活跃路由 |
| `unroute [pattern]` | 移除路由 |

#### 4.1.9 开发者工具（DevTools）

| 命令 | 功能 |
|------|------|
| `console [min-level]` | 列出控制台消息 |
| `requests` | 列出所有网络请求 |
| `request <index>` | 查看特定请求详情 |
| `run-code <code>` | 运行 Playwright 代码片段 |
| `tracing-start/stop` | 追踪录制 |
| `video-start/stop` | 视频录制 |
| `video-chapter` | 添加视频章节标记 |
| `video-show-actions/hide-actions` | 视频中标注操作 |
| `show` | 打开可视化仪表盘 |
| `show --annotate` | 启动标注模式的仪表盘 |
| `generate-locator <ref>` | 生成 Playwright locator |
| `highlight <ref>` | 高亮显示元素 |

### 4.2 元素定位机制

playwright-cli 提供三种元素定位方式：

1. **Ref 引用**（推荐）：通过 `snapshot` 命令获取页面快照，快照中每个可交互元素都有唯一 ref（如 `e15`）
   ```bash
   playwright-cli snapshot    # 获取 ref
   playwright-cli click e15   # 使用 ref 交互
   ```

2. **CSS 选择器**：
   ```bash
   playwright-cli click "#main > button.submit"
   ```

3. **Playwright Locator**：
   ```bash
   playwright-cli click "getByRole('button', { name: 'Submit' })"
   playwright-cli click "getByTestId('submit-button')"
   ```

### 4.3 Snapshot 机制

Snapshot 是 playwright-cli 的核心创新之一，是 Agent 感知页面状态的主要方式：

- **自动输出**：每次命令执行后自动提供当前浏览器状态的 Snapshot
- **按需获取**：可通过 `snapshot` 命令主动获取
- **文件保存**：Snapshot 默认保存为带时间戳的 YAML 文件
- **局部快照**：支持对特定元素进行快照
- **深度控制**：`--depth=N` 限制快照深度以提高效率
- **边界框**：`--boxes` 选项包含元素的 bounding box 信息

输出格式示例：
```
### Page
- Page URL: https://example.com/
- Page Title: Example Domain
### Snapshot
[Snapshot](.playwright-cli/page-2026-02-14T19-22-42-679Z.yml)
```

### 4.4 全局选项

| 选项 | 功能 |
|------|------|
| `--raw` | 剥离页面状态、生成代码和 Snapshot 部分，仅返回结果值 |
| `--json` | 结构化 JSON 输出 |
| `-s=<name>` | 指定会话名称 |
| `--headed` | 有头模式运行 |
| `--persistent` | 持久化浏览器配置 |
| `--config=<file>` | 指定配置文件 |

`--raw` 选项特别适合管道操作：
```bash
playwright-cli --raw eval "JSON.stringify(performance.timing)" | jq '.loadEventEnd - .navigationStart'
TOKEN=$(playwright-cli --raw cookie-get session_id)
```

### 4.5 可视化仪表盘

`playwright-cli show` 命令打开一个可视化仪表盘，提供两种视图：

- **Session Grid**：显示所有活跃会话，每个会话有实时屏幕投射预览、会话名称、当前 URL 和页面标题
- **Session Detail**：选中会话的实时视图，包含标签栏、导航控制（后退、前进、刷新、地址栏）和完整远程控制

`--annotate` 模式启动 UI 审查/设计反馈模式，用户可以在页面上绘制标注框并输入评论，Agent 接收标注截图、快照和用户备注。

---

## 5. AI 集成机制

### 5.1 SKILL 驱动集成

playwright-cli 与 AI Agent 的集成主要通过 **SKILL** 机制实现：

**安装方式**：
```bash
playwright-cli install --skills
```

此命令会在 `.claude/skills/` 目录下生成 SKILL 文件，Claude Code 等 Agent 会自动读取本地安装的 SKILL。

**SKILL-less 模式**：
即使不安装 SKILL，Agent 也能通过 `--help` 自主发现可用命令：
```
Test the "add todo" flow on https://demo.playwright.dev/todomvc using playwright-cli.
Check playwright-cli --help for available commands.
```

### 5.2 SKILL.md 结构分析

SKILL.md 的 Front Matter 定义了 Agent 的操作边界：

```yaml
name: playwright-cli
description: Automate browser interactions, test web pages and work with Playwright tests.
allowed-tools: Bash(playwright-cli:*) Bash(npx:*) Bash(npm:*)
```

- `allowed-tools` 限制 Agent 只能通过 Bash 执行 `playwright-cli`、`npx` 和 `npm` 命令
- 这种设计确保了安全性：Agent 无法直接执行任意系统命令

### 5.3 Agent 交互模式

playwright-cli 支持两种 Agent 交互模式：

#### 5.3.1 直接命令模式

Agent 直接发出 CLI 命令操控浏览器：

```bash
playwright-cli open https://demo.playwright.dev/todomvc/
playwright-cli type "Buy groceries"
playwright-cli press Enter
playwright-cli snapshot
playwright-cli check e21
playwright-cli screenshot
```

#### 5.3.2 测试调试模式

Agent 通过 `--debug=cli` 附加到 Playwright 测试会话：

```bash
# 后台运行测试
PLAYWRIGHT_HTML_OPEN=never npx playwright test --debug=cli
# 附加到测试会话
playwright-cli attach tw-XXXX
# 交互式调试
playwright-cli snapshot
playwright-cli console
playwright-cli requests
```

### 5.4 Token 效率优化

playwright-cli 的设计处处体现 Token 效率优化：

1. **Snapshot 替代完整 DOM**：不将完整 DOM 推入 LLM 上下文，而是提供精简的 Accessibility Snapshot
2. **命令式交互**：每个命令对应一个明确操作，无需冗长的 Schema 描述
3. **按需获取**：Agent 只在需要时获取页面状态，而非持续推送
4. **`--raw` 模式**：进一步精简输出，适合管道处理
5. **深度控制**：`--depth=N` 限制 Snapshot 深度

### 5.5 人机协作模式

`show --annotate` 命令实现了独特的人机协作模式：

- Agent 打开标注模式仪表盘
- 用户在实时页面上绘制标注框并输入评论
- Agent 接收标注截图、被标注区域的 Snapshot 和用户备注
- 适用于 UI 审查、设计反馈、需求澄清等场景

---

## 6. 浏览器管理能力

### 6.1 多浏览器支持

| 浏览器 | 启动方式 |
|--------|---------|
| Chromium | `playwright-cli open --browser=chromium` |
| Chrome | `playwright-cli open --browser=chrome` |
| Firefox | `playwright-cli open --browser=firefox` |
| WebKit | `playwright-cli open --browser=webkit` |
| Microsoft Edge | `playwright-cli open --browser=msedge` |

### 6.2 会话管理

playwright-cli 提供完善的会话管理能力：

- **命名会话**：`-s=<name>` 隔离不同项目的浏览器上下文
- **环境变量**：`PLAYWRIGHT_CLI_SESSION` 设置默认会话名
- **会话列表**：`list` 命令查看所有活跃会话
- **批量关闭**：`close-all` 关闭所有浏览器，`kill-all` 强制终止

每个会话具有独立的：
- Cookies、LocalStorage、SessionStorage、IndexedDB
- 缓存、浏览历史、打开的标签页

### 6.3 浏览器附加模式

`attach` 命令支持连接到已运行的浏览器实例：

| 模式 | 命令 | 说明 |
|------|------|------|
| Channel 附加 | `attach --cdp=chrome` | 连接到本地 Chrome/Edge |
| CDP 端点附加 | `attach --cdp=http://localhost:9222` | 通过 CDP 协议连接 |
| 扩展附加 | `attach --extension=chrome` | 通过 Playwright 扩展连接 |
| 分离 | `detach` | 断开附加但不关闭外部浏览器 |

### 6.4 配置文件

支持 JSON 配置文件（默认路径 `.playwright/cli.config.json`），可配置：

- **浏览器设置**：类型、启动选项、上下文选项、CDP 端点
- **网络设置**：允许/阻止的 Origin、代理
- **超时设置**：操作超时（默认 5000ms）、导航超时（默认 60000ms）
- **输出设置**：视频保存、输出目录、输出模式
- **控制台设置**：日志级别
- **代码生成**：语言选择（TypeScript / none）
- **安全设置**：文件访问限制、Test ID 属性

### 6.5 持久化配置

- **内存模式**（默认）：浏览器配置保存在内存中，关闭即丢失
- **持久化模式**：`--persistent` 将配置保存到磁盘，跨浏览器重启保留
- **自定义目录**：`--profile=<path>` 指定自定义配置目录

---

## 7. 代码生成与录制

### 7.1 自动代码生成

playwright-cli 的核心特性之一是**每个操作自动生成对应的 Playwright TypeScript 代码**：

```bash
playwright-cli fill e1 "user@example.com"
# 输出包含：
# Ran Playwright code:
# await page.getByRole('textbox', { name: 'Email' }).fill('user@example.com');
```

这意味着 Agent 在探索应用时，同时在"录制"可复用的测试代码。

### 7.2 语义化 Locator 生成

生成的代码优先使用语义化 Locator（Role-based），而非脆弱的 CSS 选择器：

```typescript
// 生成（推荐 - 语义化）
await page.getByRole('button', { name: 'Submit' }).click();

// 避免（脆弱 - CSS 选择器）
await page.locator('#submit-btn').click();
```

`generate-locator` 命令可以为任意元素生成 Playwright Locator：

```bash
playwright-cli --raw generate-locator e5
# 输出: getByRole('button', { name: 'Submit' })
```

### 7.3 Spec-Driven Testing 工作流

这是 playwright-cli 最完整的 AI 集成工作流，分为三个阶段：

#### 7.3.1 Planning（规划）

1. 确认工作空间有 Playwright 安装
2. 创建 Seed Test（种子测试）—— 最小化的初始状态测试
3. 通过 `--debug=cli` 启动测试并附加 CLI
4. 探索应用，映射交互面、用户旅程、边缘情况
5. 编写 Spec 文件（`specs/<feature>.plan.md`）

Spec 文件结构：
```markdown
# <Feature> Test Plan

## Application Overview
<功能描述>

## Test Scenarios

### 1. <Group Name>

**Seed:** `tests/seed.spec.ts`

#### 1.1. <kebab-case-scenario-name>

**File:** `tests/<group>/<kebab-case-scenario-name>.spec.ts`

**Steps:**
  1. <用户步骤>
    - expect: <可观察结果>
```

#### 7.3.2 Generate（生成）

1. 读取 Spec 文件
2. 对每个场景，通过 Seed Test 启动浏览器
3. 按照 Spec 的 Steps 逐步执行 `playwright-cli` 命令
4. 收集自动生成的 Playwright TypeScript 代码
5. 为每个 `- expect:` 添加断言
6. 写入测试文件

生成规则：
- 每个场景一个测试文件
- 使用 Spec 中的 describe 名称和 test 名称
- 每个步骤前添加 `// N. <step text>` 注释
- 从 `./fixtures` 或 `@playwright/test` 导入

#### 7.3.3 Heal（修复）

1. 运行测试发现失败
2. 通过 `--debug=cli` 附加到失败测试
3. 诊断失败原因（选择器漂移、时序问题等）
4. 用 `playwright-cli` 修正交互，获取修正后的代码
5. 更新测试文件
6. 与 Spec 对账：纯技术修复不改 Spec，用户可见变更需更新 Spec

### 7.4 视频录制与标注

playwright-cli 提供了强大的视频录制能力：

- **基础录制**：`video-start/stop`
- **章节标记**：`video-chapter` 添加章节标题和描述
- **操作标注**：`video-show-actions` 在视频中标注每个操作
- **高级录制**：通过 `run-code` 使用 `page.screencast` API 实现自定义覆盖层

Screencast Overlay API：
| 方法 | 用途 |
|------|------|
| `page.screencast.showChapter(title, opts)` | 全屏章节卡片，带模糊背景 |
| `page.screencast.showOverlay(html, opts)` | 自定义 HTML 覆盖层 |
| `disposable.dispose()` | 移除粘性覆盖层 |
| `page.screencast.hideOverlays()/showOverlays()` | 临时隐藏/显示所有覆盖层 |

### 7.5 追踪（Tracing）

追踪录制捕获完整的执行细节：

| 类别 | 内容 |
|------|------|
| Actions | 点击、填充、悬停、键盘输入、导航 |
| DOM | 每个操作前后的完整 DOM 快照 |
| Screenshots | 每步的视觉状态 |
| Network | 所有请求、响应、头部、请求体、时序 |
| Console | 所有 console.log/warn/error 消息 |
| Timing | 每个操作的精确时间 |

输出文件：
- `trace-{timestamp}.trace`：操作日志
- `trace-{timestamp}.network`：网络日志
- `resources/`：缓存资源

---

## 8. 在 UI-AI 自动化测试中的应用价值

> 本章重点分析 playwright-cli 在 AI 驱动的 UI 自动化测试场景中的实际应用价值。

### 8.1 AI 驱动的浏览器命令行操作

#### 8.1.1 命令式浏览器操控

playwright-cli 将浏览器操作封装为简洁的命令行指令，使 AI Agent 能够像人类一样"操作"浏览器：

```bash
# AI Agent 自主完成的典型流程
playwright-cli open https://app.example.com/login
playwright-cli snapshot                    # 感知页面状态
playwright-cli fill e1 "admin@test.com"    # 填写用户名
playwright-cli fill e2 "password123"       # 填写密码
playwright-cli click e3                    # 点击登录
playwright-cli snapshot                    # 验证登录结果
```

**核心价值**：
- Agent 无需理解 Playwright API 的复杂签名，只需发出简洁命令
- 命令输出自动包含页面状态反馈，形成闭环控制
- 每次操作自动生成可复用的 TypeScript 代码

#### 8.1.2 感知-决策-执行循环

playwright-cli 天然支持 AI Agent 的感知-决策-执行循环：

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  感知    │────▶│  决策    │────▶│  执行    │
│ snapshot │     │ AI 推理  │     │ click   │
│ console  │     │         │     │ fill    │
│ requests │     │         │     │ type    │
└─────────┘     └─────────┘     └─────────┘
     ▲                                 │
     └─────────────────────────────────┘
              自动反馈（命令输出包含新状态）
```

- **感知**：`snapshot`、`console`、`requests` 获取页面状态
- **决策**：AI Agent 根据状态决定下一步操作
- **执行**：`click`、`fill`、`type` 等命令执行操作
- **反馈**：命令输出自动包含新的页面状态

#### 8.1.3 多会话并行测试

通过命名会话，AI Agent 可以同时管理多个浏览器实例：

```bash
# 并行测试不同用户角色
playwright-cli -s=admin open https://app.example.com
playwright-cli -s=viewer open https://app.example.com

# 管理员操作
playwright-cli -s=admin fill e1 "admin"
playwright-cli -s=admin click e2

# 查看者操作
playwright-cli -s=viewer snapshot
playwright-cli -s=viewer click e5

# 验证权限隔离
playwright-cli -s=admin snapshot
playwright-cli -s=viewer snapshot
```

### 8.2 测试脚本自动生成

#### 8.2.1 交互即录制

playwright-cli 的**交互即录制**模式是其最核心的 AI 测试价值：

Agent 在探索应用时执行的每一个操作，都会自动生成对应的 Playwright TypeScript 代码。这意味着：

1. **零额外成本的代码生成**：Agent 不需要专门的"录制模式"，正常交互即产生代码
2. **语义化 Locator**：生成的代码使用 `getByRole`、`getByTestId` 等语义化定位器，比 CSS 选择器更稳定
3. **即时可用**：生成的代码可以直接复制到测试文件中

```bash
# Agent 交互
playwright-cli fill e1 "user@example.com"
# 自动生成：
# await page.getByRole('textbox', { name: 'Email' }).fill('user@example.com');

playwright-cli click e3
# 自动生成：
# await page.getByRole('button', { name: 'Sign In' }).click();
```

#### 8.2.2 Spec-Driven 自动生成流程

完整的 AI 驱动测试生成流程：

```
Spec 文件 ──▶ AI Agent 读取 ──▶ 逐步执行 CLI 命令 ──▶ 收集生成代码 ──▶ 组装测试文件
    │                                                              │
    │  定义场景和步骤                                               │  包含注释和断言
    │                                                              │
    ▼                                                              ▼
 specs/feature.plan.md                                    tests/group/scenario.spec.ts
```

AI Agent 的工作流程：
1. 读取 Spec 文件中的测试场景
2. 通过 Seed Test 启动浏览器
3. 按照 Spec 的步骤逐步执行 `playwright-cli` 命令
4. 如果步骤与实际应用不符，更新 Spec 以匹配现实
5. 收集自动生成的 TypeScript 代码
6. 为每个 `expect` 添加断言
7. 写入测试文件

#### 8.2.3 断言生成

playwright-cli 提供多种断言生成方式：

```bash
# 获取稳定的 locator
playwright-cli --raw generate-locator e5
# 输出: getByRole('button', { name: 'Submit' })

# 获取元素文本内容
playwright-cli --raw eval "el => el.textContent" e5

# 获取输入值
playwright-cli --raw eval "el => el.value" e5

# 获取 Aria Snapshot
playwright-cli --raw snapshot
```

推荐的断言匹配器：
- `toBeVisible()` — 元素可见
- `toHaveText(text)` — 文本匹配
- `toHaveValue(value)` / `toBeEmpty()` — 输入值匹配
- `toBeChecked()` / `toBeUnchecked()` — 复选框状态
- `toMatchAriaSnapshot(snapshot)` — 页面区域匹配 Aria 快照

### 8.3 与 AI Agent 的协作模式

#### 8.3.1 完全自主模式

AI Agent 完全自主完成测试任务：

```
用户指令: "测试 https://demo.playwright.dev/todomvc/ 的添加待办功能"
                    │
                    ▼
         AI Agent 自主执行:
         1. playwright-cli open https://demo.playwright.dev/todomvc/
         2. playwright-cli snapshot
         3. playwright-cli type "Buy groceries"
         4. playwright-cli press Enter
         5. playwright-cli snapshot
         6. 验证结果，生成测试代码
```

#### 8.3.2 人机协作模式

通过 `show --annotate` 实现人机协作：

```
AI Agent                          用户
   │                               │
   ├── show --annotate ──────────▶ │
   │                               │ (在页面上标注问题区域)
   │ ◀── 标注截图 + Snapshot ──────┤
   │                               │
   ├── 分析标注，调整操作           │
   │                               │
   ├── 继续测试 ─────────────────▶ │
   │                               │
```

适用场景：
- UI 审查：用户指出设计问题
- 需求澄清：用户标注不确定的区域
- 反馈收集：用户对测试结果发表意见

#### 8.3.3 测试调试协作模式

当测试失败时，AI Agent 可以进入调试协作模式：

```bash
# 1. 发现失败测试
PLAYWRIGHT_HTML_OPEN=never npx playwright test

# 2. 调试模式启动
PLAYWRIGHT_HTML_OPEN=never npx playwright test tests/login.spec.ts:15 --debug=cli

# 3. 附加到测试会话
playwright-cli attach tw-XXXX

# 4. 诊断
playwright-cli snapshot     # 元素是否变化？
playwright-cli console      # 应用侧错误？
playwright-cli requests     # 请求是否失败？

# 5. 修正并获取新代码
playwright-cli click e7     # 新的正确操作
# 自动生成修正后的代码

# 6. 更新测试文件
```

#### 8.3.4 Spec-Driven 协作模式

最完整的协作模式，AI Agent 作为测试工程师：

```
用户 ──▶ 提供应用 URL 和测试需求
  │
  ▼
AI Agent ──▶ Planning 阶段
  │          - 探索应用
  │          - 编写 Spec 文件
  │          - 用户审核 Spec
  │
  ▼
AI Agent ──▶ Generate 阶段
  │          - 按 Spec 生成测试代码
  │          - 运行测试验证
  │
  ▼
AI Agent ──▶ Heal 阶段（持续）
             - 修复失败测试
             - 更新 Spec（如需）
             - 与用户确认不确定变更
```

### 8.4 浏览器调试能力

#### 8.4.1 控制台监控

```bash
playwright-cli console           # 列出所有控制台消息
playwright-cli console warning   # 仅显示 warning 及以上级别
```

支持级别：`error`、`warning`、`info`、`debug`

#### 8.4.2 网络请求检查

```bash
playwright-cli requests          # 列出所有网络请求
playwright-cli request 5         # 查看第 5 个请求的详情
```

#### 8.4.3 请求模拟

```bash
# 模拟 404
playwright-cli route "**/*.jpg" --status=404

# 模拟 JSON 响应
playwright-cli route "**/api/users" --body='[{"id":1,"name":"Alice"}]' --content-type=application/json

# 条件响应（通过 run-code）
playwright-cli run-code "async page => {
  await page.route('**/api/login', route => {
    const body = route.request().postDataJSON();
    if (body.username === 'admin') {
      route.fulfill({ body: JSON.stringify({ token: 'mock-token' }) });
    } else {
      route.fulfill({ status: 401, body: JSON.stringify({ error: 'Invalid' }) });
    }
  });
}"
```

#### 8.4.4 JavaScript 执行

```bash
# 执行简单表达式
playwright-cli eval "document.title"

# 执行元素相关表达式
playwright-cli eval "el => el.textContent" e5
playwright-cli eval "el => el.getAttribute('data-testid')" e5

# 执行复杂 Playwright 代码
playwright-cli run-code "async page => {
  await page.context().grantPermissions(['geolocation']);
  await page.context().setGeolocation({ latitude: 37.7749, longitude: -122.4194 });
}"
```

#### 8.4.5 追踪分析

```bash
playwright-cli tracing-start
# ... 执行操作 ...
playwright-cli tracing-stop
```

追踪文件包含：DOM 快照、截图、网络活动、控制台日志、精确时序。

#### 8.4.6 元素高亮与 Locator 生成

```bash
# 高亮元素
playwright-cli highlight e5
playwright-cli highlight e5 --style="outline: 3px dashed red"

# 生成 Locator
playwright-cli generate-locator e5 --raw
# 输出: getByRole('button', { name: 'Submit' })
```

### 8.5 CI/CD 中的命令行集成

#### 8.5.1 Headless 模式

playwright-cli 默认以 Headless 模式运行，天然适合 CI/CD 环境：

```bash
# CI 中运行（默认 headless）
playwright-cli open https://staging.example.com
playwright-cli snapshot
playwright-cli fill e1 "ci-user@test.com"
playwright-cli fill e2 "password"
playwright-cli click e3
playwright-cli screenshot --filename=login-result.png
playwright-cli close
```

#### 8.5.2 环境变量配置

playwright-cli 支持丰富的环境变量配置（以 `PLAYWRIGHT_MCP_` 为前缀），关键 CI/CD 相关变量：

| 环境变量 | 用途 |
|----------|------|
| `PLAYWRIGHT_MCP_HEADLESS` | 是否无头模式 |
| `PLAYWRIGHT_MCP_BROWSER` | 浏览器选择 |
| `PLAYWRIGHT_MCP_CONFIG` | 配置文件路径 |
| `PLAYWRIGHT_MCP_OUTPUT_DIR` | 输出目录 |
| `PLAYWRIGHT_MCP_SAVE_VIDEO` | 保存视频 |
| `PLAYWRIGHT_MCP_SAVE_TRACE` | 保存追踪 |
| `PLAYWRIGHT_MCP_CDP_ENDPOINT` | CDP 端点（连接远程浏览器） |
| `PLAYWRIGHT_MCP_PROXY_SERVER` | 代理服务器 |
| `PLAYWRIGHT_MCP_TIMEOUT_ACTION` | 操作超时 |
| `PLAYWRIGHT_MCP_TIMEOUT_NAVIGATION` | 导航超时 |

#### 8.5.3 管道友好的输出模式

`--raw` 和 `--json` 选项使 playwright-cli 的输出可以被其他工具处理：

```bash
# JSON 输出
playwright-cli list --json

# 原始值提取
TOKEN=$(playwright-cli --raw cookie-get session_id)

# 性能指标
playwright-cli --raw eval "JSON.stringify(performance.timing)" | jq '.loadEventEnd - .navigationStart'

# 比较快照
playwright-cli --raw snapshot > before.yml
playwright-cli click e5
playwright-cli --raw snapshot > after.yml
diff before.yml after.yml
```

#### 8.5.4 存储状态复用

在 CI/CD 中，可以通过存储状态避免重复登录：

```bash
# 首次：登录并保存状态
playwright-cli open https://app.example.com/login
playwright-cli fill e1 "user@example.com"
playwright-cli fill e2 "password"
playwright-cli click e3
playwright-cli state-save auth.json
playwright-cli close

# 后续：加载状态跳过登录
playwright-cli state-load auth.json
playwright-cli open https://app.example.com/dashboard
# 已登录状态
```

#### 8.5.5 GitHub Actions 集成示例

```yaml
# .github/workflows/e2e.yml
name: E2E with Playwright CLI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-node@v5
        with:
          node-version: '20'
      - run: npm ci
      - run: npm install -g @playwright/cli@latest
      - name: Run AI-driven browser test
        env:
          PLAYWRIGHT_MCP_HEADLESS: true
          PLAYWRIGHT_MCP_OUTPUT_DIR: ./test-results
          PLAYWRIGHT_MCP_SAVE_TRACE: true
        run: |
          playwright-cli open https://staging.example.com
          playwright-cli snapshot
          playwright-cli screenshot --filename=homepage.png
          playwright-cli close
      - uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: ./test-results
```

### 8.6 UI-AI 自动化测试场景应用示例

#### 8.6.1 AI 驱动的回归测试

```bash
# AI Agent 自动执行回归测试
# 1. 打开应用
playwright-cli open https://app.example.com

# 2. 获取页面基线快照
playwright-cli snapshot --filename=baseline.yml

# 3. 执行核心流程
playwright-cli click e5            # 导航到功能页
playwright-cli fill e8 "test data" # 填写表单
playwright-cli click e10           # 提交

# 4. 验证结果
playwright-cli snapshot --filename=after-submit.yml
playwright-cli console             # 检查控制台错误
playwright-cli requests            # 检查网络请求

# 5. 截图留证
playwright-cli screenshot --filename=regression-result.png
```

#### 8.6.2 AI 驱动的兼容性测试

```bash
# 多浏览器测试
playwright-cli -s=chrome open https://app.example.com --browser=chrome
playwright-cli -s=firefox open https://app.example.com --browser=firefox
playwright-cli -s=webkit open https://app.example.com --browser=webkit

# 在每个浏览器中执行相同操作
for session in chrome firefox webkit; do
  playwright-cli -s=$session snapshot
  playwright-cli -s=$session fill e1 "test"
  playwright-cli -s=$session click e2
  playwright-cli -s=$session screenshot --filename="${session}-result.png"
done

playwright-cli close-all
```

#### 8.6.3 AI 驱动的 API 集成测试

```bash
# 模拟后端响应
playwright-cli route "**/api/user" --body='{"id":1,"name":"Test User"}' --content-type=application/json

# 执行前端操作
playwright-cli open https://app.example.com
playwright-cli click e5  # 触发 API 调用

# 验证前端对模拟数据的处理
playwright-cli snapshot
playwright-cli --raw eval "document.querySelector('.user-name').textContent"
```

---

## 9. 优势与局限

### 9.1 优势

| 优势 | 说明 |
|------|------|
| **Token 高效** | 不强制将页面数据推入 LLM，Snapshot 机制按需获取，适合有限上下文窗口的 AI Agent |
| **SKILL 驱动** | 通过 SKILL.md 向 Agent 提供操作指南，Agent 自主发现和使用命令 |
| **自动代码生成** | 每个操作自动生成 Playwright TypeScript 代码，交互即录制 |
| **语义化 Locator** | 生成 `getByRole`、`getByTestId` 等稳定定位器，减少选择器漂移 |
| **完整的浏览器操控** | 覆盖点击、输入、拖拽、键盘、鼠标、标签页、对话框等全场景 |
| **多会话管理** | 命名会话隔离，支持并行测试和 A/B 测试 |
| **丰富的调试工具** | 控制台、网络请求、追踪、视频录制、元素高亮 |
| **人机协作** | `show --annotate` 实现可视化人机协作 |
| **Spec-Driven 工作流** | 完整的 Plan → Generate → Heal 测试生命周期 |
| **CI/CD 友好** | Headless 默认、`--raw`/`--json` 输出、环境变量配置 |
| **存储状态管理** | Cookies、LocalStorage、SessionStorage 的完整管理 |
| **网络模拟** | 请求路由、响应模拟、网络故障模拟 |
| **配置灵活** | JSON 配置文件、环境变量、命令行选项多种配置方式 |
| **薄封装架构** | 核心逻辑在 playwright-core 中，CLI 包极简，易于维护和更新 |

### 9.2 局限

| 局限 | 说明 |
|------|------|
| **Alpha 版本依赖** | 依赖 Playwright alpha 版本，生产环境稳定性存疑 |
| **核心逻辑外部化** | CLI 核心实现在 playwright-core 内部，无法在本仓库中直接修改 |
| **无并行命令** | CLI 是串行命令调用，无法在单个命令中执行多个操作 |
| **无内置断言** | 生成的代码不包含断言，需要手动添加 |
| **无状态管理** | 每次 CLI 调用是独立进程，依赖 Daemon 维护状态 |
| **Windows 兼容性** | URL 中的 `&` 在 Windows 上需要特殊转义 |
| **追踪开销** | 追踪录制会增加自动化开销，大型追踪消耗磁盘空间 |
| **视频文件较大** | WebM 视频文件体积较大 |
| **无内置报告** | 没有内置的测试报告生成功能 |
| **SKILL 生态有限** | 目前仅支持 Claude Code 和 GitHub Copilot 等 Agent |
| **缺少类型定义** | 入口文件使用纯 JavaScript，无 TypeScript 类型 |
| **测试覆盖有限** | 集成测试仅有一个基本用例（open data URL） |

---

## 10. 框架搭建参考建议

### 10.1 架构参考

基于 playwright-cli 的架构分析，搭建 UI-AI 自动化测试框架时可参考以下架构：

```
┌──────────────────────────────────────────────────────────────┐
│                    AI Agent 调度层                            │
│  - 任务解析与规划                                              │
│  - Spec 文件生成                                              │
│  - 测试策略决策                                               │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                    SKILL 定义层                               │
│  - 命令使用指南                                               │
│  - 最佳实践参考                                               │
│  - 场景化工作流                                               │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                    CLI 命令层                                 │
│  - 浏览器操控命令                                             │
│  - 状态感知命令                                              │
│  - 代码生成命令                                              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                    浏览器引擎层                               │
│  - Playwright Core                                           │
│  - 多浏览器支持                                               │
│  - Daemon 进程管理                                            │
└──────────────────────────────────────────────────────────────┘
```

### 10.2 关键设计原则

1. **Token 效率优先**：所有与 AI Agent 的交互都应考虑 Token 消耗，使用精简的 Snapshot 而非完整 DOM
2. **命令式接口**：为 AI Agent 提供简洁、明确的命令接口，避免复杂的 API Schema
3. **交互即录制**：每次操作都应自动生成可复用的代码，降低测试编写成本
4. **感知-决策-执行闭环**：命令输出应包含状态反馈，支持 Agent 的闭环控制
5. **SKILL 驱动**：通过 SKILL 文件向 Agent 提供操作指南，实现自主发现和使用
6. **人机协作**：提供可视化协作工具，支持人类介入和反馈

### 10.3 推荐技术选型

| 组件 | 推荐方案 | 参考 playwright-cli |
|------|---------|---------------------|
| 浏览器自动化 | Playwright | 核心依赖 |
| AI Agent 集成 | SKILL 机制 | SKILL.md + references/ |
| 命令行框架 | playwright-core CLI Client | Client-Daemon 架构 |
| 代码生成 | Playwright Codegen | 自动 TypeScript 生成 |
| 测试框架 | @playwright/test | Spec-Driven 工作流 |
| 会话管理 | Daemon 进程 | 命名会话 + 持久化 |
| 配置管理 | JSON 配置文件 | cli.config.json |
| CI/CD 集成 | Headless + 环境变量 | PLAYWRIGHT_MCP_* 变量 |

### 10.4 扩展方向建议

1. **多 Agent 协作**：支持多个 AI Agent 同时操作不同会话，实现分布式测试
2. **智能断言生成**：基于页面状态自动生成合理的断言，减少手动添加
3. **视觉回归测试**：集成截图对比，自动检测 UI 变化
4. **测试报告生成**：内置 HTML/JSON 报告生成，支持 CI/CD 集成
5. **自然语言 Spec**：支持自然语言描述测试场景，AI 自动转换为结构化 Spec
6. **自愈测试**：当选择器失效时，AI 自动寻找替代定位器
7. **测试数据管理**：集成测试数据生成和管理
8. **跨平台支持**：增强 Windows 兼容性，支持移动端测试
9. **插件系统**：支持自定义命令和 SKILL 扩展
10. **安全增强**：敏感数据脱敏、操作审计日志

### 10.5 项目结构参考

```
uiaitest/
├── .playwright/
│   └── cli.config.json           # Playwright CLI 配置
├── specs/                         # 测试规格文件
│   └── feature.plan.md
├── tests/                         # 测试文件
│   ├── fixtures.ts                # 测试 Fixtures
│   ├── seed.spec.ts               # 种子测试
│   └── <group>/                   # 测试分组
│       └── <scenario>.spec.ts
├── skills/                        # AI Agent SKILL 定义
│   └── uiaitest/
│       ├── SKILL.md
│       └── references/
├── scripts/                       # 自动化脚本
├── traces/                        # 追踪文件
├── docs/                          # 文档
└── playwright.config.ts           # Playwright 配置
```

---

## 附录 A：命令速查表

### 核心操作

| 命令 | 用途 |
|------|------|
| `open [url]` | 打开浏览器 |
| `goto <url>` | 导航 |
| `close` | 关闭页面 |
| `type <text>` | 输入文本 |
| `click <ref>` | 点击 |
| `fill <ref> <text>` | 填充 |
| `snapshot` | 获取页面快照 |
| `eval <func>` | 执行 JS |
| `screenshot` | 截图 |

### 会话管理

| 命令 | 用途 |
|------|------|
| `-s=<name> <cmd>` | 命名会话 |
| `list` | 列出会话 |
| `close-all` | 关闭所有 |
| `kill-all` | 强制终止 |
| `attach --cdp=<url>` | 附加浏览器 |
| `detach` | 分离浏览器 |

### 调试工具

| 命令 | 用途 |
|------|------|
| `console` | 控制台消息 |
| `requests` | 网络请求 |
| `tracing-start/stop` | 追踪录制 |
| `video-start/stop` | 视频录制 |
| `show` | 可视化仪表盘 |
| `show --annotate` | 标注模式 |
| `generate-locator` | 生成 Locator |
| `highlight` | 高亮元素 |

### 全局选项

| 选项 | 用途 |
|------|------|
| `--raw` | 精简输出 |
| `--json` | JSON 输出 |
| `--headed` | 有头模式 |
| `--persistent` | 持久化配置 |
| `--config=<file>` | 配置文件 |

---

## 附录 B：配置文件完整 Schema

```typescript
{
  browser?: {
    browserName?: 'chromium' | 'firefox' | 'webkit';
    isolated?: boolean;
    userDataDir?: string;
    launchOptions?: playwright.LaunchOptions;
    contextOptions?: playwright.BrowserContextOptions;
    cdpEndpoint?: string;
    cdpHeaders?: Record<string, string>;
    cdpTimeout?: number;
    remoteEndpoint?: string;
    initPage?: string[];
    initScript?: string[];
  },
  saveVideo?: { width: number; height: number };
  outputDir?: string;
  outputMode?: 'file' | 'stdout';
  console?: { level?: 'error' | 'warning' | 'info' | 'debug' };
  network?: {
    allowedOrigins?: string[];
    blockedOrigins?: string[];
  };
  testIdAttribute?: string;
  timeouts?: {
    action?: number;
    navigation?: number;
  };
  allowUnrestrictedFileAccess?: boolean;
  codegen?: 'typescript' | 'none';
}
```

---

*本报告基于 `@playwright/cli@0.1.14` 源码分析生成，所有结论均来自实际代码和文档，未做任何猜测。*
