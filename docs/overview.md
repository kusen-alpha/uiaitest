# 概述

UIAI 是一个 AI 驱动的 UI 自动化测试框架，让测试人员用自然语言描述测试需求，由 AI Agent 自动执行测试、断言验证、失败自愈、生成报告。

---

## UIAI 能做什么？

### 🎯 自然语言驱动测试

用中文描述测试需求，AI 自动理解并执行：

```
测试用户登录流程：
1. 打开登录页面
2. 输入用户名 admin 和密码 123456
3. 点击登录按钮
4. 验证跳转到首页
```

### 🤖 AI Agent 自主执行

六种 Agent 协作完成测试全流程：

| Agent | 职责 |
|-------|------|
| **PlannerAgent** | 解析自然语言，生成测试计划 |
| **ExecutorAgent** | 感知页面、决策动作、执行操作 |
| **JudgeAgent** | 独立评估执行结果是否成功 |
| **HealerAgent** | 失败时分析原因，生成修复建议 |
| **ExplorerAgent** | AI 探索性测试，发现潜在问题 |
| **CodeRecorder** | 录制执行过程为可复现代码 |

### 🛡️ 九种 Watchdog 自动守卫

测试执行过程中自动监控和应对：

- **PopupWatchdog** — 自动关闭 JS 弹窗
- **CaptchaWatchdog** — 检测验证码，支持 TOTP 自动处理
- **CrashWatchdog** — 浏览器崩溃自动恢复
- **SecurityWatchdog** — 域名安全守卫
- **NetworkWatchdog** — 网络异常检测
- **StorageWatchdog** — Cookie/LocalStorage 自动保存恢复
- **DownloadWatchdog** — 文件下载追踪
- **DomWatchdog** — DOM 变更监控
- **VisualAnomalyWatchdog** — UI 异常检测（白屏、空图、元素堆叠）

### 🔧 四层自愈降级

定位失败时自动尝试修复：

| 层级 | 策略 | 说明 |
|------|------|------|
| L1 | 选择器降级 | 尝试 Locator 的 fallback chain |
| L2 | DOM 邻近搜索 | 在 A11y Tree 中搜索相似元素 |
| L3 | 视觉定位兜底 | VL 模型视觉定位元素 |
| L4 | AI 修复建议 | LLM 分析失败原因，生成修复建议 |

### 💾 三层缓存加速

减少 LLM 调用，提升执行效率：

- **PlanCache** — 任务流程缓存
- **LocateCache** — 元素定位缓存
- **FeatureCache** — 视觉特征缓存

### 📊 知识沉淀系统

自动积累测试经验：

- **需求级知识** — 业务需求文档
- **产品级知识** — 产品功能说明
- **经验级知识** — 成功/失败案例自动沉淀

---

## 核心特性

### 四种感知模式

Agent 如何"看"页面：

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| **A11Y_SNAPSHOT** | Accessibility Tree 快照 | Token 高效，常规页面 |
| **DOM_SERIALIZE** | DOM 序列化 | 信息完整，复杂页面 |
| **VISUAL_SCREENSHOT** | 纯视觉截图 + VL 模型 | Canvas/WebGL 页面 |
| **HYBRID** | DOM 优先，视觉降级 | 全场景覆盖 |

### 四层运行模式

| 层级 | 模式 | 说明 |
|------|------|------|
| **R1_SCRIPT** | 确定性脚本 | 手写/录制的 Python 测试代码 |
| **R2_AGENT** | 智能 Agent 辅助 | Agent 感知 + LLM 决策 + 执行循环 |
| **R3_LOCAL_DEV** | 本地开发 | MCP Server + Claude Code CLI |

### 多模型意图路由

不同任务自动路由到最优模型：

| 意图 | 模型类型 | 说明 |
|------|---------|------|
| **LOCATE** | VL 模型 | 元素定位（UI-TARS） |
| **PLAN** | 强 LLM | 任务规划（Qwen-Plus） |
| **EXTRACT** | 轻量模型 | 信息提取（Qwen-Turbo） |
| **ASSERT** | VL 模型 | 视觉断言 |
| **HEAL** | LLM | 自愈修复 |

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户交互层                              │
│   CLI命令行  │  MCP Server  │  Python SDK  │  pytest插件    │
├─────────────────────────────────────────────────────────────┤
│                      编排调度层                              │
│   TestOrchestrator  │  AgentCollabor  │  EventBus  │  Cache │
├─────────────────────────────────────────────────────────────┤
│                      AI Agent层                             │
│   PlannerAgent │ ExecutorAgent │ JudgeAgent │ HealerAgent   │
│   ExplorerAgent │ CodeRecorder │ LoopDetector │ IntentRouter│
├─────────────────────────────────────────────────────────────┤
│                      执行抽象层                              │
│   PlaywrightExecutor │ AppiumExecutor │ NetworkInterceptor │
│   Watchdog系统(9种) │ PerceptionEngine │ DeepLocator       │
├─────────────────────────────────────────────────────────────┤
│                      基础设施层                              │
│   BrowserPool │ DockerPool │ KnowledgeManager │ ConfigProxy│
└─────────────────────────────────────────────────────────────┘
```

---

## 与其他方案对比

| 特性 | UIAI | Selenium | Cypress | Playwright |
|------|------|----------|---------|------------|
| 自然语言驱动 | ✅ | ❌ | ❌ | ❌ |
| AI 自主执行 | ✅ | ❌ | ❌ | ❌ |
| 失败自动自愈 | ✅ 四层降级 | ❌ | ❌ | ❌ |
| 视觉定位 | ✅ VL模型 | ❌ | ❌ | ❌ |
| 知识沉淀 | ✅ 三级知识 | ❌ | ❌ | ❌ |
| Watchdog守卫 | ✅ 9种 | ❌ | ❌ | ❌ |
| 代码录制 | ✅ 自动生成 | ❌ 手写 | ❌ | ❌ |

---

## 适用场景

### ✅ 推荐 UIAI

- 测试团队希望减少手写代码
- 测试用例频繁变更，维护成本高
- 需要探索性测试发现潜在问题
- 希望自动积累测试经验知识
- 多平台测试（Web/App/H5）

### ⚠️ 可能不适合

- 简单的静态页面测试（传统脚本更高效）
- 无 LLM API 访问权限
- 极高实时性要求（Agent 循环有延迟）

---

## 快速开始

### 安装

```bash
pip install uiai
playwright install chromium
```

### 最简示例

```python
from uiai import TestOrchestrator

# 创建编排器
orch = TestOrchestrator()

# R2 Agent 模式：自然语言执行
result = await orch.run_agent_test(
    "打开百度搜索，输入'UIAI自动化测试'，点击搜索按钮，验证结果页包含相关内容"
)

print(f"测试结果: {result.status}")
```

### R1 脚本模式

```python
from uiai import TestCase, Locator

test = TestCase(
    id="login_test",
    name="登录测试",
    steps=[
        {"action": "navigate", "value": "https://example.com/login"},
        {"action": "type", "locator": Locator.by_test_id("username"), "value": "admin"},
        {"action": "type", "locator": Locator.by_test_id("password"), "value": "123456"},
        {"action": "click", "locator": Locator.by_role("button", name="登录")},
        {"action": "assert_url", "value": "https://example.com/home"},
    ]
)

result = await orch.run_test(test)
```

---

## CLI 命令

```bash
# 运行测试
uiai run test.yaml --mode agent --record

# 生成测试计划
uiai plan "测试购物车功能"

# 生成测试代码
uiai generate plan.md

# AI 探索性测试
uiai explore https://example.com

# 缓存管理
uiai cache stats
uiai cache clear

# 知识库管理
uiai knowledge show --level experience
uiai knowledge add --level experience --domain ecommerce --title "登录成功" --content "..."

# 查看技能列表
uiai skill

# 插件管理
uiai plugin list
uiai plugin enable TraceRecorder
```

---

## 下一步

- [快速开始](quick-start.md) — 5 分钟上手教程
- [核心概念](core-concepts.md) — 理解 Agent/感知/缓存
- [配置详解](configuration.md) — LLM/浏览器/缓存配置
- [CLI 参考](cli-reference.md) — 所有命令详解
- [最佳实践](best-practices.md) — 生产环境建议

---

## 开源信息

- **GitHub**: [uiai-framework/uiai](https://github.com/uiai-framework/uiai)
- **版本**: v1.0.0
- **许可证**: Apache 2.0
- **更新日志**: [CHANGELOG.md](../changelog/CHANGELOG.md)