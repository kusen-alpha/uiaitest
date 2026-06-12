# 快速开始

本文档将帮助您在 10 分钟内完成 UIAI 的安装和第一个测试用例。

---

## 目录

1. [环境要求](#一环境要求)
2. [安装](#二安装)
3. [配置](#三配置)
4. [第一个测试用例](#四第一个测试用例)
5. [CLI 快速使用](#五cli-快速使用)
6. [下一步](#六下一步)

---

## 一、环境要求

### 系统要求

| 系统 | 版本要求 |
|------|---------|
| Windows | Windows 10+ |
| macOS | macOS 10.15+ |
| Linux | Ubuntu 18.04+ / CentOS 7+ |

### 软件要求

| 软件 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.10+ | 核心运行环境 |
| Node.js | 18+ | Playwright 依赖 |
| pip | 21.0+ | Python 包管理器 |

### LLM API 要求

UIAI 需要大语言模型 API 支持，推荐以下任一：

| 提供商 | 推荐模型 | 说明 |
|--------|---------|------|
| OpenAI | GPT-4o | 推荐，效果最佳 |
| 阿里云 DashScope | Qwen-Plus | 国内推荐 |
| 火山引擎 | Doubao-Pro | 国内推荐 |
| Ollama | Llama3 | 本地部署 |

---

## 二、安装

### 2.1 安装 UIAI

```bash
# 使用 pip 安装
pip install uiai

# 或使用 poetry
poetry add uiai
```

### 2.2 安装 Playwright 浏览器

```bash
# 安装 Playwright
pip install playwright

# 安装浏览器（Chromium）
playwright install chromium

# 安装所有浏览器
playwright install
```

### 2.3 安装可选依赖

```bash
# 安装 Appium 支持（移动端测试）
pip install Appium-Python-Client

# 安装 TOTP 支持（验证码自动处理）
pip install pyotp

# 安装 OpenAI SDK
pip install openai

# 安装阿里云 DashScope SDK
pip install dashscope
```

### 2.4 验证安装

```bash
# 查看版本信息
uiai info

# 预期输出
UIAI Framework v1.0.0
Python: 3.10.x
Playwright: 1.40.x
```

---

## 三、配置

### 3.1 配置文件

创建 `uiai.yaml` 配置文件：

```yaml
# 浏览器配置
browser:
  browser_type: chromium
  headless: true
  viewport:
    width: 1280
    height: 720
  record_trace: true

# LLM 配置
llm:
  provider: openai
  model: gpt-4o
  api_key: ""  # 或设置环境变量 OPENAI_API_KEY
  vl_model: "gpt-4-vision-preview"  # 视觉语言模型

# 自愈配置
healing:
  enabled: true
  auto_apply: false  # 修复需人工审核
  max_retries: 3

# 报告配置
report:
  output_dir: ./reports
  format: html
  include_screenshots: true

# 全局配置
base_url: https://example.com
timeout: 30000
env: test
```

### 3.2 环境变量

推荐使用环境变量管理敏感信息：

```bash
# OpenAI
export OPENAI_API_KEY="sk-xxx"

# 阿里云 DashScope
export DASHSCOPE_API_KEY="sk-xxx"

# 火山引擎
export VOLCENGINE_API_KEY="xxx"

# UIAI 配置路径
export UIAI_CONFIG_PATH="/path/to/uiai.yaml"

# 运行环境
export UIAI_ENV="test"
```

### 3.3 多环境配置

支持按环境加载不同配置：

```
config/
├── default.yaml      # 默认配置
├── dev.yaml          # 开发环境
├── test.yaml         # 测试环境
├── staging.yaml      # 预发布环境
└── prod.yaml         # 生产环境
```

加载特定环境配置：

```python
from uiai.config import UIAIConfig

# 加载测试环境配置
config = UIAIConfig.from_yaml("config/test.yaml")
```

---

## 四、第一个测试用例

### 4.1 R1 脚本模式（确定性脚本）

创建 `test_login.py`：

```python
import asyncio
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig
from uiai.core.test_case import Priority

async def main():
    # 创建配置
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    
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
    test.add_step("输入用户名", "type", locator=Locator.by_test_id("username"), value="admin")
    test.add_step("输入密码", "type", locator=Locator.by_test_id("password"), value="123456")
    test.add_step("点击登录按钮", "click", locator=Locator.by_role("button", name="登录"))
    test.add_step("验证跳转到首页", "assert_url", value="https://example.com/home")
    
    # 执行测试
    result = await orchestrator.run_test(test)
    
    # 输出结果
    print(f"测试结果: {result.status.value}")
    print(f"执行步数: {len(result.steps)}")
    print(f"总耗时: {result.duration_ms}ms")
    
    if result.error:
        print(f"错误信息: {result.error}")

asyncio.run(main())
```

运行测试：

```bash
python test_login.py
```

### 4.2 R2 Agent 模式（自然语言驱动）

创建 `test_agent.py`：

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig
from uiai.core.perception import PerceptionMode

async def main():
    # 创建配置
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    config.llm.model = "gpt-4o"
    
    # 创建编排器
    orchestrator = TestOrchestrator(config)
    
    # R2 Agent 模式：自然语言执行
    result = await orchestrator.run_agent_test(
        task="打开百度搜索，输入'UIAI自动化测试'，点击搜索按钮，验证结果页包含相关内容",
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

asyncio.run(main())
```

运行测试：

```bash
python test_agent.py
```

### 4.3 pytest 集成

创建 `tests/test_example.py`：

```python
import pytest
from uiai import TestOrchestrator, TestCase, Locator
from uiai.config import UIAIConfig

@pytest.fixture
def orchestrator():
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    return TestOrchestrator(config)

@pytest.mark.asyncio
async def test_login(orchestrator):
    """测试用户登录"""
    test = TestCase(id="login", name="登录测试")
    test.add_step("导航", "navigate", value="https://example.com/login")
    test.add_step("输入用户名", "type", locator=Locator.by_test_id("username"), value="admin")
    test.add_step("输入密码", "type", locator=Locator.by_test_id("password"), value="123456")
    test.add_step("点击登录", "click", locator=Locator.by_role("button", name="登录"))
    
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

运行测试：

```bash
# 安装 pytest-asyncio
pip install pytest-asyncio

# 运行测试
pytest tests/ -v
```

---

## 五、CLI 快速使用

### 5.1 初始化项目

```bash
# 创建新项目
uiai init my-test-project --template advanced

# 进入项目目录
cd my-test-project

# 项目结构
# my-test-project/
# ├── config/
# │   ├── default.yaml
# │   └── environments.yaml
# ├── tests/
# ├── pages/
# ├── data/
# ├── reports/
# └── uiai.yaml
```

### 5.2 运行测试

```bash
# R1 脚本模式
uiai run https://example.com --mode script

# R2 Agent 模式
uiai run https://example.com --mode agent

# 有头模式（调试用）
uiai run https://example.com --headed

# 录制为代码
uiai run https://example.com --mode agent --record
```

### 5.3 生成测试计划

```bash
# AI 生成测试计划
uiai plan "测试购物车添加商品、修改数量、删除商品功能" --url https://example.com

# 输出到指定目录
uiai plan "测试用户注册流程" --url https://example.com --output ./plans
```

### 5.4 AI 探索性测试

```bash
# 探索性测试
uiai explore https://example.com

# 限制探索范围
uiai explore https://example.com --max-pages 20 --max-depth 3
```

### 5.5 查看框架信息

```bash
uiai info
```

---

## 六、下一步

恭喜！您已经完成了 UIAI 的快速入门。接下来建议：

1. **深入理解核心概念**
   - 阅读 [核心概念](./core-concepts.md) 了解六 Agent 协作、感知模式、Watchdog 等

2. **学习更多示例**
   - 查看 [示例代码](./examples.md) 了解各种使用场景

3. **配置优化**
   - 阅读 [配置详解](./configuration.md) 了解完整配置选项

4. **API 参考**
   - 查看 [API 参考](./api-reference.md) 了解所有 API

5. **最佳实践**
   - 阅读 [最佳实践](./best-practices.md) 提升测试效率

---

## 常见问题

### Q: 安装 Playwright 浏览器失败？

```bash
# 尝试使用管理员权限
sudo playwright install chromium

# 或指定浏览器路径
playwright install chromium --with-deps
```

### Q: LLM API 调用失败？

1. 检查 API Key 是否正确
2. 检查网络连接
3. 检查 API 配额

```python
# 测试 API 连接
import openai
openai.api_key = "your-api-key"
response = openai.ChatCompletion.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response)
```

### Q: 如何使用国内 LLM？

```yaml
# 阿里云 DashScope
llm:
  provider: dashscope
  model: qwen-plus
  api_key: "your-dashscope-api-key"
  vl_model: "qwen-vl-plus"

# 火山引擎
llm:
  provider: volcengine
  model: doubao-pro
  api_key: "your-volcengine-api-key"
```

### Q: 如何使用本地模型？

```yaml
# Ollama 本地部署
llm:
  provider: ollama
  model: llama3
  base_url: "http://localhost:11434"
```

---

> **提示**: 如有更多问题，请查看 [常见问题](./faq.md) 或 [故障排查](./troubleshooting.md)。