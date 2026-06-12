"""UIAI CLI - 命令行入口（增强版）"""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path
import subprocess
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler

from uiai import __version__
from uiai.config import UIAIConfig

console = Console()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=True, show_path=False)],
    )


@click.group()
@click.version_option(version=__version__, prog_name="uiai")
@click.option("-v", "--verbose", is_flag=True, help="详细输出")
@click.option("-c", "--config", "config_path", help="配置文件路径", type=click.Path())
@click.pass_context
def main(ctx, verbose: bool, config_path: str | None):
    """UIAI - UI AI 自动化测试框架

    自研代码Agent中控 + 开源技术底座
    支持Web/App多平台，测试用例执行、断言、报告、自愈全流程
    """
    setup_logging(verbose)
    ctx.ensure_object(dict)
    if config_path:
        ctx.obj["config"] = UIAIConfig.from_yaml(config_path)
    else:
        ctx.obj["config"] = UIAIConfig()


@main.command()
@click.argument("url")
@click.option("--browser", default="chromium", help="浏览器类型")
@click.option("--headed", is_flag=True, help="有头模式")
@click.option("--output", default="./reports", help="报告输出目录")
@click.option("--healing/--no-healing", default=True, help="是否启用自愈")
@click.option("--mode", type=click.Choice(["script", "agent", "local_dev"]), default="script", help="运行模式")
@click.option("--record/--no-record", default=False, help="录制为代码")
@click.pass_context
def run(ctx, url: str, browser: str, headed: bool, output: str, healing: bool, mode: str, record: bool):
    """运行测试用例"""
    config: UIAIConfig = ctx.obj["config"]
    config.browser.browser_type = browser
    config.browser.headless = not headed
    config.report.output_dir = output
    config.healing.enabled = healing

    console.print(Panel(f"[bold green]UIAI v{__version__}[/bold green]\n目标: {url}", title="启动测试"))

    from uiai.core.test_case import TestCase, TestStep, Priority
    from uiai.core.locator import Locator
    from uiai.orchestrator.orchestrator import TestOrchestrator

    orchestrator = TestOrchestrator(config)

    test = TestCase(id="smoke-001", name=f"冒烟测试 - {url}", priority=Priority.SMOKE)
    test.add_step("导航到目标页面", "navigate", value=url)
    test.add_step("验证页面加载", "assert_url")

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("执行测试...", total=None)

        async def _run():
            result = await orchestrator.run_test(test)
            return result

        result = asyncio.run(_run())
        progress.update(task, completed=True)

    from uiai.report.generator import ReportGenerator
    from uiai.core.result import SuiteResult
    from datetime import datetime

    suite = SuiteResult(suite_name="smoke")
    suite.results.append(result)
    suite.end_time = datetime.now()

    report_gen = ReportGenerator(output)
    json_path = report_gen.generate_json_report(suite)
    html_path = report_gen.generate_html_report(suite)
    report_gen.generate_console_report(suite)

    console.print(f"\n报告已生成:")
    console.print(f"  JSON: {json_path}")
    console.print(f"  HTML: {html_path}")


@main.command()
@click.argument("requirement")
@click.option("--url", help="目标应用URL")
@click.option("--output", default="./test_plans", help="输出目录")
@click.pass_context
def plan(ctx, requirement: str, url: str | None, output: str):
    """AI生成测试计划"""
    config: UIAIConfig = ctx.obj["config"]

    if not config.llm.api_key:
        console.print("[bold red]错误: 需要配置LLM API Key[/bold red]")
        console.print("通过配置文件设置 llm.api_key，或设置环境变量 OPENAI_API_KEY")
        sys.exit(1)

    console.print(Panel(f"[bold blue]生成测试计划[/bold blue]\n需求: {requirement[:100]}..."))

    from uiai.orchestrator.orchestrator import TestOrchestrator
    orchestrator = TestOrchestrator(config)

    async def _plan():
        return await orchestrator.generate_test_plan(requirement, url=url, output_dir=output)

    result = asyncio.run(_plan())

    if result.success:
        console.print(f"[bold green]测试计划已生成[/bold green]")
        if result.artifacts.get("plan"):
            console.print(f"  文件: {result.artifacts['plan']}")
        if result.requires_approval:
            console.print("[yellow]⚠ 需要人工审核[/yellow]")
    else:
        console.print(f"[bold red]生成失败: {result.message}[/bold red]")


@main.command()
@click.argument("plan_path", type=click.Path(exists=True))
@click.option("--url", help="目标应用URL")
@click.option("--output", default="./generated_tests", help="输出目录")
@click.pass_context
def generate(ctx, plan_path: str, url: str | None, output: str):
    """从测试计划生成测试代码"""
    config: UIAIConfig = ctx.obj["config"]
    plan_content = Path(plan_path).read_text(encoding="utf-8")

    from uiai.orchestrator.orchestrator import TestOrchestrator
    orchestrator = TestOrchestrator(config)

    async def _generate():
        return await orchestrator.generate_test_code(plan_content, base_url=url or config.base_url, output_dir=output)

    result = asyncio.run(_generate())

    if result.success:
        console.print(f"[bold green]测试代码已生成[/bold green]")
        if result.artifacts.get("code"):
            console.print(f"  文件: {result.artifacts['code']}")
        if result.requires_approval:
            console.print("[yellow]⚠ 需要人工审核后入库[/yellow]")
    else:
        console.print(f"[bold red]生成失败: {result.message}[/bold red]")


@main.command()
@click.argument("url")
@click.option("--max-pages", default=20, help="最大探索页面数")
@click.option("--max-depth", default=3, help="最大探索深度")
@click.pass_context
def explore(ctx, url: str, max_pages: int, max_depth: int):
    """AI探索性测试"""
    config: UIAIConfig = ctx.obj["config"]
    console.print(Panel(f"[bold magenta]AI探索性测试[/bold magenta]\n目标: {url}"))

    from uiai.orchestrator.orchestrator import TestOrchestrator
    orchestrator = TestOrchestrator(config)

    async def _explore():
        return await orchestrator.explore(url, max_pages=max_pages, max_depth=max_depth)

    result = asyncio.run(_explore())

    if result.success:
        console.print(f"[bold green]探索完成[/bold green]")
        console.print(f"  {result.message}")
    else:
        console.print(f"[bold red]探索失败: {result.message}[/bold red]")


@main.command()
@click.option("--host", default="0.0.0.0", help="MCP服务器地址")
@click.option("--port", default=8080, help="MCP服务器端口")
@click.pass_context
def mcp(ctx, host: str, port: int):
    """启动MCP服务器"""
    config: UIAIConfig = ctx.obj["config"]
    console.print(Panel(f"[bold cyan]UIAI MCP Server[/bold cyan]\n地址: {host}:{port}"))

    try:
        from uiai.mcp.server import start_mcp_server
        asyncio.run(start_mcp_server(config, host, port))
    except ImportError:
        console.print("[bold red]MCP依赖未安装，请运行: pip install mcp[/bold red]")


@main.command()
@click.argument("project_name", required=False, default="my-test-project")
@click.option("--template", default="basic", type=click.Choice(["basic", "advanced"]), help="项目模板")
def init(project_name: str, template: str):
    """初始化测试项目"""
    project_dir = Path(project_name)

    if project_dir.exists():
        console.print(f"[bold red]目录已存在: {project_dir}[/bold red]")
        sys.exit(1)

    # 创建项目结构
    dirs = ["tests", "pages", "data", "reports", "config"]
    for d in dirs:
        (project_dir / d).mkdir(parents=True, exist_ok=True)

    # 创建配置文件
    config_content = """# UIAI 配置文件
browser:
  browser_type: chromium
  headless: true
  viewport:
    width: 1280
    height: 720

llm:
  provider: openai
  model: gpt-4o
  api_key: ""  # 设置你的API Key
  base_url: ""  # 可选：自定义endpoint

healing:
  enabled: true
  auto_apply: false  # 修复需人工审核
  strategies:
    - selector_fallback
    - dom_neighbor_search
    - visual_ocr
    - ai_code_fix

report:
  output_dir: ./reports
  format: html

base_url: http://localhost:3000
timeout: 30000
env: test
"""
    (project_dir / "config" / "default.yaml").write_text(config_content, encoding="utf-8")

    # 创建示例测试
    test_content = '''"""示例测试"""
import asyncio
from uiai.core.locator import Locator
from uiai.core.test_case import TestCase, Priority
from uiai.config import UIAIConfig
from uiai.orchestrator.orchestrator import TestOrchestrator


async def test_example():
    config = UIAIConfig.from_yaml("config/default.yaml")
    orchestrator = TestOrchestrator(config)

    test = TestCase(id="example-001", name="示例测试", priority=Priority.SMOKE)
    test.add_step("导航", "navigate", value=config.base_url)

    result = await orchestrator.run_test(test)
    print(f"结果: {result.status.value}")


if __name__ == "__main__":
    asyncio.run(test_example())
'''
    (project_dir / "tests" / "test_example.py").write_text(test_content, encoding="utf-8")

    # 创建环境配置
    env_content = """# 环境配置
dev:
  base_url: http://localhost:3000
  description: 开发环境

test:
  base_url: http://test.example.com
  description: 测试环境

staging:
  base_url: https://staging.example.com
  description: 预发布环境

prod:
  base_url: https://www.example.com
  description: 生产环境
"""
    (project_dir / "config" / "environments.yaml").write_text(env_content, encoding="utf-8")

    # 创建README
    (project_dir / "uiai.yaml").write_text("config: config/default.yaml\n", encoding="utf-8")

    console.print(Panel(f"[bold green]项目已创建: {project_dir}[/bold green]\n\n"
                        f"目录结构:\n"
                        f"  {project_dir}/\n"
                        f"  ├── config/\n"
                        f"  │   ├── default.yaml      # 主配置\n"
                        f"  │   └── environments.yaml  # 环境配置\n"
                        f"  ├── tests/                 # 测试用例\n"
                        f"  ├── pages/                 # Page Object\n"
                        f"  ├── data/                  # 测试数据\n"
                        f"  ├── reports/               # 测试报告\n"
                        f"  └── uiai.yaml              # 项目入口配置\n\n"
                        f"快速开始:\n"
                        f"  cd {project_dir}\n"
                        f"  uiai run http://localhost:3000",
                        title="项目初始化完成"))


@main.command()
@click.option("--show", is_flag=True, help="显示当前配置")
@click.option("--validate", is_flag=True, help="验证配置文件")
@click.option("--path", "config_path", help="配置文件路径")
@click.pass_context
def config(ctx, show: bool, validate: bool, config_path: str | None):
    """配置管理"""
    cfg: UIAIConfig = ctx.obj["config"]

    if config_path:
        cfg = UIAIConfig.from_yaml(config_path)

    if show or (not validate):
        table = Table(title="UIAI 配置")
        table.add_column("配置项", style="cyan")
        table.add_column("值", style="green")

        import dataclasses
        for field_name in dataclasses.fields(cfg):
            value = getattr(cfg, field_name.name)
            if dataclasses.is_dataclass(value):
                value = dataclasses.asdict(value)
            table.add_row(field_name.name, str(value))

        console.print(table)

    if validate:
        issues = []
        if not cfg.base_url:
            issues.append("base_url 未设置")
        if cfg.llm.api_key:
            console.print("[green]✓ LLM API Key 已配置[/green]")
        else:
            issues.append("llm.api_key 未设置（AI功能不可用）")

        if issues:
            console.print("\n[yellow]配置问题:[/yellow]")
            for issue in issues:
                console.print(f"  ⚠ {issue}")
        else:
            console.print("[bold green]✓ 配置验证通过[/bold green]")


@main.command()
@click.option("--list", "list_records", is_flag=True, help="列出待审批记录")
@click.option("--approve", help="审批指定ID的修复")
@click.option("--reject", help="拒绝指定ID的修复")
@click.option("--metrics", is_flag=True, help="显示自愈指标")
def healing(list_records: bool, approve: str | None, reject: str | None, metrics: bool):
    """自愈记录管理"""
    from uiai.healing.healer import HealingManager
    manager = HealingManager()

    if list_records:
        pending = manager.pending_approvals
        if not pending:
            console.print("[green]没有待审批的自愈记录[/green]")
            return
        table = Table(title="待审批自愈记录")
        table.add_column("ID", style="cyan")
        table.add_column("步骤", style="white")
        table.add_column("策略", style="yellow")
        table.add_column("置信度", style="green")
        for r in pending:
            table.add_row(r.id, r.step_name, r.strategy.value, f"{r.confidence:.0%}")
        console.print(table)

    if approve:
        if manager.approve(approve):
            console.print(f"[green]已审批: {approve}[/green]")
        else:
            console.print(f"[red]未找到记录: {approve}[/red]")

    if reject:
        if manager.reject(reject):
            console.print(f"[yellow]已拒绝: {reject}[/yellow]")
        else:
            console.print(f"[red]未找到记录: {reject}[/red]")

    if metrics:
        m = manager.metrics
        table = Table(title="自愈指标")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green")
        table.add_row("总尝试", str(m.total_attempts))
        table.add_row("总成功", str(m.total_successes))
        table.add_row("总失败", str(m.total_failures))
        table.add_row("成功率", f"{m.success_rate:.1%}")
        table.add_row("待审批", str(m.total_pending_approval))
        console.print(table)


@main.command()
def info():
    """显示框架信息"""
    table = Table(title="UIAI 框架信息")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")

    table.add_row("版本", __version__)
    table.add_row("Python", sys.version.split()[0])
    table.add_row("框架定位", "自研代码Agent中控 + 开源技术底座")
    table.add_row("支持平台", "Web / H5 / Android / iOS / 小程序 / 桌面")
    table.add_row("AI Agent", "Planner / Generator / Healer / Explorer")
    table.add_row("执行引擎", "Playwright (Web) + Appium (App)")
    table.add_row("LLM支持", "OpenAI / Qwen-VL / Ollama / 自定义")
    table.add_row("自愈策略", "选择器降级 / DOM搜索 / OCR / AI修复")
    table.add_row("断言体系", "结构 / 视觉 / 语义 / 自定义匹配器")
    table.add_row("报告格式", "JSON / HTML / Allure / Console / 趋势")

    console.print(table)


@main.command()
@click.argument('recording_file')
@click.option('--headless/--headed', default=True)
@click.pass_context
def replay(ctx, recording_file, headless):
    """回放录制的测试"""
    config: UIAIConfig = ctx.obj["config"]
    recording_path = Path(recording_file)

    if not recording_path.exists():
        console.print(f"[bold red]录制文件不存在: {recording_file}[/bold red]")
        sys.exit(1)

    console.print(Panel(f"[bold blue]回放录制[/bold blue]\n文件: {recording_file}"))

    import json
    from uiai.executor.playwright_executor import PlaywrightExecutor

    recording_data = json.loads(recording_path.read_text(encoding="utf-8"))
    executor = PlaywrightExecutor(config)

    async def _replay():
        return await executor.replay(recording_data, headless=headless)

    result = asyncio.run(_replay())

    if result.success:
        console.print(f"[bold green]回放完成[/bold green]")
    else:
        console.print(f"[bold red]回放失败: {result.message}[/bold red]")


@main.group()
def cache():
    """缓存管理"""
    pass


@cache.command('clear')
def cache_clear():
    """清除所有缓存"""
    from uiai.cache.manager import CacheManager
    manager = CacheManager()
    manager.clear_all()
    console.print("[bold green]缓存已清除[/bold green]")


@cache.command('stats')
def cache_stats():
    """查看缓存统计"""
    from uiai.cache.manager import CacheManager
    manager = CacheManager()
    stats = manager.stats()

    table = Table(title="缓存统计")
    table.add_column("指标", style="cyan")
    table.add_column("值", style="green")
    for key, value in stats.items():
        table.add_row(str(key), str(value))
    console.print(table)


@main.group()
def knowledge():
    """知识库管理"""
    pass


@knowledge.command('show')
@click.option('--level', type=click.Choice(['requirement', 'product', 'experience']))
@click.option('--domain')
def knowledge_show(level, domain):
    """查看知识条目"""
    from uiai.knowledge.manager import KnowledgeManager
    manager = KnowledgeManager()
    results = manager.search(level=level, domain=domain)

    if not results:
        console.print("[yellow]未找到匹配的知识条目[/yellow]")
        return

    table = Table(title="知识条目")
    table.add_column("ID", style="cyan")
    table.add_column("级别", style="yellow")
    table.add_column("领域", style="magenta")
    table.add_column("标题", style="green")
    for entry in results:
        table.add_row(str(entry.id), entry.level, entry.domain, entry.title)
    console.print(table)


@knowledge.command('add')
@click.option('--level', required=True, type=click.Choice(['requirement', 'product', 'experience']))
@click.option('--domain', required=True)
@click.option('--title', required=True)
@click.option('--content', required=True)
def knowledge_add(level, domain, title, content):
    """添加知识条目"""
    from uiai.knowledge.manager import KnowledgeManager
    manager = KnowledgeManager()

    if level == 'requirement':
        manager.add_requirement(domain=domain, title=title, content=content)
    elif level == 'product':
        manager.add_product(domain=domain, title=title, content=content)
    elif level == 'experience':
        manager.add_experience(domain=domain, title=title, content=content)

    console.print(f"[bold green]知识条目已添加[/bold green] (级别: {level}, 领域: {domain})")


@main.command('skill')
def skill_list():
    """列出可用技能"""
    from uiai.skill.registry import SkillRegistry
    registry = SkillRegistry()
    skills = registry.list_skills()

    if not skills:
        console.print("[yellow]没有可用的技能[/yellow]")
        return

    table = Table(title="可用技能")
    table.add_column("名称", style="cyan")
    table.add_column("描述", style="green")
    table.add_column("状态", style="yellow")
    for s in skills:
        table.add_row(s.name, s.description, s.status)
    console.print(table)


@main.command()
@click.argument('trace_dir')
def trace(trace_dir):
    """查看Playwright Trace"""
    trace_path = Path(trace_dir)
    if not trace_path.exists():
        console.print(f"[bold red]Trace目录不存在: {trace_dir}[/bold red]")
        sys.exit(1)

    console.print(f"[bold cyan]启动Playwright Trace查看器: {trace_dir}[/bold cyan]")
    subprocess.run(["npx", "playwright", "show-trace", trace_dir], check=False)


@main.group()
def plugin():
    """插件管理"""
    pass


@plugin.command('list')
def plugin_list():
    """列出已安装插件"""
    from uiai.plugin.manager import PluginManager
    manager = PluginManager()
    plugins = manager.list_plugins()

    if not plugins:
        console.print("[yellow]没有已安装的插件[/yellow]")
        return

    table = Table(title="已安装插件")
    table.add_column("名称", style="cyan")
    table.add_column("版本", style="green")
    table.add_column("状态", style="yellow")
    for p in plugins:
        table.add_row(p.name, p.version, p.status)
    console.print(table)


@plugin.command('enable')
@click.argument('plugin_name')
def plugin_enable(plugin_name):
    """启用插件"""
    from uiai.plugin.manager import PluginManager
    manager = PluginManager()
    if manager.enable(plugin_name):
        console.print(f"[bold green]插件已启用: {plugin_name}[/bold green]")
    else:
        console.print(f"[bold red]插件启用失败: {plugin_name}[/bold red]")


@plugin.command('disable')
@click.argument('plugin_name')
def plugin_disable(plugin_name):
    """禁用插件"""
    from uiai.plugin.manager import PluginManager
    manager = PluginManager()
    if manager.disable(plugin_name):
        console.print(f"[bold yellow]插件已禁用: {plugin_name}[/bold yellow]")
    else:
        console.print(f"[bold red]插件禁用失败: {plugin_name}[/bold red]")


if __name__ == "__main__":
    main()
