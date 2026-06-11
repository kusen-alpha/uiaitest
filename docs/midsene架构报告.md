# Midscene.js 架构深度分析报告

> **分析日期**：2026-06-11  
> **项目版本**：v1.9.2  
> **项目地址**：https://github.com/web-infra-dev/midscene

---

## 1. 项目概述

### 1.1 项目定位

**Midscene.js** 是字节跳动 Web Infra 团队开源的 **AI驱动的视觉自动化测试框架**，核心理念是：

```
用户描述目标 → AI理解界面 → 自动完成测试
```

**核心特点**：
- **纯视觉驱动**：完全基于截图识别，摆脱DOM依赖
- **自然语言接口**：用自然语言描述测试意图，而非编写选择器
- **跨平台支持**：Web、Android、iOS、桌面、鸿蒙统一API
- **多模型支持**：支持UI-TARS、Qwen、Gemini、GPT等多种视觉语言模型

### 1.2 项目规模

```
仓库结构：Monorepo (pnpm workspace)
核心包数量：约15个
代码行数：约10万行
测试覆盖：单元测试 + AI测试 + E2E测试
```

---

## 2. 核心架构设计

### 2.1 整体架构分层

Midscene.js 采用 **五层架构设计**：

```
┌─────────────────────────────────────────────────────────────┐
│                    用户交互层 (User Interface)                │
│  Chrome Extension | CLI | Playwright Fixture | YAML Scripts │
├─────────────────────────────────────────────────────────────┤
│                    编排调度层 (Orchestration)                 │
│              Agent | TaskExecutor | ExecutionSession         │
├─────────────────────────────────────────────────────────────┤
│                    AI Agent层 (AI Processing)                │
│          Service | TaskBuilder | Planning | Conversation     │
├─────────────────────────────────────────────────────────────┤
│                    执行抽象层 (Execution)                     │
│    AbstractInterface | DeviceAction | TaskRunner | Report    │
├─────────────────────────────────────────────────────────────┤
│                    基础设施层 (Infrastructure)                 │
│     Platform Adapters | AI Models | Cache | Logger | Utils   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 包结构组织

```
packages/
├── core/                    # 核心引擎
│   ├── agent/               # Agent核心实现
│   │   ├── agent.ts         # Agent主类
│   │   ├── tasks.ts         # 任务执行器
│   │   ├── task-builder.ts  # 任务构建器
│   │   ├── execution-session.ts # 执行会话
│   │   └── task-cache.ts    # 缓存系统
│   ├── ai-model/            # AI模型层
│   ├── service/             # AI服务层
│   ├── device/              # 设备抽象层
│   └── types.ts             # 类型定义
│
├── web-integration/         # Web集成层
│   ├── playwright/          # Playwright集成
│   │   ├── page.ts          # Playwright页面
│   │   ├── ai-fixture.ts    # Playwright Fixture
│   │   └── reporter/        # 报告器
│   ├── puppeteer/           # Puppeteer集成
│   ├── bridge-mode/         # 桥接模式
│   └── chrome-extension/    # Chrome扩展
│
├── android/                 # Android平台适配
├── ios/                     # iOS平台适配
├── harmony/                 # 鸿蒙平台适配
├── computer/                # 桌面平台适配
├── mcp/                     # MCP Server
├── shared/                  # 共享工具
└── cli/                     # CLI工具
```

---

## 3. Agent架构详解

### 3.1 Agent核心类设计

Agent 是整个系统的核心协调器，负责管理完整的自动化生命周期：

```typescript
// packages/core/src/agent/agent.ts
export class Agent<InterfaceType extends AbstractInterface = AbstractInterface> {
  // 核心属性
  interface: InterfaceType;      // 平台接口
  service: Service;              // AI服务
  taskExecutor: TaskExecutor;    // 任务执行器
  dump: ReportActionDump;        // 报告数据
  taskCache?: TaskCache;         // 缓存系统
  modelConfigManager: ModelConfigManager; // 模型配置管理
  
  // 核心API方法
  async aiAct(taskPrompt: TUserPrompt): Promise<string>;  // 自动规划执行
  async aiTap(locatePrompt: TUserPrompt): Promise<void>;  // 点击
  async aiInput(locatePrompt, value): Promise<void>;      // 输入
  async aiQuery<T>(demand): Promise<T>;                   // 数据提取
  async aiAssert(assertion): Promise<void>;               // 断言
  async aiWaitFor(assertion, timeout): Promise<void>;     // 等待条件
  async aiLocate(prompt): Promise<{rect, center}>;        // 定位元素
}
```

### 3.2 Agent生命周期

```
┌─────────────┐
│  构造阶段   │  constructor(interface, opts)
│             │  → 初始化Service、TaskExecutor、Cache
│             │  → 构建ActionSpace
│             │  → 设置ReportGenerator
├─────────────┤
│  运行阶段   │  aiAct / aiTap / aiQuery ...
│             │  → 获取UIContext（截图+尺寸）
│             │  → 调用AI模型进行规划/定位
│             │  → 执行动作序列
│             │  → 记录执行过程到Report
├─────────────┤
│  销毁阶段   │  destroy()
│             │  → 清理Interface资源
│             │  → 生成最终报告
│             │  → 释放内存
└─────────────┘
```

### 3.3 核心数据模型

#### 3.3.1 UIContext - 界面上下文

```typescript
export abstract class UIContext {
  abstract screenshot: ScreenshotItem;     // 截图（Base64）
  abstract shotSize: Size;                 // 截图尺寸
  abstract shrunkShotToLogicalRatio: number; // 坐标转换比例
  abstract _isFrozen?: boolean;            // 是否冻结
}
```

#### 3.3.2 ExecutionTask - 执行任务

```typescript
export interface ExecutionTask {
  taskId: string;
  type: 'Planning' | 'Insight' | 'Action Space' | 'Log';
  subType?: string;
  status: 'pending' | 'running' | 'finished' | 'failed' | 'cancelled';
  param?: any;
  thought?: string;
  executor: (param, context) => Promise<ExecutionTaskReturn>;
  timing?: { start, end, cost, ... };
  usage?: AIUsageInfo;  // AI调用统计
  error?: Error;
}
```

#### 3.3.3 PlanningAction - 规划动作

```typescript
export interface PlanningAction<ParamType = any> {
  thought?: string;      // AI思考过程
  log?: string;          // 用户可见的日志
  type: string;          // 动作类型（Tap/Input/Scroll等）
  param: ParamType;      // 动作参数
}
```

---

## 4. 任务执行系统

### 4.1 TaskExecutor - 任务执行引擎

TaskExecutor 是核心执行引擎，负责将AI规划转换为可执行任务：

```typescript
// packages/core/src/agent/tasks.ts
export class TaskExecutor {
  interface: AbstractInterface;
  service: Service;
  taskCache?: TaskCache;
  taskBuilder: TaskBuilder;
  
  // 核心方法
  async action(userPrompt, planningModel, defaultModel): Promise<ExecutionResult>;
  async runPlans(title, plans, planningModel, defaultModel): Promise<ExecutionResult>;
  async createTypeQueryExecution(type, demand, modelRuntime): Promise<ExecutionResult>;
  async waitFor(assertion, opt, modelRuntime): Promise<ExecutionResult>;
}
```

### 4.2 执行流程详解

**aiAct 执行流程**（最核心的自动规划流程）：

```
用户输入自然语言指令
         ↓
┌────────────────────────────────────────────────────┐
│                    主规划循环                        │
│  while (!shouldContinuePlanning) {                  │
│    ┌──────────────────────────────────────────┐    │
│    │  1. Planning阶段                          │    │
│    │  → 获取UIContext（截图）                   │    │
│    │  → 调用planningModel生成PlanningAction[]  │    │
│    │  → 返回：actions, thought, shouldContinue │    │
│    └──────────────────────────────────────────┘    │
│                    ↓                               │
│    ┌──────────────────────────────────────────┐    │
│    │  2. 转换阶段                              │    │
│    │  → TaskBuilder.build(plans)              │    │
│    │  → 将PlanningAction转换为ExecutionTask[] │    │
│    │  → 处理Locate任务（元素定位）              │    │
│    └──────────────────────────────────────────┘    │
│                    ↓                               │
│    ┌──────────────────────────────────────────┐    │
│    │  3. 执行阶段                              │    │
│    │  → ExecutionSession.appendAndRun(tasks)  │    │
│    │  → TaskRunner逐个执行任务                 │    │
│    │  → 记录执行结果和截图                      │    │
│    └──────────────────────────────────────────┘    │
│                    ↓                               │
│    ┌──────────────────────────────────────────┐    │
│    │  4. 反馈阶段                              │    │
│    │  → 收集执行反馈                           │    │
│    │  → 设置pendingFeedbackMessage            │    │
│    │  → 判断是否需要重新规划                    │    │
│    └──────────────────────────────────────────┘    │
│  }                                                  │
└────────────────────────────────────────────────────┘
         ↓
    返回执行结果 + YAML流程（用于缓存）
```

### 4.3 TaskBuilder - 任务构建器

将AI规划的动作转换为可执行任务：

```typescript
// packages/core/src/agent/task-builder.ts
export class TaskBuilder {
  async build(plans: PlanningAction[], planningModel, defaultModel): Promise<{tasks}> {
    for (const plan of plans) {
      if (plan.type === 'Locate') {
        // 创建定位任务
        tasks.push(this.createLocateTask(plan));
      } else if (plan.type === 'Finished') {
        // 创建完成标记
        tasks.push({ type: 'Action Space', subType: 'Finished' });
      } else {
        // 创建动作任务（Tap/Input/Scroll等）
        // 先处理locate参数（如果需要）
        tasks.push(this.handleActionPlan(plan));
      }
    }
    return { tasks };
  }
}
```

### 4.4 TaskRunner - 任务运行器

实际执行任务的引擎：

```typescript
// packages/core/src/task-runner.ts
export class TaskRunner {
  tasks: ExecutionTask[];
  status: 'init' | 'pending' | 'running' | 'completed' | 'error';
  
  async flush(): Promise<{output, thought}> {
    while (taskIndex < this.tasks.length) {
      const task = this.tasks[taskIndex];
      task.status = 'running';
      
      // 获取UI上下文
      const uiContext = await this.getUiContext();
      
      // 执行任务
      const returnValue = await task.executor(task.param, {
        task,
        element: previousFindOutput?.element,
        uiContext
      });
      
      // 记录结果
      Object.assign(task, returnValue);
      task.status = 'finished';
      
      // 截图记录（最后一个任务）
      if (isLastTask) {
        const screenshot = await this.captureScreenshot();
        task.recorder.push({ type: 'screenshot', screenshot });
      }
      
      taskIndex++;
    }
    return { output: lastTask.output, thought: lastTask.thought };
  }
}
```

---

## 5. AI模型集成

### 5.1 多模型策略

Midscene.js 采用 **意图路由（Intent Routing）** 的多模型策略：

```typescript
// 模型意图类型
type TIntent = 'default' | 'planning' | 'insight';

// 模型配置管理
class ModelConfigManager {
  getModelConfig(intent: TIntent): TModelConfig {
    // 根据意图返回对应模型配置
    // default: 用于元素定位（VL模型）
    // planning: 用于任务规划（LLM模型）
    // insight: 用于数据提取/断言（VL模型）
  }
}
```

**推荐模型配置**：

| 意图 | 推荐模型 | 用途 |
|------|---------|------|
| default (locate) | UI-TARS-1.5-7B, Qwen3-VL | 元素定位，返回坐标 |
| planning | GPT-4o-mini, Qwen | 任务规划，生成动作序列 |
| insight | GPT-4o, Gemini | 数据提取，复杂理解 |

### 5.2 Service层 - AI服务调用

Service 是AI调用的核心服务层：

```typescript
// packages/core/src/service/index.ts
export default class Service {
  contextRetrieverFn: () => Promise<UIContext>;
  
  // 元素定位
  async locate(query, opt, modelRuntime): Promise<LocateResultWithDump> {
    // 1. 深度定位：先定位区域，再定位元素
    const searchArea = await this.resolveLocateSearchArea(query);
    
    // 2. 调用VL模型定位元素
    const result = await AiLocateElement({
      context,
      targetElementDescription: queryPrompt,
      searchConfig: searchArea.config,
      modelRuntime
    });
    
    // 3. 返回元素坐标和执行记录
    return { element: { center, rect }, dump };
  }
  
  // 数据提取
  async extract<T>(dataDemand, modelRuntime): Promise<ServiceExtractResult<T>> {
    const result = await AiExtractElementInfo({
      context,
      dataQuery: dataDemand,
      modelRuntime
    });
    return { data, thought, dump };
  }
  
  // 元素描述
  async describe(target, modelRuntime): Promise<{description}> {
    // 截取目标区域，生成自然语言描述
  }
}
```

### 5.3 视觉定位流程

```
用户描述："点击登录按钮"
         ↓
┌────────────────────────────────────────────┐
│  1. 截图获取                                │
│  → interface.screenshotBase64()            │
│  → 可能进行压缩（screenshotShrinkFactor）   │
└────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────┐
│  2. 深度定位（可选）                         │
│  → AiLocateSection: 先定位大致区域          │
│  → cropByRect: 截取区域图片                 │
│  → 减少token消耗，提高精度                  │
└────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────┐
│  3. VL模型定位                              │
│  → 发送截图 + 描述到VL模型                  │
│  → 模型返回：{ point: [x,y], bbox: [...] } │
│  → 坐标转换：screenshot → logical          │
└────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────┐
│  4. 缓存写入（可选）                         │
│  → cacheFeatureForPoint: 提取元素特征       │
│  → 写入缓存，下次快速定位                   │
└────────────────────────────────────────────┘
         ↓
    返回：{ center: [x,y], rect: {...} }
```

---

## 6. 自动化测试理念

### 6.1 自然语言驱动测试

Midscene.js 的核心理念是用自然语言替代传统选择器：

```typescript
// 传统方式（脆弱）
await page.locator('#login-btn').click();
await page.locator('input[name="email"]').fill('test@example.com');

// Midscene方式（稳定）
await agent.aiTap('登录按钮');
await agent.aiInput('邮箱输入框', { value: 'test@example.com' });
await agent.aiAssert('页面显示登录成功提示');
```

### 6.2 API设计理念

#### 6.2.1 aiAct - 自动规划执行

最核心的API，AI自主规划并执行整个流程：

```typescript
// 用户描述目标，AI自动完成
await agent.aiAct('在搜索框输入"React教程"，点击搜索按钮，等待结果加载完成');

// 内部流程：
// 1. Planning: AI分析截图，生成动作序列
// 2. Execute: 逐个执行动作
// 3. Replan: 如果失败，重新规划
// 4. Complete: 直到目标完成
```

#### 6.2.2 原子操作API

提供精确控制的原子操作：

```typescript
// 定位
await agent.aiTap('提交按钮');
await agent.aiHover('导航菜单');
await agent.aiRightClick('文件图标');
await agent.aiDoubleClick('文件夹');

// 输入
await agent.aiInput('搜索框', { value: '关键词', mode: 'replace' });
await agent.aiKeyboardPress('Enter');
await agent.aiClearInput('输入框');

// 滚动
await agent.aiScroll(null, { direction: 'down', scrollType: 'scrollToBottom' });

// 移动端
await agent.aiLongPress('消息气泡');
await agent.aiSwipe({ direction: 'up', distance: 200 });
await agent.aiPinch({ direction: 'out' });
```

#### 6.2.3 数据提取API

```typescript
// 结构化数据提取
const products = await agent.aiQuery<{name: string, price: number}[]>(
  '提取商品列表中的所有商品名称和价格'
);

// 简单类型提取
const count = await agent.aiNumber('页面上的商品数量');
const title = await agent.aiString('页面标题');
const isVisible = await agent.aiBoolean('登录按钮是否可见');
```

#### 6.2.4 断言API

```typescript
// 自然语言断言
await agent.aiAssert('页面显示"登录成功"消息');
await agent.aiAssert('购物车中有3件商品');

// 等待条件
await agent.aiWaitFor('加载完成，页面显示结果列表', { timeoutMs: 10000 });
```

### 6.3 Playwright集成

通过Fixture机制无缝集成Playwright：

```typescript
// packages/web-integration/src/playwright/ai-fixture.ts
export const PlaywrightAiFixture = (options?) => {
  return {
    // 自动清理的Fixture
    _midsceneFinalizeReports: async ({}, use, testInfo) => {
      await use();
      // 测试结束后自动生成报告
      const reportPaths = await finalizeAgentRecords(testInfo);
      setReportAnnotation(testInfo, reportPaths);
    },
    
    // Agent获取
    agentForPage: async ({ page }, use, testInfo) => {
      await use(async (propsPage, opts) => {
        return createOrReuseAgentForPage(propsPage || page, testInfo, opts);
      });
    },
    
    // 所有AI方法作为Fixture
    ai: async ({ page }, use, testInfo) => { ... },
    aiTap: async ({ page }, use, testInfo) => { ... },
    aiAssert: async ({ page }, use, testInfo) => { ... },
    // ...
  };
};

// 使用示例
import { test } from '@playwright/test';
import { PlaywrightAiFixture } from '@midscene/web';

test.extend(PlaywrightAiFixture())('登录测试', async ({ page, ai, aiAssert }) => {
  await page.goto('https://example.com/login');
  await ai('输入用户名和密码，点击登录');
  await aiAssert('显示登录成功');
});
```

---

## 7. 关键设计亮点

### 7.1 纯视觉定位

**核心创新**：完全摆脱DOM依赖，基于截图识别元素

```typescript
// 传统方式的问题
// - CSS选择器脆弱，UI变化就失效
// - Canvas/WebGL无法通过DOM定位
// - 跨平台没有统一DOM

// Midscene解决方案
// - VL模型理解视觉内容
// - 返回像素坐标，直接操作
// - 跨平台统一视觉接口
```

### 7.2 智能缓存系统

**三层缓存策略**：

```typescript
// 1. Plan缓存：缓存整个任务流程
if (matchedCache?.yamlWorkflow) {
  await this.runYaml(matchedCache.yamlWorkflow);
  return; // 直接执行缓存流程，跳过AI调用
}

// 2. Locate缓存：缓存元素定位结果
const locateCacheRecord = this.taskCache?.matchLocateCache(prompt);
if (locateCacheRecord?.cache) {
  // 通过XPath/CSS特征快速定位
  const rect = await interface.rectMatchesCacheFeature(cacheEntry);
  return { center, rect }; // 跳过VL模型调用
}

// 3. 特征缓存：提取元素特征用于下次匹配
const feature = await interface.cacheFeatureForPoint(center);
this.taskCache.updateOrAppendCacheRecord({ type: 'locate', prompt, cache: feature });
```

**缓存效果**：
- 首次执行：正常AI调用
- 后续执行：缓存命中，速度提升3-10倍

### 7.3 深度定位（Deep Locate）

**两阶段定位策略**：

```typescript
// 1. 第一阶段：定位大致区域
const searchArea = await AiLocateSection({
  context,
  sectionDescription: prompt
});
// 返回大致区域 rect

// 2. 第二阶段：在区域内精确定位
const croppedImage = await cropByRect(screenshot, searchArea.rect);
const element = await AiLocateElement({
  context: croppedImage,
  targetElementDescription: prompt
});
// 返回精确坐标
```

**优势**：
- 减少token消耗（只处理局部图片）
- 提高定位精度（聚焦区域）
- 处理复杂界面（多元素场景）

### 7.4 桥接模式（Bridge Mode）

**本地SDK + 浏览器扩展双向通信**：

```
┌─────────────────┐         WebSocket         ┌─────────────────┐
│   本地CLI/SDK    │ ←──────────────────────→ │  Chrome Extension │
│                 │                           │                  │
│  Agent实例      │                           │  页面控制        │
│  脚本编写       │                           │  截图/执行       │
│  报告生成       │                           │  实时反馈        │
└─────────────────┘                           └─────────────────┘
```

**应用场景**：
- 本地脚本控制远程浏览器
- 实时调试和可视化
- 跨机器协作测试

### 7.5 YAML脚本系统

**声明式测试脚本**：

```yaml
tasks:
  - name: 登录测试
    flow:
      - ai: "打开登录页面"
      - aiInput:
          locate: "用户名输入框"
          value: "test@example.com"
      - aiInput:
          locate: "密码输入框"
          value: "password123"
      - aiTap: "登录按钮"
      - aiAssert: "显示登录成功"
```

**优势**：
- 无需编程知识
- 可读性强
- 易于维护和版本管理

---

## 8. 设备抽象层设计

### 8.1 AbstractInterface

统一的设备控制接口：

```typescript
// packages/core/src/device/index.ts
export abstract class AbstractInterface {
  abstract interfaceType: string;           // 平台类型标识
  abstract screenshotBase64(): Promise<string>; // 截图
  abstract size(): Promise<Size>;           // 尺寸
  abstract actionSpace(): DeviceAction[];   // 支持的动作
  
  // 缓存相关（可选）
  abstract cacheFeatureForPoint?(center): Promise<ElementCacheFeature>;
  abstract rectMatchesCacheFeature?(feature): Promise<Rect>;
  
  // 输入原语（可选）
  inputPrimitives?: InputPrimitives;        // 统一输入接口
  
  // 生命周期
  abstract destroy?(): Promise<void>;
  abstract beforeInvokeAction?(actionName, param): Promise<void>;
  abstract afterInvokeAction?(actionName, param): Promise<void>;
}
```

### 8.2 InputPrimitives - 输入原语

统一的输入操作抽象：

```typescript
export interface InputPrimitives {
  pointer?: PointerInputPrimitives;   // 指针操作（点击/悬停）
  keyboard?: KeyboardInputPrimitives; // 键盘操作（输入/按键）
  touch?: TouchInputPrimitives;       // 触摸操作（滑动/捏合）
  scroll?: ScrollInputPrimitives;     // 滚动操作
  system?: SystemInputPrimitives;     // 系统操作（返回键/主页）
}

// 自动生成DeviceAction
export function defineActionsFromInputPrimitives(input: InputPrimitives): DeviceAction[] {
  // 根据inputPrimitives自动生成Tap/Input/Scroll等动作
}
```

### 8.3 平台适配示例

**Android适配**：

```typescript
// packages/android/src/agent.ts
export class AndroidAgent extends Agent<AndroidDevice> {
  // 通过ADB控制设备
  // 支持触摸、滑动、按键等移动端操作
}

// InputPrimitives实现
const input: MobileInputPrimitives = {
  pointer: { tap, doubleClick, longPress, dragAndDrop },
  keyboard: { typeText, keyboardPress, clearInput },
  touch: { swipe, pinch },
  system: { backButton, homeButton }
};
```

**Web适配**：

```typescript
// packages/web-integration/src/playwright/page.ts
export class PlaywrightWebPage extends AbstractInterface {
  interfaceType = 'playwright';
  
  async screenshotBase64() {
    return this.page.screenshot({ base64: true });
  }
  
  actionSpace() {
    return defineActionsFromInputPrimitives({
      pointer: { tap: (p) => this.page.mouse.click(p.x, p.y) },
      keyboard: { typeText: (v) => this.page.keyboard.type(v) },
      scroll: { scroll: (p) => this.page.mouse.wheel(p.deltaX, p.deltaY) }
    });
  }
}
```

---

## 9. 报告系统设计

### 9.1 ExecutionDump

执行过程记录：

```typescript
export class ExecutionDump {
  id: string;
  logTime: number;
  name: string;
  tasks: ExecutionTask[];
  
  // 每个任务包含：
  // - 截图记录
  // - AI调用记录（usage, rawResponse）
  // - 执行时间（timing）
  // - 错误信息（如果失败）
}
```

### 9.2 ReportActionDump

完整报告数据：

```typescript
export class ReportActionDump {
  sdkVersion: string;
  groupName: string;
  executions: ExecutionDump[];
  modelBriefs: ModelBrief[];  // 使用的模型列表
  
  // 序列化方式
  serialize(): string;                          // 文件引用模式
  serializeWithInlineScreenshots(): string;    // 内嵌截图模式
}
```

### 9.3 可视化报告

- **HTML报告**：可视化回放每一步操作
- **截图记录**：每步操作前后截图对比
- **AI思考**：展示AI的决策过程
- **时间统计**：每个操作的耗时分析

---

## 10. 与UIAI项目的对比参考

### 10.1 架构对比

| 特性 | Midscene.js | UIAI（我们的项目） |
|------|-------------|-------------------|
| 核心模式 | 智能自主Agent循环 | 智能自主Agent循环 |
| 定位方式 | 纯视觉定位 | 视觉+DOM混合定位 |
| 执行引擎 | TaskExecutor + TaskRunner | TestAgent + LoopDetector |
| 数据模型 | PlanningAction + ExecutionTask | AgentOutput + ActionModel |
| 缓存系统 | 三层缓存（Plan/Locate/Feature） | 任务缓存 |
| 多模型 | 意图路由（default/planning/insight） | 多模型配置 |

### 10.2 可借鉴的设计

1. **TaskExecutor架构**：
   - 清晰的Planning → Build → Execute → Feedback流程
   - 可复用的ExecutionSession封装

2. **缓存系统**：
   - Plan缓存：存储整个任务流程（YAML格式）
   - Locate缓存：存储元素定位结果
   - Feature缓存：提取元素特征快速匹配

3. **InputPrimitives抽象**：
   - 统一的输入原语接口
   - 自动生成DeviceAction
   - 跨平台适配简化

4. **Playwright集成**：
   - Fixture机制无缝集成
   - 自动报告生成和注解

5. **深度定位策略**：
   - 两阶段定位提高精度
   - 区域裁剪减少token消耗

### 10.3 差异化方向

1. **UIAI的优势**：
   - 四层运行模式（L1-L4）
   - 更灵活的混合定位策略
   - 代码录制功能
   - 自愈机制设计

2. **可增强的方向**：
   - 引入Midscene的深度定位策略
   - 增强缓存系统（三层缓存）
   - 完善InputPrimitives抽象
   - 优化Playwright集成方式

---

## 11. 总结

### 11.1 Midscene.js的核心价值

1. **纯视觉驱动**：彻底摆脱DOM依赖，实现真正的跨平台统一
2. **自然语言接口**：降低自动化测试门槛，非程序员也能编写测试
3. **智能缓存**：大幅提升执行效率，降低AI调用成本
4. **多模型策略**：根据任务类型选择最优模型，平衡成本和效果
5. **完善的生态**：Chrome扩展、CLI、Playwright集成、YAML脚本

### 11.2 关键技术亮点

- **Agent架构**：清晰的职责划分，可扩展的设计
- **TaskExecutor**：完善的执行流程，支持重新规划
- **Service层**：统一的AI调用接口，支持多种VL模型
- **AbstractInterface**：跨平台抽象，简化平台适配
- **报告系统**：可视化回放，便于调试和分析

### 11.3 对UIAI项目的启示

Midscene.js 提供了一个成熟的AI驱动自动化测试框架的完整实现，其架构设计、缓存策略、跨平台抽象等都是值得借鉴的优秀实践。结合我们UIAI项目的四层运行模式、混合定位策略、代码录制等特色功能，可以打造一个更强大、更灵活的UI AI自动化测试框架。

---

**参考资料**：
- [Midscene.js 官方文档](https://midscenejs.com/)
- [GitHub仓库](https://github.com/web-infra-dev/midscene)
- [源码分析](https://deepwiki.com/web-infra-dev/midscene)