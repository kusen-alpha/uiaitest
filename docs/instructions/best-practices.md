# 最佳实践

本文档介绍 UIAI 的最佳实践，帮助您提升测试效率和稳定性。

---

## 目录

1. [定位器最佳实践](#一定位器最佳实践)
2. [测试用例组织](#二测试用例组织)
3. [Agent 模式最佳实践](#三agent-模式最佳实践)
4. [知识沉淀最佳实践](#四知识沉淀最佳实践)
5. [自愈配置最佳实践](#五自愈配置最佳实践)
6. [Watchdog 配置最佳实践](#六watchdog-配置最佳实践)
7. [性能优化](#七性能优化)
8. [CI/CD 集成](#八cicd-集成)

---

## 一、定位器最佳实践

### 1.1 优先使用语义化定位器

**推荐顺序**: ROLE → TEST_ID → LABEL → PLACEHOLDER → TEXT → CSS → XPATH

```python
from uiai import Locator

# 推荐：语义化定位
Locator.by_role("button", name="登录")
Locator.by_test_id("username-input")
Locator.by_label("用户名")
Locator.by_placeholder("请输入用户名")

# 避免：脆弱的 CSS/XPath
Locator.by_css("#login-form > div:nth-child(2) > input")
Locator.by_xpath("//div[@class='form']/input[1]")
```

### 1.2 添加降级策略

为每个定位器添加多级降级策略，提高定位成功率。

```python
locator = Locator.by_test_id("username")
    .with_fallback(LocatorType.CSS, "#username")
    .with_fallback(LocatorType.XPATH, "//input[@name='username']")
    .with_fallback(LocatorType.TEXT, "用户名")
```

### 1.3 使用 TestID 属性

在开发阶段，建议开发团队添加 `data-testid` 属性：

```html
<!-- HTML 示例 -->
<input data-testid="username-input" type="text" />
<button data-testid="login-button">登录</button>
```

```python
# Python 定位
Locator.by_test_id("username-input")
Locator.by_test_id("login-button")
```

### 1.4 避免使用动态 ID

```python
# 避免：动态生成的 ID
Locator.by_css("#input-12345")  # ID 每次不同

# 推荐：稳定的属性
Locator.by_test_id("username")
Locator.by_label("用户名")
```

### 1.5 使用文本定位时注意精确性

```python
# 精确匹配
Locator.by_text("登录", exact=True)

# 包含匹配
Locator.by_text("登录", exact=False)  # 匹配 "点击登录按钮"
```

---

## 二、测试用例组织

### 2.1 按功能模块组织

```
tests/
├── login/
│   ├── test_login_success.py
│   ├── test_login_failure.py
│   └── test_login_logout.py
├── cart/
│   ├── test_cart_add.py
│   ├── test_cart_remove.py
│   └── test_cart_checkout.py
├── order/
│   ├── test_order_create.py
│   ├── test_order_cancel.py
│   └── test_order_refund.py
└── payment/
    ├── test_payment_success.py
    └── test_payment_failure.py
```

### 2.2 使用 Page Object Model

创建 Page Object 封装页面操作：

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
    
    async def get_item_count(self) -> int:
        """获取商品数量"""
        return await self.count(self.cart_items)
    
    async def checkout(self):
        """结算"""
        await self.click(self.checkout_button)
```

### 2.3 使用测试数据管理

```python
# data/users.yaml
users:
  valid:
    username: "admin"
    password: "123456"
  invalid:
    username: "invalid"
    password: "wrong"

# tests/test_login.py
import yaml

def load_test_data():
    with open("data/users.yaml") as f:
        return yaml.safe_load(f)

@pytest.mark.asyncio
async def test_login_with_valid_user(orchestrator):
    data = load_test_data()
    user = data["users"]["valid"]
    
    test = TestCase(id="login_valid", name="有效用户登录")
    test.add_step("输入用户名", "type", 
        locator=Locator.by_test_id("username"), value=user["username"])
    test.add_step("输入密码", "type", 
        locator=Locator.by_test_id("password"), value=user["password"])
    
    result = await orchestrator.run_test(test)
    assert result.status.value == "passed"
```

### 2.4 使用标签分类

```python
test = TestCase(
    id="login_test",
    name="登录测试",
    tags=["登录", "核心功能", "P1"]
)

# 按标签过滤运行
# pytest -m "登录"
# pytest -m "核心功能"
# pytest -m "P1"
```

---

## 三、Agent 模式最佳实践

### 3.1 提供清晰的任务描述

```python
# 好的描述：具体、明确
result = await orchestrator.run_agent_test(
    "登录系统（用户名admin，密码123456），进入订单列表页面，验证第一个订单的状态为'已完成'"
)

# 不好的描述：模糊、不具体
result = await orchestrator.run_agent_test(
    "测试订单"
)
```

### 3.2 使用初始动作减少不确定性

```python
result = await orchestrator.run_agent_test(
    "搜索商品并添加到购物车",
    initial_actions=[
        {"action_type": "navigate", "params": {"url": "https://example.com"}},
        {"action_type": "click", "params": {"selector": "#accept-cookies"}},
        {"action_type": "click", "params": {"selector": "#close-banner"}}
    ]
)
```

### 3.3 设置合理的最大步数

```python
# 简单任务：10-20 步
result = await orchestrator.run_agent_test(
    "登录系统",
    max_steps=20
)

# 复杂任务：30-50 步
result = await orchestrator.run_agent_test(
    "完成购物流程：搜索、添加购物车、结算、支付",
    max_steps=50
)
```

### 3.4 选择合适的感知模式

```python
from uiai.core.perception import PerceptionMode

# 常规页面：A11Y_SNAPSHOT（Token 效率最高）
result = await orchestrator.run_agent_test(
    "测试登录功能",
    perception_mode=PerceptionMode.A11Y_SNAPSHOT
)

# 复杂页面：DOM_SERIALIZE
result = await orchestrator.run_agent_test(
    "测试复杂表单",
    perception_mode=PerceptionMode.DOM_SERIALIZE
)

# Canvas/WebGL 页面：VISUAL_SCREENSHOT
result = await orchestrator.run_agent_test(
    "测试图表交互",
    perception_mode=PerceptionMode.VISUAL_SCREENSHOT
)

# 默认：HYBRID（自动选择）
result = await orchestrator.run_agent_test(
    "测试购物流程",
    perception_mode=PerceptionMode.HYBRID
)
```

### 3.5 结合知识上下文

```python
# 先导入业务知识
await km.add_requirement(
    domain="ecommerce",
    title="购物车限制",
    content="购物车最多添加 99 件商品"
)

# Agent 执行时会使用知识上下文
result = await orchestrator.run_agent_test(
    "测试购物车添加商品"
)
```

---

## 四、知识沉淀最佳实践

### 4.1 预先导入业务知识

在测试开始前，导入业务需求知识和产品知识：

```python
from uiai.core.knowledge import KnowledgeManager

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
```

### 4.2 定期维护知识库

```python
# 权重衰减，清理过期知识
await km.decay_weights(decay_factor=0.95)

# 清理低权重知识
await km.cleanup_expired(min_weight=0.1)

# 查看知识统计
stats = await km.stats()
print(f"需求级知识: {stats['requirement_count']}")
print(f"产品级知识: {stats['product_count']}")
print(f"经验级知识: {stats['experience_count']}")
```

### 4.3 使用知识上下文

```python
# 为 Agent 构建知识上下文
context = await km.build_context(
    query="测试购物车功能",
    domain="ecommerce",
    max_tokens=2000
)

print(context)
# 输出：
# ## 业务知识
# - 购物车最多添加 99 件商品
# - 支持支付宝、微信支付、银行卡支付
# 
# ## 测试经验
# - 登录成功案例：用户名 admin，密码 123456
```

---

## 五、自愈配置最佳实践

### 5.1 生产环境配置

```yaml
healing:
  enabled: true
  auto_apply: false  # 需人工审核
  max_retries: 3
  screenshot_on_failure: true
  strategies:
    - selector_fallback
    - dom_neighbor_search
    - visual_ocr
    - ai_code_fix
```

### 5.2 开发环境配置

```yaml
healing:
  enabled: true
  auto_apply: true   # 自动应用（谨慎使用）
  max_retries: 5
  screenshot_on_failure: true
```

### 5.3 定期审核自愈记录

```bash
# 查看待审批记录
uiai healing --list

# 审批有效修复
uiai healing --approve heal-001

# 拒绝无效修复
uiai healing --reject heal-002

# 查看自愈指标
uiai healing --metrics
```

### 5.4 自愈策略选择

| 场景 | 推荐策略 |
|------|---------|
| UI 结构稳定 | selector_fallback |
| UI 经常变化 | dom_neighbor_search + visual_ocr |
| Canvas/WebGL | visual_ocr |
| 新功能测试 | ai_code_fix |

---

## 六、Watchdog 配置最佳实践

### 6.1 配置验证码自动处理

```python
from uiai.core.watchdog import CaptchaWatchdog
import pyotp

# 配置 TOTP 自动处理
totp = pyotp.TOTP("your-totp-secret")

captcha_watchdog = CaptchaWatchdog(
    event_bus,
    totp_secret="your-totp-secret"
)
```

### 6.2 配置域名安全

```yaml
browser:
  allowed_domains:
    - "*.example.com"
    - "api.example.com"
    - "cdn.example.com"
  prohibited_domains:
    - "*.ads.com"
    - "*.tracking.com"
```

### 6.3 配置网络重试

```yaml
watchdog:
  network:
    enabled: true
    timeout: 30000
    retry_count: 3
    retry_delay: 1000
```

### 6.4 配置崩溃恢复

```yaml
watchdog:
  crash:
    enabled: true
    max_restarts: 3
    checkpoint_interval: 5
```

---

## 七、性能优化

### 7.1 使用缓存

```python
# 检查缓存
cached_plan = await orchestrator.get_cached_plan("登录并查看订单")
if cached_plan:
    # 使用缓存计划，减少 LLM 调用
    steps = cached_plan.steps
```

### 7.2 选择合适的感知模式

| 感知模式 | Token 消耗 | 适用场景 |
|---------|-----------|---------|
| A11Y_SNAPSHOT | ~500 tokens | 常规页面，推荐默认 |
| DOM_SERIALIZE | ~2000 tokens | 复杂页面 |
| VISUAL_SCREENSHOT | ~1500 tokens + 图片 | Canvas/WebGL |
| HYBRID | 动态 | 全场景覆盖 |

### 7.3 并行执行

```yaml
parallel_workers: 4  # 根据机器配置调整
```

```python
# 并行执行测试套件
tests = [TestCase(...), TestCase(...), TestCase(...)]
result = await orchestrator.run_suite(tests, parallel=True)
```

### 7.4 减少不必要的等待

```python
# 使用智能等待
test.add_step("等待登录按钮", "wait", 
    locator=Locator.by_role("button", name="登录"), 
    timeout=5000)

# 避免：固定等待
# await asyncio.sleep(5)  # 不推荐
```

### 7.5 优化 LLM 配置

```yaml
llm:
  temperature: 0.1  # 低温度，减少随机性
  max_tokens: 2048  # 限制输出长度
  
  # 模型路由
  model: gpt-4o              # 主模型（复杂任务）
  extract_model: gpt-3.5-turbo  # 轻量模型（简单任务）
```

---

## 八、CI/CD 集成

### 8.1 GitHub Actions 配置

```yaml
# .github/workflows/test.yml
name: UIAI Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install uiai
          playwright install chromium
      
      - name: Run tests
        run: |
          uiai run https://staging.example.com --mode agent
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      
      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: test-reports
          path: reports/
```

### 8.2 Jenkins 配置

```groovy
// Jenkinsfile
pipeline {
    agent any
    
    environment {
        OPENAI_API_KEY = credentials('openai-api-key')
    }
    
    stages {
        stage('Setup') {
            steps {
                sh 'pip install uiai'
                sh 'playwright install chromium'
            }
        }
        
        stage('Test') {
            steps {
                sh 'uiai run https://staging.example.com --mode agent'
            }
        }
        
        stage('Report') {
            steps {
                publishHTML([
                    allowMissing: false,
                    alwaysLinkToLastBuild: true,
                    keepAll: true,
                    reportDir: 'reports',
                    reportFiles: 'report.html',
                    reportName: 'Test Report'
                ])
            }
        }
    }
}
```

### 8.3 pytest 集成

```python
# conftest.py
import pytest
from uiai import TestOrchestrator
from uiai.config import UIAIConfig

@pytest.fixture(scope="session")
def orchestrator():
    config = UIAIConfig()
    config.llm.api_key = os.environ.get("OPENAI_API_KEY")
    orchestrator = TestOrchestrator(config)
    yield orchestrator
    await orchestrator.stop()

# pytest.ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

### 8.4 Docker 集成

```dockerfile
# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装依赖
RUN pip install uiai playwright
RUN playwright install chromium --with-deps

# 复制测试代码
COPY tests/ ./tests/
COPY uiai.yaml ./uiai.yaml

# 运行测试
CMD ["uiai", "run", "https://example.com", "--mode", "agent"]
```

---

> **下一步**: 查看 [故障排查](./troubleshooting.md) 或 [架构设计](./architecture.md)。