# 开发者指南

本文档介绍如何扩展和定制 UIAI。

---

## 目录

1. [开发环境搭建](#一开发环境搭建)
2. [扩展 Agent](#二扩展-agent)
3. [扩展 Watchdog](#三扩展-watchdog)
4. [扩展执行器](#四扩展执行器)
5. [扩展插件](#五扩展插件)
6. [扩展技能](#六扩展技能)
7. [贡献代码](#七贡献代码)
8. [代码规范](#八代码规范)

---

## 一、开发环境搭建

### 1.1 克隆仓库

```bash
git clone https://github.com/uiai-framework/uiai.git
cd uiai
```

### 1.2 安装开发依赖

```bash
# 使用 pip
pip install -e ".[dev]"

# 或使用 poetry
poetry install --with dev
```

### 1.3 安装 Playwright

```bash
playwright install chromium
```

### 1.4 运行测试

```bash
pytest tests/ -v
```

### 1.5 项目结构

```
uiai/
├── uiai/
│   ├── __init__.py          # 包入口
│   ├── config.py            # 配置模块
│   ├── cli.py               # CLI 模块
│   ├── core/                # 核心模块
│   │   ├── test_case.py     # 测试用例
│   │   ├── locator.py       # 定位器
│   │   ├── perception.py    # 感知引擎
│   │   ├── watchdog.py      # Watchdog
│   │   ├── cache.py         # 缓存
│   │   ├── knowledge.py     # 知识库
│   │   └── eventbus.py      # 事件总线
│   ├── agent/               # Agent 模块
│   │   ├── base.py          # Agent 基类
│   │   ├── planner.py       # 规划 Agent
│   │   ├── executor.py      # 执行 Agent
│   │   ├── judge.py         # 评估 Agent
│   │   ├── healer.py        # 修复 Agent
│   │   ├── explorer.py      # 探索 Agent
│   │   └── recorder.py      # 录制 Agent
│   ├── executor/            # 执行器模块
│   │   ├── base.py          # 执行器基类
│   │   ├── playwright.py    # Playwright 执行器
│   │   └── appium.py        # Appium 执行器
│   ├── orchestrator/        # 编排模块
│   │   └ orchestrator.py    # 编排器
│   ├── assertion/           # 断言模块
│   │   └ engine.py          # 断言引擎
│   ├── plugins/             # 插件模块
│   │   ├── manager.py       # 插件管理
│   │   └ base.py            # 插件基类
│   └── skills/              # 技能模块
│       ├── registry.py      # 技能注册
│       └ base.py            # 技能基类
├── tests/                   # 测试目录
├── docs/                    # 文档目录
├── pyproject.toml           # 项目配置
└── README.md                # 项目说明
```

---

## 二、扩展 Agent

### 2.1 Agent 基类

```python
from uiai.agent.base import BaseAgent, AgentRole, AgentOutput

class BaseAgent:
    """Agent 基类"""
    
    name: str                    # Agent 名称
    role: AgentRole              # Agent 角色
    llm_client: LLMClient        # LLM 客户端
    
    async def run(self, input_data, **kwargs) -> AgentOutput:
        """执行 Agent 任务"""
        raise NotImplementedError
    
    async def _build_prompt(self, input_data) -> str:
        """构建提示词"""
        raise NotImplementedError
    
    async def _parse_output(self, response) -> AgentOutput:
        """解析输出"""
        raise NotImplementedError
```

### 2.2 创建自定义 Agent

```python
from uiai.agent.base import BaseAgent, AgentRole, AgentOutput
from uiai.core.eventbus import EventBus

class MyCustomAgent(BaseAgent):
    """自定义 Agent"""
    
    def __init__(self, llm_client=None, event_bus=None):
        super().__init__(
            name="MyCustomAgent",
            role=AgentRole.EXECUTOR,  # 或自定义角色
            llm_client=llm_client
        )
        self._bus = event_bus or EventBus()
    
    async def run(self, input_data, **kwargs) -> AgentOutput:
        """执行自定义逻辑"""
        # 1. 构建提示词
        prompt = self._build_prompt(input_data)
        
        # 2. 调用 LLM
        response = await self.llm_client.chat([
            {"role": "system", "content": "你是一个自定义 Agent"},
            {"role": "user", "content": prompt}
        ])
        
        # 3. 解析输出
        output = self._parse_output(response)
        
        # 4. 发布事件
        await self._bus.publish("CUSTOM_AGENT_COMPLETED", {
            "agent": self.name,
            "result": output.data
        })
        
        return output
    
    async def _build_prompt(self, input_data) -> str:
        """构建提示词"""
        return f"""
        任务: {input_data.get('task')}
        上下文: {input_data.get('context')}
        
        请分析并给出执行建议。
        """
    
    async def _parse_output(self, response) -> AgentOutput:
        """解析输出"""
        return AgentOutput(
            role=self.role,
            success=True,
            data={"suggestion": response},
            message="执行成功"
        )
```

### 2.3 注册 Agent

```python
from uiai import TestOrchestrator
from uiai.config import UIAIConfig

config = UIAIConfig()
orchestrator = TestOrchestrator(config)

# 注册自定义 Agent
custom_agent = MyCustomAgent(llm_client=config.llm)
orchestrator.register_agent(custom_agent)
```

### 2.4 AgentRole 枚举

| 角色 | 说明 |
|------|------|
| PLANNER | 规划角色 |
| EXECUTOR | 执行角色 |
| JUDGE | 评估角色 |
| HEALER | 修复角色 |
| EXPLORER | 探索角色 |
| RECORDER | 录制角色 |

---

## 三、扩展 Watchdog

### 3.1 Watchdog 基类

```python
from uiai.core.watchdog import BaseWatchdog
from uiai.core.eventbus import Event

class BaseWatchdog:
    """Watchdog 基类"""
    
    @property
    def name(self) -> str:
        """Watchdog 名称"""
        raise NotImplementedError
    
    async def start(self) -> None:
        """启动 Watchdog"""
        raise NotImplementedError
    
    async def stop(self) -> None:
        """停止 Watchdog"""
        raise NotImplementedError
    
    async def on_event(self, event: Event) -> dict | None:
        """处理事件"""
        raise NotImplementedError
```

### 3.2 创建自定义 Watchdog

```python
from uiai.core.watchdog import BaseWatchdog
from uiai.core.eventbus import Event, EventBus

class MyCustomWatchdog(BaseWatchdog):
    """自定义 Watchdog"""
    
    def __init__(self, event_bus: EventBus):
        self._bus = event_bus
        self._handler_id = None
    
    @property
    def name(self) -> str:
        return "my_custom"
    
    async def start(self) -> None:
        """启动 Watchdog"""
        # 注册事件订阅
        self._handler_id = self._bus.subscribe(
            self._handle_event,
            event_type="my_custom_event"
        )
        
        # 初始化资源
        self._init_resources()
    
    async def stop(self) -> None:
        """停止 Watchdog"""
        # 取消订阅
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
        
        # 清理资源
        self._cleanup_resources()
    
    async def on_event(self, event: Event) -> dict | None:
        """处理事件"""
        # 处理逻辑
        result = await self._process_event(event)
        
        # 发布处理完成事件
        await self._bus.publish("MY_CUSTOM_HANDLED", {
            "original_event": event.type,
            "result": result
        })
        
        return result
    
    async def _handle_event(self, event: Event):
        """事件处理器"""
        return await self.on_event(event)
    
    def _init_resources(self):
        """初始化资源"""
        pass
    
    def _cleanup_resources(self):
        """清理资源"""
        pass
    
    async def _process_event(self, event: Event) -> dict:
        """处理事件"""
        return {"processed": True}
```

### 3.3 注册 Watchdog

```python
from uiai.core.watchdog import WatchdogManager
from uiai.core.eventbus import EventBus

event_bus = EventBus()
manager = WatchdogManager(event_bus)

# 注册自定义 Watchdog
custom_watchdog = MyCustomWatchdog(event_bus)
manager.register(custom_watchdog)

# 启动
await manager.start_all()

# 停止
await manager.stop_all()
```

---

## 四、扩展执行器

### 4.1 Executor 基类

```python
from uiai.executor.base import BaseExecutor
from uiai.core.locator import Locator
from uiai.core.platform import Platform

class BaseExecutor:
    """执行器基类"""
    
    platform: Platform
    
    async def start(self, **kwargs) -> None:
        """启动执行器"""
        raise NotImplementedError
    
    async def stop(self) -> None:
        """停止执行器"""
        raise NotImplementedError
    
    async def navigate(self, url: str) -> None:
        """导航"""
        raise NotImplementedError
    
    async def click(self, locator: Locator) -> None:
        """点击"""
        raise NotImplementedError
    
    async def type_text(self, locator: Locator, text: str) -> None:
        """输入"""
        raise NotImplementedError
    
    # ... 其他方法
```

### 4.2 创建自定义执行器

```python
from uiai.executor.base import BaseExecutor
from uiai.core.locator import Locator, LocatorType
from uiai.core.platform import Platform

class MyCustomExecutor(BaseExecutor):
    """自定义执行器"""
    
    platform = Platform.WEB
    
    def __init__(self, config):
        self._config = config
        self._driver = None
    
    async def start(self, **kwargs) -> None:
        """启动执行器"""
        # 初始化驱动
        self._driver = self._init_driver()
    
    async def stop(self) -> None:
        """停止执行器"""
        if self._driver:
            self._driver.close()
            self._driver = None
    
    async def navigate(self, url: str) -> None:
        """导航"""
        self._driver.get(url)
    
    async def click(self, locator: Locator) -> None:
        """点击"""
        element = await self._find_element(locator)
        element.click()
    
    async def type_text(self, locator: Locator, text: str) -> None:
        """输入"""
        element = await self._find_element(locator)
        element.clear()
        element.send_keys(text)
    
    async def _find_element(self, locator: Locator):
        """查找元素"""
        # 尝试主定位器
        try:
            return self._locate_by_type(locator.type, locator.value)
        except:
            # 尝试降级策略
            for fallback in locator.fallbacks:
                try:
                    return self._locate_by_type(fallback.type, fallback.value)
                except:
                    continue
            raise Exception(f"Element not found: {locator}")
    
    def _locate_by_type(self, type: LocatorType, value: str):
        """按类型定位"""
        if type == LocatorType.CSS:
            return self._driver.find_element("css selector", value)
        elif type == LocatorType.XPATH:
            return self._driver.find_element("xpath", value)
        # ... 其他类型
```

### 4.3 注册执行器

```python
from uiai import TestOrchestrator
from uiai.executor.base import ExecutorFactory

# 注册自定义执行器
ExecutorFactory.register("custom", MyCustomExecutor)

# 使用自定义执行器
orchestrator = TestOrchestrator(config)
result = await orchestrator.run_test(test, executor_type="custom")
```

---

## 五、扩展插件

### 5.1 Plugin 基类

```python
from uiai.plugins.base import BasePlugin, PluginHook

class BasePlugin:
    """插件基类"""
    
    name: str
    version: str
    
    async def on_hook(self, hook: PluginHook, data: dict) -> dict:
        """处理钩子"""
        raise NotImplementedError
```

### 5.2 PluginHook 枚举

| 钩子 | 说明 |
|------|------|
| BEFORE_TEST | 测试前 |
| AFTER_TEST | 测试后 |
| BEFORE_STEP | 步骤前 |
| AFTER_STEP | 步骤后 |
| ON_ERROR | 错误时 |
| ON_HEALING | 自愈时 |

### 5.3 创建自定义插件

```python
from uiai.plugins.base import BasePlugin, PluginHook

class MyCustomPlugin(BasePlugin):
    """自定义插件"""
    
    name = "MyCustomPlugin"
    version = "1.0.0"
    
    async def on_hook(self, hook: PluginHook, data: dict) -> dict:
        """处理钩子"""
        if hook == PluginHook.BEFORE_TEST:
            # 测试前处理
            return await self._before_test(data)
        
        elif hook == PluginHook.AFTER_TEST:
            # 测试后处理
            return await self._after_test(data)
        
        elif hook == PluginHook.ON_ERROR:
            # 错误处理
            return await self._on_error(data)
        
        return data
    
    async def _before_test(self, data: dict) -> dict:
        """测试前处理"""
        # 添加自定义数据
        data["custom_context"] = "..."
        return data
    
    async def _after_test(self, data: dict) -> dict:
        """测试后处理"""
        # 处理测试结果
        result = data.get("result")
        # 自定义逻辑
        return data
    
    async def _on_error(self, data: dict) -> dict:
        """错误处理"""
        # 处理错误
        error = data.get("error")
        # 自定义逻辑
        return data
```

### 5.4 注册插件

```python
from uiai.plugins.manager import PluginManager

manager = PluginManager()

# 注册插件
manager.register(MyCustomPlugin())

# 启用插件
manager.enable("MyCustomPlugin")

# 禁用插件
manager.disable("MyCustomPlugin")
```

---

## 六、扩展技能

### 6.1 Skill 基类

```python
from uiai.skills.base import Skill, InputPrimitive

class Skill:
    """技能基类"""
    
    name: str
    description: str
    input_primitives: list[InputPrimitive]
    
    async def execute(self, context, inputs) -> dict:
        """执行技能"""
        raise NotImplementedError
```

### 6.2 InputPrimitive 枚举

| 原语 | 说明 |
|------|------|
| TEXT | 文本输入 |
| ELEMENT | 元素输入 |
| URL | URL 输入 |
| IMAGE | 图片输入 |
| COORDINATE | 坐标输入 |

### 6.3 创建自定义技能

```python
from uiai.skills.base import Skill, InputPrimitive

class MyCustomSkill(Skill):
    """自定义技能"""
    
    name = "my_custom_skill"
    description = "自定义技能描述"
    input_primitives = [InputPrimitive.TEXT, InputPrimitive.ELEMENT]
    
    async def execute(self, context, inputs) -> dict:
        """执行技能"""
        # 获取输入
        text = inputs.get("text")
        element = inputs.get("element")
        
        # 执行逻辑
        result = await self._process(text, element, context)
        
        return {"result": result}
    
    async def _process(self, text, element, context):
        """处理逻辑"""
        # 自定义处理
        return "processed"
```

### 6.4 注册技能

```python
from uiai.skills.registry import SkillRegistry

registry = SkillRegistry()

# 注册技能
registry.register(MyCustomSkill())

# 查看技能列表
skills = registry.list()
for skill in skills:
    print(f"{skill.name}: {skill.description}")
```

---

## 七、贡献代码

### 7.1 贡献流程

1. Fork 仓库
2. 创建特性分支
3. 编写代码和测试
4. 提交 PR

### 7.2 分支命名

```
feature/xxx    # 新功能
fix/xxx        # Bug 修复
docs/xxx       # 文档更新
refactor/xxx   # 重构
```

### 7.3 PR 检查清单

- [ ] 代码遵循规范
- [ ] 添加了单元测试
- [ ] 测试通过
- [ ] 更新了文档
- [ ] PR 描述清晰

### 7.4 提交信息格式

```
<type>: <subject>

<body>

<footer>
```

**type 类型**:

| 类型 | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| style | 代码格式 |
| refactor | 重构 |
| test | 测试 |
| chore | 构建/工具 |

**示例**:

```
feat: 添加自定义 Watchdog 支持

- 新增 BaseWatchdog 抽象类
- 支持自定义 Watchdog 注册
- 添加示例代码

Closes #123
```

---

## 八、代码规范

### 8.1 Python 版本

使用 Python 3.10+ 特性：

```python
# 类型注解
from typing import Optional, List

def func(name: str, age: Optional[int] = None) -> List[str]:
    ...

# match 语句
match value:
    case "a":
        ...
    case "b":
        ...
```

### 8.2 代码风格

遵循 PEP 8：

```python
# 好的示例
class MyClass:
    def __init__(self, name: str):
        self._name = name
    
    def get_name(self) -> str:
        return self._name

# 避免
class myClass:
    def __init__(self,name):
        self.name=name
```

### 8.3 类型注解

```python
from typing import Optional, List, Dict, Any

def process_data(
    data: Dict[str, Any],
    options: Optional[List[str]] = None
) -> Dict[str, Any]:
    """处理数据"""
    ...
```

### 8.4 文档字符串

```python
def execute_task(task: str, max_steps: int = 50) -> TestResult:
    """
    执行测试任务。
    
    Args:
        task: 任务描述
        max_steps: 最大执行步数
    
    Returns:
        TestResult: 测试结果
    
    Raises:
        ValueError: 如果 task 为空
    """
    if not task:
        raise ValueError("task must be non-empty")
    ...
```

### 8.5 单元测试

```python
import pytest
from uiai import TestOrchestrator

@pytest.mark.asyncio
async def test_execute_task():
    """测试执行任务"""
    orchestrator = TestOrchestrator(config)
    result = await orchestrator.run_agent_test("登录系统")
    
    assert result.status.value in ["passed", "healed"]
    assert len(result.steps) > 0

@pytest.mark.asyncio
async def test_execute_task_with_empty_input():
    """测试空输入"""
    orchestrator = TestOrchestrator(config)
    
    with pytest.raises(ValueError):
        await orchestrator.run_agent_test("")
```

---

> **下一步**: 查看 [示例代码](./examples.md) 了解更多使用示例。