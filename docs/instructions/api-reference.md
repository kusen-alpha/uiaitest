# API 参考

本文档详细介绍 UIAI 的核心 API。

---

## 目录

1. [TestOrchestrator](#一testorchestrator)
2. [TestCase](#二testcase)
3. [Locator](#三locator)
4. [TestResult](#四testresult)
5. [BaseExecutor](#五baseexecutor)
6. [PerceptionEngine](#六perceptionengine)
7. [CacheManager](#七cachemanager)
8. [KnowledgeManager](#八knowledgemanager)
9. [WatchdogManager](#九watchdogmanager)
10. [AssertionEngine](#十assertionengine)
11. [EventBus](#十一eventbus)

---

## 一、TestOrchestrator

测试编排调度中控，核心入口类。

### 1.1 导入

```python
from uiai import TestOrchestrator
from uiai.config import UIAIConfig
```

### 1.2 初始化

```python
TestOrchestrator(config: UIAIConfig | None = None)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| config | UIAIConfig | 配置对象，为 None 时使用默认配置 |

### 1.3 run_test（R1 脚本模式）

```python
async def run_test(
    test_case: TestCase,
    executor: BaseExecutor | None = None
) -> TestResult
```

执行单个测试用例（确定性脚本模式）。

| 参数 | 类型 | 说明 |
|------|------|------|
| test_case | TestCase | 测试用例对象 |
| executor | BaseExecutor | 执行器，为 None 时自动创建 |

**返回**: TestResult 测试结果对象

**示例**:

```python
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig

async def main():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    test = TestCase(id="login", name="登录测试")
    test.add_step("导航", "navigate", value="https://example.com/login")
    test.add_step("点击", "click", locator=Locator.by_role("button", name="登录"))
    
    result = await orchestrator.run_test(test)
    print(result.status.value)  # passed / failed / healed

asyncio.run(main())
```

### 1.4 run_agent_test（R2 Agent 模式）

```python
async def run_agent_test(
    task: str,
    executor: BaseExecutor | None = None,
    perception_mode: PerceptionMode = PerceptionMode.HYBRID,
    max_steps: int = 50,
    initial_actions: list[dict] | None = None
) -> TestResult
```

执行自然语言驱动的测试（Agent 自主循环模式）。

| 参数 | 类型 | 说明 |
|------|------|------|
| task | str | 自然语言任务描述 |
| executor | BaseExecutor | 执行器 |
| perception_mode | PerceptionMode | 感知模式 |
| max_steps | int | 最大执行步数 |
| initial_actions | list[dict] | 确定性预步骤 |

**返回**: TestResult 测试结果对象

**示例**:

```python
from uiai.core.perception import PerceptionMode

result = await orchestrator.run_agent_test(
    "登录系统并查看订单列表",
    perception_mode=PerceptionMode.HYBRID,
    max_steps=30,
    initial_actions=[
        {"action_type": "navigate", "params": {"url": "https://example.com"}}
    ]
)
```

### 1.5 run_suite

```python
async def run_suite(
    test_cases: list[TestCase],
    platform: Platform = Platform.WEB
) -> SuiteResult
```

执行测试套件。

| 参数 | 类型 | 说明 |
|------|------|------|
| test_cases | list[TestCase] | 测试用例列表 |
| platform | Platform | 平台类型 |

**返回**: SuiteResult 测试套件结果

**示例**:

```python
tests = [
    TestCase(id="login", name="登录测试"),
    TestCase(id="search", name="搜索测试"),
]

result = await orchestrator.run_suite(tests)
print(f"通过: {result.passed_count}")
print(f"失败: {result.failed_count}")
```

### 1.6 generate_test_plan

```python
async def generate_test_plan(
    requirement: str,
    **kwargs
) -> AgentOutput
```

生成测试计划（PlannerAgent）。

| 参数 | 类型 | 说明 |
|------|------|------|
| requirement | str | 需求描述 |

**返回**: AgentOutput 包含测试计划

**示例**:

```python
plan = await orchestrator.generate_test_plan(
    requirement="测试购物车功能：添加商品、修改数量、删除商品"
)

print(plan.output)  # Markdown 格式的测试计划
```

### 1.7 generate_test_code

```python
async def generate_test_code(
    plan: str,
    **kwargs
) -> AgentOutput
```

从测试计划生成测试代码（GeneratorAgent）。

| 参数 | 类型 | 说明 |
|------|------|------|
| plan | str | 测试计划（Markdown） |

**返回**: AgentOutput 包含测试代码

**示例**:

```python
code = await orchestrator.generate_test_code(plan.output)
print(code.output)  # Python 测试代码
```

### 1.8 explore

```python
async def explore(
    url: str,
    **kwargs
) -> AgentOutput
```

AI 探索性测试（ExplorerAgent）。

| 参数 | 类型 | 说明 |
|------|------|------|
| url | str | 目标 URL |
| max_pages | int | 最大探索页面数 |
| max_depth | int | 最大探索深度 |

**返回**: AgentOutput 包含发现的问题

**示例**:

```python
result = await orchestrator.explore(
    url="https://example.com",
    max_pages=20,
    max_depth=3
)

for issue in result.issues:
    print(f"问题: {issue.description}")
```

---

## 二、TestCase

测试用例模型。

### 2.1 导入

```python
from uiai import TestCase, TestStep
from uiai.core.test_case import TestCaseType, Priority
```

### 2.2 创建测试用例

```python
TestCase(
    id: str,
    name: str,
    steps: list[TestStep] = [],
    case_type: TestCaseType = TestCaseType.SCRIPT,
    priority: Priority = Priority.MEDIUM,
    platform: str = "web",
    tags: list[str] = [],
    preconditions: list[str] = [],
    fixtures: dict = {},
    source: str = "manual",
    metadata: dict = {}
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| id | str | 用例唯一标识 |
| name | str | 用例名称 |
| steps | list[TestStep] | 测试步骤列表 |
| case_type | TestCaseType | 用例类型 |
| priority | Priority | 优先级 |
| platform | str | 平台：web / android / ios |
| tags | list[str] | 标签 |
| preconditions | list[str] | 前置条件 |
| fixtures | dict | Fixture 数据 |
| source | str | 来源：manual / ai_generated / recorded |
| metadata | dict | 元数据 |

### 2.3 TestCaseType 枚举

| 值 | 说明 |
|------|------|
| SCRIPT | 确定性脚本 |
| NATURAL_LANGUAGE | 自然语言用例 |
| RECORDED | 录制用例 |
| DATA_DRIVEN | 数据驱动 |
| AI_GENERATED | AI 生成 |

### 2.4 Priority 枚举

| 值 | 说明 |
|------|------|
| SMOKE | 冒烟测试 |
| CRITICAL | 关键功能 |
| HIGH | 高优先级 |
| MEDIUM | 中优先级 |
| LOW | 低优先级 |

### 2.5 添加步骤（链式调用）

```python
def add_step(
    name: str,
    action: str,
    locator: Locator | None = None,
    value: str | None = None,
    expected: str | None = None,
    timeout: int | None = None
) -> TestCase
```

| 参数 | 类型 | 说明 |
|------|------|------|
| name | str | 步骤名称 |
| action | str | 动作类型 |
| locator | Locator | 定位器 |
| value | str | 输入值 |
| expected | str | 预期结果 |
| timeout | int | 超时时间 |

**返回**: TestCase（支持链式调用）

**示例**:

```python
test = TestCase(id="login", name="登录测试")

test.add_step("导航到登录页", "navigate", value="https://example.com/login")
    .add_step("输入用户名", "type", locator=Locator.by_test_id("username"), value="admin")
    .add_step("输入密码", "type", locator=Locator.by_test_id("password"), value="123456")
    .add_step("点击登录", "click", locator=Locator.by_role("button", name="登录"))
    .add_step("验证跳转", "assert_url", value="https://example.com/home")
```

### 2.6 支持的动作类型

| 动作 | 说明 | 参数 |
|------|------|------|
| navigate | 导航到 URL | value: URL |
| click | 点击元素 | locator |
| type | 输入文本 | locator, value |
| fill | 填充表单 | locator, value |
| select | 选择下拉选项 | locator, value |
| check | 勾选复选框 | locator |
| uncheck | 取消勾选 | locator |
| hover | 悬停 | locator |
| press | 按键 | value: key |
| wait | 等待 | locator, timeout |
| screenshot | 截图 | value: path |
| assert_visible | 断言可见 | locator |
| assert_text | 断言文本 | locator, value |
| assert_url | 断言 URL | value |
| assert_title | 断言标题 | value |
| scroll | 滚动 | value: direction |
| drag | 拖拽 | locator, value: target |

---

## 三、Locator

定位器抽象，支持多策略降级。

### 3.1 导入

```python
from uiai import Locator, LocatorType
```

### 3.2 创建定位器

```python
# 通过角色定位（推荐）
Locator.by_role(role: str, name: str | None = None)

# 通过 TestID 定位
Locator.by_test_id(test_id: str)

# 通过标签文本定位
Locator.by_label(text: str)

# 通过占位符定位
Locator.by_placeholder(text: str)

# 通过文本定位
Locator.by_text(text: str, exact: bool = False)

# 通过 Alt 文本定位
Locator.by_alt_text(text: str)

# 通过 Title 定位
Locator.by_title(text: str)

# CSS 选择器
Locator.by_css(selector: str)

# XPath
Locator.by_xpath(xpath: str)

# 图像识别定位
Locator.by_image(image_path: str, threshold: float = 0.9)

# OCR 文字定位
Locator.by_ocr(text: str)

# 坐标定位（最低优先级）
Locator.by_coordinate(x: int, y: int)

# App 端定位
Locator.by_accessibility_id(id: str)
```

### 3.3 LocatorType 枚举（按优先级排序）

| 类型 | 说明 | 优先级 |
|------|------|--------|
| ROLE | getByRole | 最高 |
| TEST_ID | getByTestId | 高 |
| LABEL | getByLabel | 高 |
| PLACEHOLDER | getByPlaceholder | 中 |
| TEXT | getByText | 中 |
| ALT_TEXT | getByAltText | 中 |
| TITLE | getByTitle | 中 |
| CSS | CSS 选择器 | 低 |
| XPATH | XPath | 低 |
| ACCESSIBILITY_ID | App 端定位 | 中 |
| IMAGE | 图像识别 | 低 |
| OCR | OCR 文字定位 | 低 |
| COORDINATE | 坐标定位 | 最低 |

### 3.4 添加降级策略

```python
def with_fallback(
    type: LocatorType,
    value: str
) -> Locator
```

| 参数 | 类型 | 说明 |
|------|------|------|
| type | LocatorType | 定位类型 |
| value | str | 定位值 |

**返回**: Locator（支持链式调用）

**示例**:

```python
locator = Locator.by_test_id("username")
    .with_fallback(LocatorType.CSS, "#username")
    .with_fallback(LocatorType.XPATH, "//input[@name='username']")
    .with_fallback(LocatorType.TEXT, "用户名")
```

### 3.5 定位器属性

```python
locator.type        # LocatorType
locator.value       # 定位值
locator.fallbacks   # 降级策略列表
```

---

## 四、TestResult

测试结果模型。

### 4.1 导入

```python
from uiai import TestResult, TestStatus
```

### 4.2 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| test_id | str | 用例 ID |
| test_name | str | 用例名称 |
| status | TestStatus | 测试状态 |
| steps | list[StepResult] | 步骤结果列表 |
| error | str | 错误信息 |
| duration_ms | int | 总耗时（毫秒） |
| healing_records | list | 自愈记录 |
| recorded_code | str | 录制的代码 |
| screenshots | list[str] | 截图路径列表 |
| trace_path | str | Trace 文件路径 |
| metadata | dict | 元数据 |

### 4.3 TestStatus 枚举

| 值 | 说明 |
|------|------|
| PASSED | 通过 |
| FAILED | 失败 |
| HEALED | 自愈成功 |
| SKIPPED | 跳过 |
| ERROR | 执行错误 |

### 4.4 StepResult

| 属性 | 类型 | 说明 |
|------|------|------|
| name | str | 步骤名称 |
| action | str | 动作类型 |
| status | TestStatus | 步骤状态 |
| duration_ms | int | 步骤耗时 |
| error | str | 错误信息 |
| screenshot | str | 截图路径 |

---

## 五、BaseExecutor

执行器基类，定义统一的操作接口。

### 5.1 导入

```python
from uiai.executor.base import BaseExecutor
from uiai.executor.playwright_executor import PlaywrightExecutor
from uiai.executor.appium_executor import AppiumExecutor
```

### 5.2 核心方法

#### start

```python
async def start(**kwargs) -> None
```

启动执行器。

#### stop

```python
async def stop() -> None
```

停止执行器。

#### navigate

```python
async def navigate(url: str) -> None
```

导航到 URL。

#### click

```python
async def click(locator: Locator) -> None
```

点击元素。

#### type_text

```python
async def type_text(locator: Locator, text: str, clear: bool = True) -> None
```

输入文本。

| 参数 | 类型 | 说明 |
|------|------|------|
| locator | Locator | 定位器 |
| text | str | 输入文本 |
| clear | bool | 是否先清空 |

#### fill

```python
async def fill(locator: Locator, value: str) -> None
```

填充表单。

#### select_option

```python
async def select_option(locator: Locator, value: str) -> None
```

选择下拉选项。

#### check

```python
async def check(locator: Locator) -> None
```

勾选复选框。

#### uncheck

```python
async def uncheck(locator: Locator) -> None
```

取消勾选。

#### hover

```python
async def hover(locator: Locator) -> None
```

悬停。

#### press_key

```python
async def press_key(key: str) -> None
```

按键。

| key | 说明 |
|------|------|
| Enter | 回车 |
| Tab | Tab |
| Escape | Esc |
| ArrowUp | 上箭头 |
| ArrowDown | 下箭头 |
| ArrowLeft | 左箭头 |
| ArrowRight | 右箭头 |

#### wait_for

```python
async def wait_for(locator: Locator, timeout: int | None = None) -> None
```

等待元素出现。

#### screenshot

```python
async def screenshot(path: str | None = None) -> str
```

截图。

**返回**: 截图路径

#### get_text

```python
async def get_text(locator: Locator) -> str
```

获取元素文本。

#### is_visible

```python
async def is_visible(locator: Locator) -> bool
```

判断元素是否可见。

#### get_url

```python
async def get_url() -> str
```

获取当前 URL。

#### get_title

```python
async def get_title() -> str
```

获取页面标题。

#### get_accessibility_tree

```python
async def get_accessibility_tree() -> dict
```

获取 Accessibility Tree。

#### evaluate

```python
async def evaluate(expression: str) -> Any
```

执行 JavaScript。

---

## 六、PerceptionEngine

感知模式引擎。

### 6.1 导入

```python
from uiai.core.perception import PerceptionEngine, PerceptionMode
```

### 6.2 PerceptionMode 枚举

| 值 | 说明 |
|------|------|
| A11Y_SNAPSHOT | Accessibility Tree 快照 |
| DOM_SERIALIZE | DOM 序列化 |
| VISUAL_SCREENSHOT | 截图 + VL 模型 |
| HYBRID | DOM 优先，视觉降级 |

### 6.3 创建感知引擎

```python
PerceptionEngine(
    executor: BaseExecutor,
    vl_client: LLMClient | None = None,
    default_mode: PerceptionMode = PerceptionMode.HYBRID
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| executor | BaseExecutor | 执行器 |
| vl_client | LLMClient | VL 模型客户端 |
| default_mode | PerceptionMode | 默认感知模式 |

### 6.4 执行感知

```python
async def perceive(
    mode: PerceptionMode | None = None
) -> PerceptionResult
```

| 参数 | 类型 | 说明 |
|------|------|------|
| mode | PerceptionMode | 感知模式，为 None 时使用默认 |

**返回**: PerceptionResult 感知结果

### 6.5 格式化为 LLM 输入

```python
def format_for_llm(
    result: PerceptionResult,
    max_tokens: int = 4000
) -> str
```

| 参数 | 类型 | 说明 |
|------|------|------|
| result | PerceptionResult | 感知结果 |
| max_tokens | int | 最大 tokens |

**返回**: 格式化后的文本

---

## 七、CacheManager

三层缓存管理器。

### 7.1 导入

```python
from uiai.core.cache import CacheManager
```

### 7.2 创建缓存管理器

```python
CacheManager(
    storage_dir: str = "./.uiai_cache",
    max_entries: int = 1000,
    ttl: int = 3600
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| storage_dir | str | 存储目录 |
| max_entries | int | 最大条目数 |
| ttl | int | 缓存 TTL（秒） |

### 7.3 核心方法

#### get_plan

```python
async def get_plan(task_desc: str) -> PlanCache | None
```

获取任务流程缓存。

#### set_plan

```python
async def set_plan(
    task_desc: str,
    workflow: list,
    version_hash: str
) -> None
```

设置任务流程缓存。

#### get_locate

```python
async def get_locate(description: str) -> LocateCache | None
```

获取元素定位缓存。

#### set_locate

```python
async def set_locate(
    description: str,
    location: dict,
    feature_hash: str
) -> None
```

设置元素定位缓存。

#### get_feature

```python
async def get_feature(description: str) -> FeatureCache | None
```

获取视觉特征缓存。

#### set_feature

```python
async def set_feature(
    description: str,
    features: list
) -> None
```

设置视觉特征缓存。

#### stats

```python
async def stats() -> dict
```

获取缓存统计。

**返回**: 
```python
{
    "plan_count": 10,
    "locate_count": 50,
    "feature_count": 20,
    "total_size": 1024
}
```

#### clear_all

```python
async def clear_all() -> None
```

清除所有缓存。

#### save_to_disk

```python
async def save_to_disk() -> None
```

持久化到磁盘。

#### load_from_disk

```python
async def load_from_disk() -> None
```

从磁盘加载。

---

## 八、KnowledgeManager

知识沉淀管理器。

### 8.1 导入

```python
from uiai.core.knowledge import KnowledgeManager, KnowledgeLevel
```

### 8.2 KnowledgeLevel 枚举

| 值 | 说明 |
|------|------|
| REQUIREMENT | 需求级 |
| PRODUCT | 产品级 |
| EXPERIENCE | 经验级 |

### 8.3 创建知识管理器

```python
KnowledgeManager(
    storage_dir: str = "./.uiai_knowledge",
    max_entries: int = 500
)
```

### 8.4 添加知识

#### add_requirement

```python
async def add_requirement(
    domain: str,
    title: str,
    content: str,
    tags: list[str] = []
) -> KnowledgeEntry
```

添加需求级知识。

#### add_product

```python
async def add_product(
    domain: str,
    title: str,
    content: str
) -> KnowledgeEntry
```

添加产品级知识。

#### add_experience

```python
async def add_experience(
    domain: str,
    title: str,
    content: str,
    source: str = "agent_learned",
    success: bool = True
) -> KnowledgeEntry
```

添加经验级知识。

### 8.5 搜索知识

```python
async def search(
    query: str,
    domain: str | None = None,
    level: KnowledgeLevel | None = None,
    top_k: int = 5
) -> list[KnowledgeEntry]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| query | str | 搜索关键词 |
| domain | str | 业务领域 |
| level | KnowledgeLevel | 知识级别 |
| top_k | int | 返回数量 |

**返回**: 知识条目列表

### 8.6 构建上下文

```python
async def build_context(
    query: str,
    domain: str | None = None,
    max_tokens: int = 2000
) -> str
```

为 Agent 构建知识上下文。

**返回**: 格式化的知识上下文文本

---

## 九、WatchdogManager

Watchdog 守卫管理器。

### 9.1 导入

```python
from uiai.core.watchdog import WatchdogManager, BaseWatchdog
from uiai.core.watchdog.popup import PopupWatchdog
from uiai.core.watchdog.captcha import CaptchaWatchdog
```

### 9.2 创建管理器

```python
WatchdogManager(event_bus: EventBus)
```

### 9.3 注册 Watchdog

```python
def register(watchdog: BaseWatchdog) -> None
```

### 9.4 启动/停止

```python
async def start_all() -> None
async def stop_all() -> None
```

### 9.5 示例

```python
from uiai.core.eventbus import EventBus

event_bus = EventBus()
manager = WatchdogManager(event_bus)

# 注册 Watchdog
manager.register(PopupWatchdog(event_bus))
manager.register(CaptchaWatchdog(event_bus, totp_secret="xxx"))

# 启动
await manager.start_all()

# 停止
await manager.stop_all()
```

---

## 十、AssertionEngine

断言引擎。

### 10.1 导入

```python
from uiai.assertion.engine import AssertionEngine, AssertionType
```

### 10.2 AssertionType 枚举

| 值 | 说明 |
|------|------|
| VISIBLE | 可见断言 |
| TEXT_EQUALS | 文本相等 |
| TEXT_CONTAINS | 文本包含 |
| URL_EQUALS | URL 相等 |
| URL_CONTAINS | URL 包含 |
| TITLE_EQUALS | 标题相等 |
| ATTRIBUTE | 属性断言 |
| COUNT | 数量断言 |

### 10.3 断言方法

#### assert_visible

```python
async def assert_visible(locator: Locator) -> AssertionResult
```

断言元素可见。

#### assert_text_equals

```python
async def assert_text_equals(
    locator: Locator,
    expected: str
) -> AssertionResult
```

断言文本相等。

#### assert_text_contains

```python
async def assert_text_contains(
    locator: Locator,
    text: str
) -> AssertionResult
```

断言文本包含。

#### assert_url_equals

```python
async def assert_url_equals(expected: str) -> AssertionResult
```

断言 URL 相等。

#### assert_url_contains

```python
async def assert_url_contains(text: str) -> AssertionResult
```

断言 URL 包含。

#### assert_title_equals

```python
async def assert_title_equals(expected: str) -> AssertionResult
```

断言标题相等。

#### assert_attribute

```python
async def assert_attribute(
    locator: Locator,
    attribute: str,
    value: str
) -> AssertionResult
```

断言属性值。

#### assert_count

```python
async def assert_count(
    locator: Locator,
    expected: int
) -> AssertionResult
```

断言元素数量。

---

## 十一、EventBus

事件总线，用于模块间通信。

### 11.1 导入

```python
from uiai.core.eventbus import EventBus, Event
```

### 11.2 创建 EventBus

```python
EventBus()
```

### 11.3 发布事件

```python
async def publish(
    event_type: str,
    data: dict | None = None
) -> None
```

| 参数 | 类型 | 说明 |
|------|------|------|
| event_type | str | 事件类型 |
| data | dict | 事件数据 |

### 11.4 订阅事件

```python
def subscribe(
    handler: Callable,
    event_type: str | None = None
) -> str
```

| 参数 | 类型 | 说明 |
|------|------|------|
| handler | Callable | 事件处理器 |
| event_type | str | 事件类型，为 None 时订阅所有 |

**返回**: 处理器 ID

### 11.5 取消订阅

```python
def unsubscribe(handler_id: str) -> None
```

### 11.6 事件类型

| 事件类型 | 说明 |
|---------|------|
| POPUP_DETECTED | 弹窗检测 |
| POPUP_HANDLED | 弹窗处理完成 |
| CAPTCHA_DETECTED | 验证码检测 |
| CRASH_DETECTED | 崩溃检测 |
| CRASH_RECOVERED | 崩溃恢复 |
| NETWORK_ERROR | 网络错误 |
| DOM_CHANGED | DOM 变更 |
| STEP_COMPLETED | 步骤完成 |
| TEST_COMPLETED | 测试完成 |

### 11.7 示例

```python
event_bus = EventBus()

# 订阅事件
async def on_popup(event: Event):
    print(f"弹窗检测: {event.data}")

handler_id = event_bus.subscribe(on_popup, "POPUP_DETECTED")

# 发布事件
await event_bus.publish("POPUP_DETECTED", {"type": "alert", "message": "提示"})

# 取消订阅
event_bus.unsubscribe(handler_id)
```

---

> **下一步**: 查看 [CLI 命令参考](./cli-reference.md) 或 [最佳实践](./best-practices.md)。