# UIAI 官方开源文档

> **UIAI** — AI 驱动的 UI 自动化测试框架，让测试人员用自然语言描述测试需求，由 AI Agent 自动执行测试、断言验证、失败自愈、生成报告。

---

## 文档导航

### 入门指南

| 文档 | 说明 |
|------|------|
| [快速开始](./getting-started.md) | 环境安装、第一个测试用例、CLI 快速使用 |
| [核心概念](./core-concepts.md) | 六 Agent 协作、四层运行模式、感知引擎、Watchdog 守卫 |
| [示例代码](./examples.md) | 完整的代码示例，涵盖各种使用场景 |

### 配置与 API

| 文档 | 说明 |
|------|------|
| [配置详解](./configuration.md) | 浏览器、LLM、自愈、报告等完整配置说明 |
| [API 参考](./api-reference.md) | TestOrchestrator、TestCase、Locator 等核心 API |
| [CLI 命令参考](./cli-reference.md) | 所有 CLI 命令的详细说明 |

### 进阶使用

| 文档 | 说明 |
|------|------|
| [最佳实践](./best-practices.md) | 定位器策略、测试用例组织、性能优化 |
| [故障排查](./troubleshooting.md) | 常见错误、调试技巧、错误码参考 |
| [常见问题](./faq.md) | FAQ 常见问题解答 |

### 开发者指南

| 文档 | 说明 |
|------|------|
| [架构设计](./architecture.md) | 整体架构、模块设计、数据流 |
| [开发者指南](./developer-guide.md) | 扩展 Agent、Watchdog、执行器、插件 |

---

## 快速链接

### 5 分钟快速上手

```python
import asyncio
from uiai import TestOrchestrator
from uiai.config import UIAIConfig

async def main():
    config = UIAIConfig()
    config.llm.api_key = "your-api-key"
    
    orchestrator = TestOrchestrator(config)
    
    # R2 Agent 模式：自然语言执行测试
    result = await orchestrator.run_agent_test(
        "打开百度搜索，输入'UIAI自动化测试'，点击搜索按钮"
    )
    
    print(f"测试结果: {result.status.value}")

asyncio.run(main())
```

### 核心特性一览

| 特性 | 说明 |
|------|------|
| **六 Agent 协作** | Planner / Executor / Judge / Healer / Explorer / CodeRecorder |
| **四层运行模式** | R1_SCRIPT / R2_AGENT / R3_LOCAL_DEV |
| **四种感知模式** | A11Y_SNAPSHOT / DOM_SERIALIZE / VISUAL_SCREENSHOT / HYBRID |
| **九种 Watchdog** | 弹窗、验证码、崩溃、安全、网络、存储、下载、DOM 变更、UI 异常 |
| **四层自愈降级** | 选择器降级 → DOM 邻近搜索 → 视觉定位兜底 → AI 修复建议 |
| **三层缓存系统** | PlanCache / LocateCache / FeatureCache |
| **三级知识沉淀** | 需求级 / 产品级 / 经验级 |

### 支持平台

| 平台 | 执行引擎 |
|------|---------|
| Web | Playwright |
| H5 | Playwright |
| Android | Appium |
| iOS | Appium |
| 小程序 | Playwright |
| 桌面应用 | Playwright |

---

## 版本信息

- **当前版本**: v1.0.0
- **发布日期**: 2026-06-12
- **Python 版本**: 3.10+
- **许可证**: MIT

---

## 获取帮助

- **GitHub**: https://github.com/uiai-framework/uiai
- **问题反馈**: https://github.com/uiai-framework/uiai/issues
- **文档**: https://uiai-framework.github.io/docs

---

> **UIAI** — 让 AI 帮你写测试、跑测试、修测试。