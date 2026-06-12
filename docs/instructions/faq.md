# 常见问题 FAQ

本文档汇总 UIAI 的常见问题和解答。

---

## 目录

1. [安装与配置](#一安装与配置)
2. [定位器问题](#二定位器问题)
3. [Agent 模式问题](#三agent-模式问题)
4. [自愈功能问题](#四自愈功能问题)
5. [Watchdog 问题](#五watchdog-问题)
6. [LLM 问题](#六llm-问题)
7. [性能问题](#七性能问题)
8. [移动端问题](#八移动端问题)
9. [CI/CD 问题](#九cicd-问题)
10. [其他问题](#十其他问题)

---

## 一、安装与配置

### Q1: 如何安装 UIAI？

```bash
pip install uiai
playwright install chromium
```

### Q2: 如何安装 Playwright 浏览器？

```bash
# 安装 Chromium
playwright install chromium

# 安装所有浏览器
playwright install

# 安装时包含依赖
playwright install chromium --with-deps
```

### Q3: 如何配置 LLM API Key？

**方式一：配置文件**

```yaml
llm:
  api_key: "your-api-key"
```

**方式二：环境变量**

```bash
export OPENAI_API_KEY="your-api-key"
```

### Q4: 如何使用国内 LLM？

**阿里云 DashScope**:

```yaml
llm:
  provider: dashscope
  model: qwen-plus
  api_key: "${DASHSCOPE_API_KEY}"
  vl_model: "qwen-vl-plus"
```

**火山引擎**:

```yaml
llm:
  provider: volcengine
  model: doubao-pro
  api_key: "${VOLCENGINE_API_KEY}"
```

### Q5: 如何使用本地模型？

```yaml
llm:
  provider: ollama
  model: llama3
  base_url: "http://localhost:11434"
```

### Q6: 如何配置多环境？

```
config/
├── default.yaml      # 默认配置
├── dev.yaml          # 开发环境
├── test.yaml         # 测试环境
└── staging.yaml      # 预发布环境
```

```python
config = UIAIConfig.from_yaml("config/test.yaml")
```

---

## 二、定位器问题

### Q7: 如何提高定位成功率？

1. 使用语义化定位器（ROLE/TEST_ID）
2. 添加降级策略
3. 启用自愈功能
4. 添加 TestID 属性

```python
locator = Locator.by_test_id("username")
    .with_fallback(LocatorType.CSS, "#username")
    .with_fallback(LocatorType.XPATH, "//input[@name='username']")
```

### Q8: 如何处理动态变化的元素？

使用语义化定位器 + 降级策略：

```python
# 避免：动态 ID
Locator.by_css("#input-12345")

# 推荐：语义定位
Locator.by_role("button", name="登录")
Locator.by_label("用户名")
```

### Q9: 如何处理 Canvas/WebGL 元素？

使用 VISUAL_SCREENSHOT 感知模式：

```python
result = await orchestrator.run_agent_test(
    "测试图表",
    perception_mode=PerceptionMode.VISUAL_SCREENSHOT
)
```

### Q10: 如何添加 TestID 属性？

在开发阶段，建议开发团队添加 `data-testid` 属性：

```html
<input data-testid="username-input" type="text" />
<button data-testid="login-button">登录</button>
```

---

## 三、Agent 模式问题

### Q11: Agent 进入循环怎么办？

1. 检查任务描述是否清晰
2. 减少最大步数
3. 使用初始动作

```python
result = await orchestrator.run_agent_test(
    "登录系统",
    max_steps=20,
    initial_actions=[
        {"action_type": "navigate", "params": {"url": "https://example.com/login"}}
    ]
)
```

### Q12: Agent 执行超时怎么办？

1. 增加最大步数
2. 简化任务描述
3. 分拆为多个小任务

```python
# 分拆任务
result1 = await orchestrator.run_agent_test("登录系统")
result2 = await orchestrator.run_agent_test("查看订单列表")
```

### Q13: 如何提供更好的任务描述？

```python
# 好的描述：具体、明确
result = await orchestrator.run_agent_test(
    "登录系统（用户名admin，密码123456），进入订单列表页面，验证第一个订单的状态为'已完成'"
)

# 不好的描述：模糊、不具体
result = await orchestrator.run_agent_test("测试订单")
```

### Q14: 如何选择感知模式？

| 感知模式 | Token 消耗 | 适用场景 |
|---------|-----------|---------|
| A11Y_SNAPSHOT | ~500 tokens | 常规页面，推荐默认 |
| DOM_SERIALIZE | ~2000 tokens | 复杂页面 |
| VISUAL_SCREENSHOT | ~1500 tokens + 图片 | Canvas/WebGL |
| HYBRID | 动态 | 全场景覆盖 |

---

## 四、自愈功能问题

### Q15: 如何启用自愈功能？

```yaml
healing:
  enabled: true
  auto_apply: false  # 需人工审核
  max_retries: 3
```

### Q16: 如何审核自愈记录？

```bash
# 查看待审批记录
uiai healing --list

# 审批修复
uiai healing --approve heal-001

# 拒绝修复
uiai healing --reject heal-002
```

### Q17: 自愈成功率低怎么办？

1. 添加更多降级策略
2. 使用更稳定的定位器
3. 配置视觉定位兜底

```yaml
healing:
  strategies:
    - selector_fallback
    - dom_neighbor_search
    - visual_ocr
    - ai_code_fix
```

### Q18: 生产环境是否应该启用自愈？

建议启用，但设置 `auto_apply: false`：

```yaml
healing:
  enabled: true
  auto_apply: false  # 需人工审核
```

---

## 五、Watchdog 问题

### Q19: 如何处理弹窗？

PopupWatchdog 自动处理：

```yaml
watchdog:
  popup:
    enabled: true
    default_action: accept
```

### Q20: 如何处理验证码？

配置 TOTP：

```yaml
watchdog:
  captcha:
    enabled: true
    totp_secret: "your-totp-secret"
```

### Q21: 如何处理浏览器崩溃？

CrashWatchdog 自动恢复：

```yaml
watchdog:
  crash:
    enabled: true
    max_restarts: 3
```

### Q22: 如何配置域名安全？

```yaml
browser:
  allowed_domains:
    - "*.example.com"
  prohibited_domains:
    - "*.ads.com"
```

---

## 六、LLM 问题

### Q23: LLM API 调用失败怎么办？

1. 检查 API Key 是否正确
2. 检查网络连接
3. 检查 API 配额
4. 使用备用模型

```yaml
llm:
  model: gpt-4o
  fallback_model: gpt-3.5-turbo
```

### Q24: 如何减少 Token 消耗？

1. 使用 A11Y_SNAPSHOT 感知模式
2. 使用缓存
3. 使用轻量模型

```yaml
llm:
  extract_model: gpt-3.5-turbo

cache:
  enabled: true
```

### Q25: 如何配置多模型路由？

```yaml
llm:
  model: gpt-4o              # 主模型（PLAN/HEAL）
  vl_model: gpt-4-vision-preview  # 视觉模型（LOCATE/ASSERT）
  extract_model: gpt-3.5-turbo    # 轻量模型（EXTRACT）
```

---

## 七、性能问题

### Q26: 如何提高执行速度？

1. 使用缓存
2. 使用更快的模型
3. 减少感知 Token 数
4. 并行执行

```yaml
cache:
  enabled: true

parallel_workers: 4
```

### Q27: 如何减少内存占用？

```yaml
parallel_workers: 1

cache:
  max_entries: 100
```

### Q28: 如何优化网络延迟？

```yaml
browser:
  proxy:
    server: ""  # 移除不必要的代理
```

---

## 八、移动端问题

### Q29: 如何配置 Android 测试？

```yaml
appium:
  server_url: "http://127.0.0.1:4723"
  platform_name: Android
  automation_name: UiAutomator2
  device_name: "emulator-5554"
  app_package: "com.example.app"
  app_activity: "com.example.app.MainActivity"
```

### Q30: 如何配置 iOS 测试？

```yaml
appium:
  server_url: "http://127.0.0.1:4723"
  platform_name: iOS
  automation_name: XCUITest
  device_name: "iPhone 14"
  app: "/path/to/app.app"
```

### Q31: Appium 连接失败怎么办？

1. 检查 Appium Server 是否启动
2. 检查设备连接状态
3. 检查配置是否正确

```bash
# 启动 Appium Server
appium

# 检查设备连接
adb devices
```

---

## 九、CI/CD 问题

### Q32: 如何在 GitHub Actions 中使用？

```yaml
# .github/workflows/test.yml
name: UIAI Tests

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install uiai
      - run: playwright install chromium
      - run: uiai run https://staging.example.com --mode agent
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### Q33: 如何在 Jenkins 中使用？

```groovy
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
    }
}
```

### Q34: 如何在 Docker 中使用？

```dockerfile
FROM python:3.10-slim

WORKDIR /app

RUN pip install uiai playwright
RUN playwright install chromium --with-deps

COPY tests/ ./tests/
COPY uiai.yaml ./uiai.yaml

CMD ["uiai", "run", "https://example.com", "--mode", "agent"]
```

---

## 十、其他问题

### Q35: 如何查看执行过程？

1. 使用有头模式
2. 查看 Playwright Trace
3. 启用详细日志

```bash
uiai run https://example.com --headed -v
uiai trace reports/trace.zip --open
```

### Q36: 如何录制测试代码？

```bash
uiai run https://example.com --mode agent --record
```

### Q37: 如何生成测试计划？

```bash
uiai plan "测试购物车功能" --url https://example.com
```

### Q38: 如何进行探索性测试？

```bash
uiai explore https://example.com --max-pages 20 --max-depth 3
```

### Q39: 如何查看框架信息？

```bash
uiai info
```

### Q40: 如何获取帮助？

- **GitHub**: https://github.com/uiai-framework/uiai
- **问题反馈**: https://github.com/uiai-framework/uiai/issues
- **文档**: https://uiai-framework.github.io/docs

---

> **UIAI** — 让 AI 帮你写测试、跑测试、修测试。