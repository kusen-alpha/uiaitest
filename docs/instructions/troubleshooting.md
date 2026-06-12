# 故障排查

本文档介绍 UIAI 的常见问题和故障排查方法。

---

## 目录

1. [常见错误](#一常见错误)
2. [调试技巧](#二调试技巧)
3. [错误码参考](#三错误码参考)
4. [日志分析](#四日志分析)
5. [性能问题](#五性能问题)
6. [常见问题 FAQ](#六常见问题-faq)

---

## 一、常见错误

### 1.1 LLM API 错误

#### 错误：`llm.api_key must be non-empty`

**原因**: 未配置 LLM API Key

**解决方案**:

```yaml
# uiai.yaml
llm:
  api_key: "your-api-key"
```

或设置环境变量：

```bash
export OPENAI_API_KEY="your-api-key"
```

#### 错误：`LLM API call failed: rate limit exceeded`

**原因**: API 调用频率超限

**解决方案**:

1. 降低并行数
2. 增加请求间隔
3. 升级 API 配额

```yaml
parallel_workers: 1  # 降低并行数
```

#### 错误：`LLM API call failed: invalid model`

**原因**: 模型名称错误或不支持

**解决方案**:

```yaml
llm:
  model: gpt-4o  # 使用正确的模型名称
```

### 1.2 定位失败

#### 错误：`Element not found: locator=...`

**原因**: 元素定位失败

**解决方案**:

1. 检查定位器是否正确
2. 添加降级策略
3. 启用自愈功能

```python
# 添加降级策略
locator = Locator.by_test_id("username")
    .with_fallback(LocatorType.CSS, "#username")
    .with_fallback(LocatorType.XPATH, "//input[@name='user']")
```

#### 错误：`Element not visible: locator=...`

**原因**: 元素存在但不可见

**解决方案**:

1. 等待元素可见
2. 检查元素是否被遮挡
3. 检查 CSS 样式

```python
test.add_step("等待元素", "wait", 
    locator=Locator.by_test_id("username"),
    timeout=5000)
```

#### 错误：`Element detached from DOM`

**原因**: 元素已从 DOM 中移除

**解决方案**:

1. 检查页面是否刷新
2. 检查元素是否被动态移除
3. 使用更稳定的定位器

### 1.3 Agent 循环

#### 错误：`Loop detected: same action repeated`

**原因**: Agent 进入循环状态

**解决方案**:

1. 检查任务描述是否清晰
2. 减少最大步数
3. 使用初始动作减少不确定性

```python
result = await orchestrator.run_agent_test(
    "登录系统",
    max_steps=20,  # 减少最大步数
    initial_actions=[
        {"action_type": "navigate", "params": {"url": "https://example.com/login"}}
    ]
)
```

#### 错误：`Agent timeout: max steps exceeded`

**原因**: 超过最大执行步数

**解决方案**:

1. 增加最大步数
2. 简化任务描述
3. 分拆为多个小任务

```python
# 分拆任务
result1 = await orchestrator.run_agent_test("登录系统")
result2 = await orchestrator.run_agent_test("查看订单列表")
```

### 1.4 浏览器错误

#### 错误：`Browser crashed`

**原因**: 浏览器崩溃

**解决方案**:

1. CrashWatchdog 会自动恢复
2. 检查系统资源
3. 降低并行数

```yaml
parallel_workers: 1  # 降低并行数
watchdog:
  crash:
    enabled: true
    max_restarts: 3
```

#### 错误：`Browser timeout: page load failed`

**原因**: 页面加载超时

**解决方案**:

1. 增加超时时间
2. 检查网络连接
3. 检查页面是否有阻塞资源

```yaml
timeout: 60000  # 增加超时时间
```

#### 错误：`Playwright browser not installed`

**原因**: 未安装 Playwright 浏览器

**解决方案**:

```bash
playwright install chromium
```

### 1.5 网络错误

#### 错误：`Network error: connection refused`

**原因**: 网络连接失败

**解决方案**:

1. 检查网络连接
2. 检查防火墙设置
3. 检查代理配置

```yaml
browser:
  proxy:
    server: "http://proxy.example.com:8080"
```

#### 错误：`Network error: timeout`

**原因**: 网络请求超时

**解决方案**:

```yaml
watchdog:
  network:
    timeout: 60000
    retry_count: 3
```

### 1.6 验证码错误

#### 错误：`Captcha detected: unknown type`

**原因**: 检测到未知类型验证码

**解决方案**:

1. 配置 TOTP 自动处理
2. 设置人工介入通知

```yaml
watchdog:
  captcha:
    enabled: true
    totp_secret: "your-totp-secret"
    notify_on_unknown: true
```

---

## 二、调试技巧

### 2.1 启用详细日志

```bash
uiai run https://example.com -v
```

### 2.2 使用有头模式

```bash
uiai run https://example.com --headed
```

观察浏览器操作过程。

### 2.3 使用慢速模式

```yaml
browser:
  slow_mo: 0.5  # 每步延迟 0.5 秒
```

### 2.4 查看 Playwright Trace

```bash
# 运行测试并录制 Trace
uiai run https://example.com

# 查看 Trace
uiai trace reports/trace.zip --open
```

### 2.5 检查缓存状态

```bash
uiai cache stats
```

### 2.6 检查知识库状态

```bash
uiai knowledge show --level experience
```

### 2.7 检查自愈记录

```bash
uiai healing --list
uiai healing --metrics
```

### 2.8 使用断点调试

```python
import asyncio
from uiai import TestOrchestrator

async def debug_test():
    config = UIAIConfig()
    config.browser.headless = False
    config.browser.slow_mo = 0.5
    
    orchestrator = TestOrchestrator(config)
    
    # 执行到断点
    result = await orchestrator.run_agent_test(
        "登录系统",
        max_steps=10
    )
    
    # 检查状态
    print(f"当前 URL: {await orchestrator.executor.get_url()}")
    print(f"执行历史: {result.steps}")
    
    # 继续执行
    result = await orchestrator.run_agent_test(
        "查看订单列表",
        initial_actions=result.steps  # 从断点继续
    )

asyncio.run(debug_test())
```

---

## 三、错误码参考

| 错误码 | 说明 | 解决方案 |
|--------|------|---------|
| E001 | LLM API Key 未配置 | 配置 llm.api_key |
| E002 | 元素定位失败 | 添加降级策略或启用自愈 |
| E003 | Agent 循环检测 | 优化任务描述，减少步数 |
| E004 | 浏览器崩溃 | 检查资源，降低并行数 |
| E005 | 网络超时 | 检查网络，增加 timeout |
| E006 | 域名安全违规 | 检查 allowed_domains |
| E007 | 验证码无法自动处理 | 配置 TOTP 或人工介入 |
| E008 | 检查点恢复失败 | 检查存储状态 |
| E009 | 知识库加载失败 | 检查知识库目录 |
| E010 | 缓存加载失败 | 检查缓存目录 |
| E011 | 配置文件解析失败 | 检查 YAML 格式 |
| E012 | Playwright 未安装 | 运行 playwright install |
| E013 | Appium 连接失败 | 检查 Appium Server |
| E014 | 权限不足 | 检查文件权限 |
| E015 | 内存不足 | 降低并行数，检查资源 |

---

## 四、日志分析

### 4.1 日志级别

| 级别 | 说明 |
|------|------|
| DEBUG | 详细调试信息 |
| INFO | 一般信息 |
| WARNING | 警告信息 |
| ERROR | 错误信息 |
| CRITICAL | 严重错误 |

### 4.2 启用日志

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 4.3 日志文件

```yaml
logging:
  level: DEBUG
  file: ./logs/uiai.log
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### 4.4 关键日志信息

**Agent 执行日志**:

```
[ExecutorAgent] Starting task: 登录系统
[ExecutorAgent] Perception mode: HYBRID
[ExecutorAgent] Step 1: navigate to https://example.com/login
[ExecutorAgent] Step 2: type text to username-input
[ExecutorAgent] Step 3: click login-button
[ExecutorAgent] Task completed: success
```

**定位失败日志**:

```
[Locator] Primary locator failed: by_test_id(username)
[Healer] L1 fallback: by_css(#username) - success
[Healer] Healing applied: selector_fallback
```

**Watchdog 日志**:

```
[PopupWatchdog] Alert detected: "提示信息"
[PopupWatchdog] Auto handled: accept
[CaptchaWatchdog] TOTP captcha detected
[CaptchaWatchdog] Auto filled: 123456
```

---

## 五、性能问题

### 5.1 执行速度慢

**原因**: LLM 调用延迟高

**解决方案**:

1. 使用缓存
2. 选择更快的模型
3. 减少感知 Token 数

```yaml
llm:
  model: gpt-3.5-turbo  # 更快的模型
  
cache:
  enabled: true
```

### 5.2 内存占用高

**原因**: 并行数过多或缓存过大

**解决方案**:

```yaml
parallel_workers: 1

cache:
  max_entries: 100
```

### 5.3 Token 消耗高

**原因**: 感知模式选择不当

**解决方案**:

```python
# 使用 A11Y_SNAPSHOT 模式（Token 效率最高）
result = await orchestrator.run_agent_test(
    "测试登录",
    perception_mode=PerceptionMode.A11Y_SNAPSHOT
)
```

### 5.4 网络延迟高

**原因**: 网络连接慢或代理配置不当

**解决方案**:

```yaml
browser:
  proxy:
    server: ""  # 移除不必要的代理
```

---

## 六、常见问题 FAQ

### Q1: 如何处理动态变化的元素？

**A**: 使用语义化定位器 + 降级策略：

```python
locator = Locator.by_role("button", name="登录")
    .with_fallback(LocatorType.TEXT, "登录")
```

### Q2: 如何处理弹窗？

**A**: PopupWatchdog 自动处理：

```yaml
watchdog:
  popup:
    enabled: true
    default_action: accept
```

### Q3: 如何处理验证码？

**A**: 配置 TOTP：

```yaml
watchdog:
  captcha:
    enabled: true
    totp_secret: "your-totp-secret"
```

### Q4: 如何提高定位成功率？

**A**: 
1. 使用语义化定位器
2. 添加降级策略
3. 启用自愈功能
4. 添加 TestID 属性

### Q5: 如何减少 Token 消耗？

**A**: 
1. 使用 A11Y_SNAPSHOT 感知模式
2. 使用缓存
3. 使用轻量模型

### Q6: 如何处理 Canvas/WebGL 页面？

**A**: 使用 VISUAL_SCREENSHOT 感知模式：

```python
result = await orchestrator.run_agent_test(
    "测试图表",
    perception_mode=PerceptionMode.VISUAL_SCREENSHOT
)
```

### Q7: 如何在 CI/CD 中使用？

**A**: 参考 [最佳实践 - CI/CD 集成](./best-practices.md#八cicd-集成)

### Q8: 如何使用国内 LLM？

**A**: 

```yaml
# 阿里云 DashScope
llm:
  provider: dashscope
  model: qwen-plus
  api_key: "${DASHSCOPE_API_KEY}"

# 火山引擎
llm:
  provider: volcengine
  model: doubao-pro
  api_key: "${VOLCENGINE_API_KEY}"
```

### Q9: 如何使用本地模型？

**A**: 

```yaml
llm:
  provider: ollama
  model: llama3
  base_url: "http://localhost:11434"
```

### Q10: 如何查看执行过程？

**A**: 
1. 使用有头模式
2. 查看 Playwright Trace
3. 启用详细日志

```bash
uiai run https://example.com --headed -v
uiai trace reports/trace.zip --open
```

---

> **下一步**: 查看 [架构设计](./architecture.md) 或 [开发者指南](./developer-guide.md)。