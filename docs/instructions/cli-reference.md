# CLI 命令参考

本文档详细介绍 UIAI 的所有 CLI 命令。

---

## 目录

1. [命令概览](#一命令概览)
2. [run](#二run)
3. [plan](#三plan)
4. [generate](#四generate)
5. [explore](#五explore)
6. [init](#六init)
7. [config](#七config)
8. [healing](#八healing)
9. [cache](#九cache)
10. [knowledge](#十knowledge)
11. [skill](#十一skill)
12. [plugin](#十二plugin)
13. [mcp](#十三mcp)
14. [replay](#十四replay)
15. [trace](#十五trace)
16. [info](#十六info)

---

## 一、命令概览

### 1.1 基本用法

```bash
uiai [命令] [选项]
```

### 1.2 命令列表

| 命令 | 说明 |
|------|------|
| run | 运行测试用例 |
| plan | AI 生成测试计划 |
| generate | 从计划生成测试代码 |
| explore | AI 探索性测试 |
| init | 初始化测试项目 |
| config | 配置管理 |
| healing | 自愈记录管理 |
| cache | 缓存管理 |
| knowledge | 知识库管理 |
| skill | 查看技能列表 |
| plugin | 插件管理 |
| mcp | 启动 MCP 服务器 |
| replay | 回放录制的测试 |
| trace | 查看 Playwright Trace |
| info | 显示框架信息 |

### 1.3 全局选项

| 选项 | 说明 |
|------|------|
| -v, --verbose | 详细输出 |
| -q, --quiet | 安静模式 |
| --config | 配置文件路径 |
| --env | 运行环境 |
| --help | 显示帮助 |

---

## 二、run

运行测试用例。

### 2.1 基本用法

```bash
uiai run <url> [选项]
```

### 2.2 参数

| 参数 | 说明 |
|------|------|
| url | 目标 URL |

### 2.3 选项

| 选项 | 说明 |
|------|------|
| --browser | 浏览器类型（chromium/firefox/safari） |
| --headed | 有头模式 |
| --headless | 无头模式 |
| --output | 报告输出目录 |
| --healing | 启用自愈 |
| --no-healing | 禁用自愈 |
| --mode | 运行模式（script/agent） |
| --record | 录制为代码 |
| --max-steps | 最大执行步数 |
| --perception | 感知模式（a11y/dom/visual/hybrid） |
| --timeout | 超时时间（毫秒） |
| --parallel | 并行数 |

### 2.4 示例

```bash
# R1 脚本模式
uiai run https://example.com --mode script

# R2 Agent 模式
uiai run https://example.com --mode agent

# 有头模式（调试用）
uiai run https://example.com --headed

# 录制为代码
uiai run https://example.com --mode agent --record

# 指定感知模式
uiai run https://example.com --mode agent --perception hybrid

# 限制最大步数
uiai run https://example.com --mode agent --max-steps 30

# 禁用自愈
uiai run https://example.com --no-healing

# 指定输出目录
uiai run https://example.com --output ./reports

# 详细输出
uiai run https://example.com -v
```

---

## 三、plan

AI 生成测试计划。

### 3.1 基本用法

```bash
uiai plan <需求描述> [选项]
```

### 3.2 参数

| 参数 | 说明 |
|------|------|
| 需求描述 | 自然语言需求描述 |

### 3.3 选项

| 选项 | 说明 |
|------|------|
| --url | 目标应用 URL |
| --output | 输出目录 |
| --domain | 业务领域 |
| --format | 输出格式（markdown/json） |

### 3.4 示例

```bash
# 生成测试计划
uiai plan "测试购物车添加商品、修改数量、删除商品功能" --url https://example.com

# 输出到指定目录
uiai plan "测试用户注册流程" --url https://example.com --output ./plans

# 指定业务领域
uiai plan "测试订单支付流程" --url https://example.com --domain ecommerce

# JSON 格式输出
uiai plan "测试登录功能" --url https://example.com --format json
```

---

## 四、generate

从测试计划生成测试代码。

### 4.1 基本用法

```bash
uiai generate <计划文件> [选项]
```

### 4.2 参数

| 参数 | 说明 |
|------|------|
| 计划文件 | 测试计划文件路径（Markdown） |

### 4.3 选项

| 选项 | 说明 |
|------|------|
| --url | 目标应用 URL |
| --output | 输出目录 |
| --format | 输出格式（python/pytest） |

### 4.4 示例

```bash
# 从计划生成代码
uiai generate test_plans/购物车测试计划.md --output ./generated_tests

# 指定 URL
uiai generate test_plans/登录测试计划.md --url https://example.com

# pytest 格式
uiai generate test_plans/搜索测试计划.md --format pytest
```

---

## 五、explore

AI 探索性测试。

### 5.1 基本用法

```bash
uiai explore <url> [选项]
```

### 5.2 参数

| 参数 | 说明 |
|------|------|
| url | 目标 URL |

### 5.3 选项

| 选项 | 说明 |
|------|------|
| --max-pages | 最大探索页面数 |
| --max-depth | 最大探索深度 |
| --output | 输出目录 |
| --headed | 有头模式 |
| --timeout | 超时时间（毫秒） |

### 5.4 示例

```bash
# 探索性测试
uiai explore https://example.com

# 限制探索范围
uiai explore https://example.com --max-pages 20 --max-depth 3

# 有头模式
uiai explore https://example.com --headed

# 指定输出目录
uiai explore https://example.com --output ./explore_reports
```

---

## 六、init

初始化测试项目。

### 6.1 基本用法

```bash
uiai init [项目名称] [选项]
```

### 6.2 参数

| 参数 | 说明 |
|------|------|
| 项目名称 | 项目名称（可选） |

### 6.3 选项

| 选项 | 说明 |
|------|------|
| --template | 项目模板（basic/advanced） |
| --path | 项目路径 |

### 6.4 项目模板

| 模板 | 说明 |
|------|------|
| basic | 基础模板，包含基本配置 |
| advanced | 高级模板，包含完整结构 |

### 6.5 生成的项目结构

**basic 模板**:

```
my-test-project/
├── uiai.yaml              # 配置文件
├── tests/                 # 测试用例
└── reports/               # 测试报告
```

**advanced 模板**:

```
my-test-project/
├── config/
│   ├── default.yaml      # 主配置
│   ├── dev.yaml          # 开发环境
│   ├── test.yaml         # 测试环境
│   └── staging.yaml      # 预发布环境
├── tests/                 # 测试用例
│   ├── login/
│   ├── cart/
│   └── order/
├── pages/                 # Page Object
├── data/                  # 测试数据
├── reports/               # 测试报告
├── checkpoints/           # 检查点
├── downloads/             # 下载文件
└── uiai.yaml              # 项目入口配置
```

### 6.6 示例

```bash
# 创建基础项目
uiai init my-test-project

# 创建高级项目
uiai init my-test-project --template advanced

# 指定路径
uiai init --path /path/to/project
```

---

## 七、config

配置管理。

### 7.1 基本用法

```bash
uiai config [选项]
```

### 7.2 选项

| 选项 | 说明 |
|------|------|
| --show | 显示当前配置 |
| --validate | 验证配置文件 |
| --path | 配置文件路径 |
| --set | 设置配置项 |
| --get | 获取配置项 |

### 7.3 示例

```bash
# 显示当前配置
uiai config --show

# 验证配置文件
uiai config --validate

# 指定配置文件路径
uiai config --path /path/to/uiai.yaml --show

# 获取配置项
uiai config --get browser.headless

# 设置配置项
uiai config --set browser.headless=false
```

---

## 八、healing

自愈记录管理。

### 8.1 基本用法

```bash
uiai healing [选项]
```

### 8.2 选项

| 选项 | 说明 |
|------|------|
| --list | 列出待审批记录 |
| --approve <id> | 审批指定 ID 的修复 |
| --reject <id> | 拒绝指定 ID 的修复 |
| --metrics | 显示自愈指标 |
| --clear | 清除所有记录 |

### 8.3 示例

```bash
# 列出待审批记录
uiai healing --list

# 审批修复
uiai healing --approve heal-001

# 拒绝修复
uiai healing --reject heal-002

# 显示自愈指标
uiai healing --metrics

# 输出：
# 自愈成功率: 85%
# 待审批记录: 3
# 已审批记录: 15
# 总修复次数: 20

# 清除所有记录
uiai healing --clear
```

---

## 九、cache

缓存管理。

### 9.1 基本用法

```bash
uiai cache <子命令>
```

### 9.2 子命令

| 子命令 | 说明 |
|------|------|
| clear | 清除所有缓存 |
| stats | 查看缓存统计 |
| save | 持久化缓存 |
| load | 加载缓存 |

### 9.3 示例

```bash
# 查看缓存统计
uiai cache stats

# 输出：
# Plan 缓存: 10 条
# Locate 缓存: 50 条
# Feature 缓存: 20 条
# 总大小: 1024 KB

# 清除所有缓存
uiai cache clear

# 持久化缓存
uiai cache save

# 加载缓存
uiai cache load
```

---

## 十、knowledge

知识库管理。

### 10.1 基本用法

```bash
uiai knowledge <子命令> [选项]
```

### 10.2 子命令

| 子命令 | 说明 |
|------|------|
| show | 查看知识条目 |
| add | 添加知识条目 |
| search | 搜索知识 |
| clear | 清除知识库 |
| stats | 查看统计 |

### 10.3 show 选项

| 选项 | 说明 |
|------|------|
| --level | 知识级别（requirement/product/experience） |
| --domain | 业务领域 |
| --limit | 显示数量 |

### 10.4 add 选项

| 选项 | 说明 |
|------|------|
| --level | 知识级别（必填） |
| --domain | 业务领域（必填） |
| --title | 标题（必填） |
| --content | 内容（必填） |
| --tags | 标签 |

### 10.5 search 选项

| 选项 | 说明 |
|------|------|
| --query | 搜索关键词 |
| --domain | 业务领域 |
| --level | 知识级别 |
| --top-k | 返回数量 |

### 10.6 示例

```bash
# 查看知识条目
uiai knowledge show --level experience --domain ecommerce

# 添加知识条目
uiai knowledge add \
  --level requirement \
  --domain ecommerce \
  --title "购物车限制" \
  --content "最多99件"

# 搜索知识
uiai knowledge search --query "购物车" --domain ecommerce

# 查看统计
uiai knowledge stats

# 清除知识库
uiai knowledge clear
```

---

## 十一、skill

查看技能列表。

### 11.1 基本用法

```bash
uiai skill [选项]
```

### 11.2 选项

| 选项 | 说明 |
|------|------|
| --list | 列出所有技能 |
| --detail <name> | 查看技能详情 |

### 11.3 示例

```bash
# 列出所有技能
uiai skill --list

# 输出：
# 技能列表：
# - navigate: 导航到 URL
# - click: 点击元素
# - type: 输入文本
# - fill: 填充表单
# - select: 选择下拉选项
# - scroll: 滚动页面
# - drag: 拖拽元素
# - screenshot: 截图
# - wait: 等待元素
# - assert: 断言验证

# 查看技能详情
uiai skill --detail click

# 输出：
# 技能: click
# 描述: 点击元素
# 输入原语: ELEMENT
# 参数:
#   - locator: 定位器（必填）
#   - timeout: 超时时间（可选）
```

---

## 十二、plugin

插件管理。

### 12.1 基本用法

```bash
uiai plugin <子命令>
```

### 12.2 子命令

| 子命令 | 说明 |
|------|------|
| list | 列出已安装插件 |
| enable <name> | 启用插件 |
| disable <name> | 禁用插件 |
| install <name> | 安装插件 |
| uninstall <name> | 卸载插件 |

### 12.3 示例

```bash
# 列出已安装插件
uiai plugin list

# 启用插件
uiai plugin enable my-plugin

# 禁用插件
uiai plugin disable my-plugin

# 安装插件
uiai plugin install my-plugin

# 卸载插件
uiai plugin uninstall my-plugin
```

---

## 十三、mcp

启动 MCP 服务器。

### 13.1 基本用法

```bash
uiai mcp [选项]
```

### 13.2 选项

| 选项 | 说明 |
|------|------|
| --host | 服务器地址 |
| --port | 服务器端口 |
| --transport | 传输方式（stdio/http） |

### 13.3 示例

```bash
# 启动 MCP 服务器（默认）
uiai mcp

# 指定地址和端口
uiai mcp --host 0.0.0.0 --port 8080

# 使用 stdio 传输
uiai mcp --transport stdio

# 使用 HTTP 传输
uiai mcp --transport http --port 8080
```

---

## 十四、replay

回放录制的测试。

### 14.1 基本用法

```bash
uiai replay <录制文件> [选项]
```

### 14.2 参数

| 参数 | 说明 |
|------|------|
| 录制文件 | 录制文件路径 |

### 14.3 选项

| 选项 | 说明 |
|------|------|
| --headed | 有头模式 |
| --speed | 回放速度（0.5-2.0） |
| --pause | 每步暂停时间（毫秒） |

### 14.4 示例

```bash
# 回放录制
uiai replay recordings/login_test.json

# 有头模式
uiai replay recordings/login_test.json --headed

# 加速回放
uiai replay recordings/login_test.json --speed 1.5

# 每步暂停
uiai replay recordings/login_test.json --pause 500
```

---

## 十五、trace

查看 Playwright Trace。

### 15.1 基本用法

```bash
uiai trace <trace文件> [选项]
```

### 15.2 参数

| 参数 | 说明 |
|------|------|
| trace文件 | Trace 文件路径（.zip） |

### 15.3 选项

| 选项 | 说明 |
|------|------|
| --open | 打开 Trace Viewer |
| --export | 导出为 HTML |

### 15.4 示例

```bash
# 打开 Trace Viewer
uiai trace reports/trace.zip --open

# 导出为 HTML
uiai trace reports/trace.zip --export trace.html
```

---

## 十六、info

显示框架信息。

### 16.1 基本用法

```bash
uiai info
```

### 16.2 输出

```
UIAI Framework v1.0.0
Python: 3.10.x
Playwright: 1.40.x
Platform: Windows

配置:
  浏览器: chromium
  LLM: gpt-4o
  自愈: enabled
  缓存: enabled
  知识库: enabled

模块:
  - TestOrchestrator
  - PlannerAgent
  - ExecutorAgent
  - JudgeAgent
  - HealerAgent
  - ExplorerAgent
  - CodeRecorder
  - PerceptionEngine
  - CacheManager
  - KnowledgeManager
  - WatchdogManager
  - AssertionEngine
  - EventBus
```

---

> **下一步**: 查看 [最佳实践](./best-practices.md) 或 [故障排查](./troubleshooting.md)。