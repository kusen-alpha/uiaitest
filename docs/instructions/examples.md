# 示例代码

本文档提供 UIAI 的完整示例代码，涵盖各种使用场景。

---

## 目录

1. [基础示例](#一基础示例)
2. [R1 脚本模式示例](#二r1-脚本模式示例)
3. [R2 Agent 模式示例](#三r2-agent-模式示例)
4. [Page Object 模式示例](#四page-object-模式示例)
5. [pytest 集成示例](#五pytest-集成示例)
6. [移动端测试示例](#六移动端测试示例)
7. [数据驱动测试示例](#七数据驱动测试示例)
8. [自愈功能示例](#八自愈功能示例)
9. [知识沉淀示例](#九知识沉淀示例)
10. [Watchdog 示例](#十watchdog-示例)

---

## 一、基础示例

### 1.1 最简示例

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig

async def main():
    # 创建配置
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    
    # 创建编排器
    orchestrator = TestOrchestrator(config)
    
    # R2 Agent 模式：自然语言执行
    result = await orchestrator.run_agent_test(
        "打开百度搜索，输入'UIAI自动化测试'，点击搜索按钮"
    )
    
    print(f"测试结果: {result.status.value}")

asyncio.run(main())
```

### 1.2 CLI 快速使用

```bash
# R2 Agent 模式
uiai run https://example.com --mode agent

# R1 脚本模式
uiai run https://example.com --mode script

# 有头模式
uiai run https://example.com --headed
```

---

## 二、R1 脚本模式示例

### 2.1 登录测试

```python
import asyncio
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig
from uiai.core.test_case import Priority

async def test_login():
    # 创建配置
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    config.browser.headless = True
    
    # 创建编排器
    orchestrator = TestOrchestrator(config)
    
    # 定义测试用例
    test = TestCase(
        id="login_test",
        name="用户登录测试",
        priority=Priority.HIGH,
        tags=["登录", "核心功能"]
    )
    
    # 添加测试步骤（链式调用）
    test.add_step("导航到登录页", "navigate", value="https://example.com/login")
    test.add_step("输入用户名", "type", 
        locator=Locator.by_test_id("username"), value="admin")
    test.add_step("输入密码", "type", 
        locator=Locator.by_test_id("password"), value="123456")
    test.add_step("点击登录按钮", "click", 
        locator=Locator.by_role("button", name="登录"))
    test.add_step("验证跳转到首页", "assert_url", value="https://example.com/home")
    
    # 执行测试
    result = await orchestrator.run_test(test)
    
    # 输出结果
    print(f"测试结果: {result.status.value}")
    print(f"执行步数: {len(result.steps)}")
    print(f"总耗时: {result.duration_ms}ms")
    
    if result.error:
        print(f"错误信息: {result.error}")

asyncio.run(test_login())
```

### 2.2 购物流程测试

```python
import asyncio
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig

async def test_cart_checkout():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    test = TestCase(
        id="cart_checkout",
        name="购物车结算测试",
        tags=["购物车", "结算"]
    )
    
    test.add_step("导航到商品页", "navigate", value="https://example.com/product/1")
    test.add_step("点击加入购物车", "click", 
        locator=Locator.by_role("button", name="加入购物车"))
    test.add_step("导航到购物车", "navigate", value="https://example.com/cart")
    test.add_step("验证商品数量", "assert_count", 
        locator=Locator.by_test_id("cart-item"), value=1)
    test.add_step("点击结算", "click", 
        locator=Locator.by_role("button", name="结算"))
    test.add_step("验证跳转到结算页", "assert_url_contains", value="checkout")
    
    result = await orchestrator.run_test(test)
    print(f"测试结果: {result.status.value}")

asyncio.run(test_cart_checkout())
```

### 2.3 使用降级策略

```python
import asyncio
from uiai import TestOrchestrator, TestCase, Locator, LocatorType
from uiai.config import UIAIConfig

async def test_with_fallback():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    # 定义多级降级定位器
    username_locator = Locator.by_test_id("username")
        .with_fallback(LocatorType.CSS, "#username")
        .with_fallback(LocatorType.XPATH, "//input[@name='username']")
        .with_fallback(LocatorType.TEXT, "用户名")
    
    test = TestCase(id="login", name="登录测试")
    test.add_step("输入用户名", "type", locator=username_locator, value="admin")
    
    result = await orchestrator.run_test(test)
    print(f"测试结果: {result.status.value}")

asyncio.run(test_with_fallback())
```

---

## 三、R2 Agent 模式示例

### 3.1 自然语言驱动测试

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig
from uiai.core.perception import PerceptionMode

async def test_agent_mode():
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    config.llm.model = "gpt-4o"
    
    orchestrator = TestOrchestrator(config)
    
    # R2 Agent 模式：自然语言执行
    result = await orchestrator.run_agent_test(
        task="登录系统（用户名admin，密码123456），进入订单列表页面，验证第一个订单的状态为'已完成'",
        perception_mode=PerceptionMode.HYBRID,
        max_steps=30
    )
    
    # 输出结果
    print(f"测试结果: {result.status.value}")
    print(f"执行步数: {len(result.steps)}")
    print(f"总耗时: {result.duration_ms}ms")
    
    # 查看执行步骤
    for i, step in enumerate(result.steps, 1):
        print(f"步骤 {i}: {step.action} - {step.status.value}")

asyncio.run(test_agent_mode())
```

### 3.2 使用初始动作

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig

async def test_with_initial_actions():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    # 添加确定性预步骤
    result = await orchestrator.run_agent_test(
        task="搜索商品并添加到购物车",
        initial_actions=[
            {"action_type": "navigate", "params": {"url": "https://example.com"}},
            {"action_type": "click", "params": {"selector": "#accept-cookies"}},
            {"action_type": "click", "params": {"selector": "#close-banner"}}
        ],
        max_steps=20
    )
    
    print(f"测试结果: {result.status.value}")

asyncio.run(test_with_initial_actions())
```

### 3.3 选择感知模式

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig
from uiai.core.perception import PerceptionMode

async def test_perception_modes():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    # A11Y_SNAPSHOT 模式（Token 效率最高）
    result1 = await orchestrator.run_agent_test(
        "测试登录功能",
        perception_mode=PerceptionMode.A11Y_SNAPSHOT
    )
    
    # DOM_SERIALIZE 模式（信息完整）
    result2 = await orchestrator.run_agent_test(
        "测试复杂表单",
        perception_mode=PerceptionMode.DOM_SERIALIZE
    )
    
    # VISUAL_SCREENSHOT 模式（Canvas/WebGL）
    result3 = await orchestrator.run_agent_test(
        "测试图表交互",
        perception_mode=PerceptionMode.VISUAL_SCREENSHOT
    )
    
    # HYBRID 模式（自动选择）
    result4 = await orchestrator.run_agent_test(
        "测试购物流程",
        perception_mode=PerceptionMode.HYBRID
    )

asyncio.run(test_perception_modes())
```

---

## 四、Page Object 模式示例

### 4.1 定义 Page Object

```python
from uiai.core.page_object import BasePage
from uiai import Locator

class LoginPage(BasePage):
    """登录页面"""
    
    username_input = Locator.by_test_id("username")
    password_input = Locator.by_test_id("password")
    login_button = Locator.by_role("button", name="登录")
    error_message = Locator.by_test_id("error-message")
    
    async def login(self, username: str, password: str):
        """执行登录"""
        await self.fill(self.username_input, username)
        await self.fill(self.password_input, password)
        await self.click(self.login_button)
    
    async def get_error_message(self) -> str:
        """获取错误消息"""
        return await self.get_text(self.error_message)
    
    async def is_login_success(self) -> bool:
        """判断登录是否成功"""
        return await self.get_url().endswith("/home")


class CartPage(BasePage):
    """购物车页面"""
    
    cart_items = Locator.by_test_id("cart-item")
    checkout_button = Locator.by_role("button", name="结算")
    total_price = Locator.by_test_id("total-price")
    
    async def get_item_count(self) -> int:
        """获取商品数量"""
        return await self.count(self.cart_items)
    
    async def get_total_price(self) -> str:
        """获取总价"""
        return await self.get_text(self.total_price)
    
    async def checkout(self):
        """结算"""
        await self.click(self.checkout_button)
```

### 4.2 使用 Page Object

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig

async def test_with_page_object():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    # 启动执行器
    executor = await orchestrator.create_executor()
    
    # 创建 Page Object
    login_page = LoginPage(executor)
    
    # 导航到登录页
    await executor.navigate("https://example.com/login")
    
    # 使用 Page Object 方法
    await login_page.login("admin", "123456")
    
    # 验证登录成功
    assert await login_page.is_login_success()
    
    # 停止执行器
    await executor.stop()

asyncio.run(test_with_page_object())
```

---

## 五、pytest 集成示例

### 5.1 pytest 配置

```python
# conftest.py
import pytest
import os
from uiai import TestOrchestrator
from uiai.config import UIAIConfig

@pytest.fixture(scope="session")
def config():
    """配置 fixture"""
    config = UIAIConfig()
    config.llm.api_key = os.environ.get("OPENAI_API_KEY")
    return config

@pytest.fixture(scope="session")
async def orchestrator(config):
    """编排器 fixture"""
    orchestrator = TestOrchestrator(config)
    yield orchestrator
    await orchestrator.stop()
```

### 5.2 pytest 测试用例

```python
# tests/test_login.py
import pytest
from uiai import TestCase, Locator

@pytest.mark.asyncio
async def test_login_success(orchestrator):
    """测试登录成功"""
    test = TestCase(id="login_success", name="登录成功测试")
    test.add_step("导航", "navigate", value="https://example.com/login")
    test.add_step("输入用户名", "type", 
        locator=Locator.by_test_id("username"), value="admin")
    test.add_step("输入密码", "type", 
        locator=Locator.by_test_id("password"), value="123456")
    test.add_step("点击登录", "click", 
        locator=Locator.by_role("button", name="登录"))
    test.add_step("验证跳转", "assert_url", value="https://example.com/home")
    
    result = await orchestrator.run_test(test)
    assert result.status.value == "passed"

@pytest.mark.asyncio
async def test_login_failure(orchestrator):
    """测试登录失败"""
    test = TestCase(id="login_failure", name="登录失败测试")
    test.add_step("导航", "navigate", value="https://example.com/login")
    test.add_step("输入错误密码", "type", 
        locator=Locator.by_test_id("password"), value="wrong")
    test.add_step("点击登录", "click", 
        locator=Locator.by_role("button", name="登录"))
    test.add_step("验证错误提示", "assert_visible", 
        locator=Locator.by_test_id("error-message"))
    
    result = await orchestrator.run_test(test)
    assert result.status.value == "passed"

@pytest.mark.asyncio
async def test_search_agent(orchestrator):
    """测试搜索功能（Agent 模式）"""
    result = await orchestrator.run_agent_test(
        "在搜索框输入'测试'并搜索，验证有结果返回"
    )
    assert result.status.value in ["passed", "healed"]
```

### 5.3 运行 pytest

```bash
# 安装 pytest-asyncio
pip install pytest-asyncio

# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_login.py -v

# 按标签过滤
pytest tests/ -m "登录"
```

---

## 六、移动端测试示例

### 6.1 Android 测试

```python
import asyncio
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig, AppiumConfig
from uiai.core.platform import Platform

async def test_android_app():
    # 创建配置
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    
    # Appium 配置
    config.appium = AppiumConfig(
        server_url="http://127.0.0.1:4723",
        platform_name="Android",
        automation_name="UiAutomator2",
        device_name="emulator-5554",
        app_package="com.example.app",
        app_activity="com.example.app.MainActivity"
    )
    
    # 创建编排器
    orchestrator = TestOrchestrator(config)
    
    # 定义测试用例
    test = TestCase(
        id="android_login",
        name="Android 登录测试",
        platform="android"
    )
    
    test.add_step("输入用户名", "type", 
        locator=Locator.by_accessibility_id("username"), value="admin")
    test.add_step("输入密码", "type", 
        locator=Locator.by_accessibility_id("password"), value="123456")
    test.add_step("点击登录", "click", 
        locator=Locator.by_accessibility_id("login-button"))
    
    # 执行测试
    result = await orchestrator.run_test(test, platform=Platform.ANDROID)
    print(f"测试结果: {result.status.value}")

asyncio.run(test_android_app())
```

### 6.2 iOS 测试

```python
import asyncio
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig, AppiumConfig
from uiai.core.platform import Platform

async def test_ios_app():
    config = UIAIConfig()
    
    # Appium 配置
    config.appium = AppiumConfig(
        server_url="http://127.0.0.1:4723",
        platform_name="iOS",
        automation_name="XCUITest",
        device_name="iPhone 14",
        app="/path/to/app.app"
    )
    
    orchestrator = TestOrchestrator(config)
    
    test = TestCase(
        id="ios_login",
        name="iOS 登录测试",
        platform="ios"
    )
    
    test.add_step("输入用户名", "type", 
        locator=Locator.by_accessibility_id("username"), value="admin")
    test.add_step("点击登录", "click", 
        locator=Locator.by_accessibility_id("login-button"))
    
    result = await orchestrator.run_test(test, platform=Platform.IOS)
    print(f"测试结果: {result.status.value}")

asyncio.run(test_ios_app())
```

---

## 七、数据驱动测试示例

### 7.1 使用 YAML 数据

```yaml
# data/users.yaml
users:
  valid:
    - username: "admin"
      password: "123456"
    - username: "user1"
      password: "password1"
  invalid:
    - username: "invalid"
      password: "wrong"
    - username: ""
      password: ""
```

```python
# tests/test_data_driven.py
import asyncio
import yaml
import pytest
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig

def load_users():
    with open("data/users.yaml") as f:
        return yaml.safe_load(f)["users"]

@pytest.mark.asyncio
@pytest.mark.parametrize("user", load_users()["valid"])
async def test_login_valid_users(orchestrator, user):
    """测试有效用户登录"""
    test = TestCase(id="login_valid", name="有效用户登录")
    test.add_step("导航", "navigate", value="https://example.com/login")
    test.add_step("输入用户名", "type", 
        locator=Locator.by_test_id("username"), value=user["username"])
    test.add_step("输入密码", "type", 
        locator=Locator.by_test_id("password"), value=user["password"])
    test.add_step("点击登录", "click", 
        locator=Locator.by_role("button", name="登录"))
    
    result = await orchestrator.run_test(test)
    assert result.status.value == "passed"

@pytest.mark.asyncio
@pytest.mark.parametrize("user", load_users()["invalid"])
async def test_login_invalid_users(orchestrator, user):
    """测试无效用户登录"""
    test = TestCase(id="login_invalid", name="无效用户登录")
    test.add_step("导航", "navigate", value="https://example.com/login")
    test.add_step("输入用户名", "type", 
        locator=Locator.by_test_id("username"), value=user["username"])
    test.add_step("输入密码", "type", 
        locator=Locator.by_test_id("password"), value=user["password"])
    test.add_step("点击登录", "click", 
        locator=Locator.by_role("button", name="登录"))
    test.add_step("验证错误提示", "assert_visible", 
        locator=Locator.by_test_id("error-message"))
    
    result = await orchestrator.run_test(test)
    assert result.status.value == "passed"
```

---

## 八、自愈功能示例

### 8.1 启用自愈

```python
import asyncio
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig

async def test_with_healing():
    config = UIAIConfig()
    config.healing.enabled = True
    config.healing.auto_apply = False  # 需人工审核
    config.healing.max_retries = 3
    
    orchestrator = TestOrchestrator(config)
    
    test = TestCase(id="healing_test", name="自愈测试")
    test.add_step("点击按钮", "click", 
        locator=Locator.by_test_id("old-button-id"))  # 可能失效的定位器
    
    result = await orchestrator.run_test(test)
    
    # 查看自愈记录
    if result.healing_records:
        for record in result.healing_records:
            print(f"步骤: {record.step_name}")
            print(f"原始定位: {record.original_locator}")
            print(f"修复策略: {record.strategy}")
            print(f"修复后定位: {record.healed_locator}")
            print(f"是否成功: {record.success}")

asyncio.run(test_with_healing())
```

### 8.2 审核自愈记录

```bash
# 查看待审批记录
uiai healing --list

# 审批修复
uiai healing --approve heal-001

# 拒绝修复
uiai healing --reject heal-002
```

---

## 九、知识沉淀示例

### 9.1 导入业务知识

```python
import asyncio
from uiai.core.knowledge import KnowledgeManager

async def import_knowledge():
    km = KnowledgeManager()
    
    # 导入需求级知识
    await km.add_requirement(
        domain="ecommerce",
        title="购物车数量限制",
        content="购物车最多添加 99 件商品，超过限制时显示提示信息",
        tags=["购物车", "限制"]
    )
    
    await km.add_requirement(
        domain="ecommerce",
        title="支付方式",
        content="支持支付宝、微信支付、银行卡支付三种方式",
        tags=["支付"]
    )
    
    # 导入产品级知识
    await km.add_product(
        domain="ecommerce",
        title="商品搜索规则",
        content="搜索支持关键词、分类、价格区间筛选，搜索结果按相关性排序"
    )
    
    await km.add_product(
        domain="ecommerce",
        title="登录页面布局",
        content="登录页面包含用户名输入框、密码输入框、登录按钮，布局为垂直居中"
    )
    
    print("知识导入完成")

asyncio.run(import_knowledge())
```

### 9.2 使用知识上下文

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig
from uiai.core.knowledge import KnowledgeManager

async def test_with_knowledge():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    # 获取知识管理器
    km = orchestrator.knowledge_manager
    
    # 构建知识上下文
    context = await km.build_context(
        query="测试购物车功能",
        domain="ecommerce",
        max_tokens=2000
    )
    
    print("知识上下文:")
    print(context)
    
    # 执行测试（Agent 会使用知识上下文）
    result = await orchestrator.run_agent_test(
        "测试购物车添加商品功能"
    )
    
    print(f"测试结果: {result.status.value}")

asyncio.run(test_with_knowledge())
```

---

## 十、Watchdog 示例

### 10.1 配置弹窗守卫

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig
from uiai.core.watchdog import WatchdogManager, PopupWatchdog
from uiai.core.eventbus import EventBus

async def test_with_popup_watchdog():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    # 创建 EventBus
    event_bus = EventBus()
    
    # 创建 Watchdog Manager
    manager = WatchdogManager(event_bus)
    
    # 注册弹窗守卫
    popup_watchdog = PopupWatchdog(event_bus)
    popup_watchdog.default_action = "accept"  # 自动点击确定
    manager.register(popup_watchdog)
    
    # 启动 Watchdog
    await manager.start_all()
    
    # 执行测试
    result = await orchestrator.run_agent_test("测试有弹窗的页面")
    
    # 停止 Watchdog
    await manager.stop_all()
    
    print(f"测试结果: {result.status.value}")

asyncio.run(test_with_popup_watchdog())
```

### 10.2 配置验证码守卫

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig
from uiai.core.watchdog import WatchdogManager, CaptchaWatchdog
from uiai.core.eventbus import EventBus

async def test_with_captcha_watchdog():
    config = UIAIConfig()
    orchestrator = TestOrchestrator(config)
    
    event_bus = EventBus()
    manager = WatchdogManager(event_bus)
    
    # 注册验证码守卫（TOTP）
    captcha_watchdog = CaptchaWatchdog(
        event_bus,
        totp_secret="your-totp-secret"  # TOTP 密钥
    )
    manager.register(captcha_watchdog)
    
    await manager.start_all()
    
    result = await orchestrator.run_agent_test("测试有验证码的页面")
    
    await manager.stop_all()
    
    print(f"测试结果: {result.status.value}")

asyncio.run(test_with_captcha_watchdog())
```

---

> **下一步**: 查看 [常见问题](./faq.md) 或 [故障排查](./troubleshooting.md)。