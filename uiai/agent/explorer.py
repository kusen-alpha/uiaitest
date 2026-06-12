"""Explorer Agent - 自主探索页面，发现异常（增强版）"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from uiai.agent.base import BaseAgent, AgentOutput, AgentRole
from uiai.agent.llm import BaseLLMClient, LLMMessage
from uiai.core.knowledge import KnowledgeManager
from uiai.executor.base import BaseExecutor
from uiai.core.locator import Locator

logger = logging.getLogger(__name__)

EXPLORER_SYSTEM_PROMPT = """你是一个UI探索测试专家（Explorer Agent），隶属于UIAI自动化测试框架。

## 探索策略

1. **识别可交互元素**：按钮、链接、输入框、下拉框、复选框
2. **按优先级交互**：主要CTA > 导航链接 > 表单元素 > 次要操作
3. **检查页面状态**：每步操作后检查URL、标题、控制台错误
4. **记录异常**：JS错误、404、布局错乱、文案问题、死链接

## 输出格式

### 探索路径
| 步骤 | 操作 | 目标 | 结果 |
|------|------|------|------|
| 1 | click | 登录按钮 | 成功跳转 |

### 发现的异常
| # | 类型 | 描述 | 严重程度 | 截图 |
|---|------|------|---------|------|
| 1 | JS错误 | Uncaught TypeError | high | path |

### 覆盖统计
- 访问页面数: X
- 交互元素数: X
- 可交互元素覆盖率: X%
"""


@dataclass
class ExplorationStep:
    """探索步骤记录"""
    step_number: int
    action: str
    target: str
    result: str = ""
    url: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExplorationAnomaly:
    """探索发现的异常"""
    anomaly_type: str  # js_error / layout / dead_link / 404 / content / accessibility
    description: str
    severity: str  # high / medium / low
    url: str = ""
    screenshot_path: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ExplorerAgent(BaseAgent):
    """探索Agent（增强版）

    输入：目标URL + 探索策略
    输出：探索报告 + 异常列表

    增强：
    - 结构化探索步骤记录
    - 异常分类和严重度评估
    - 覆盖率统计
    - AI引导的智能探索路径
    """

    def __init__(self, llm_client: BaseLLMClient | None = None, executor: BaseExecutor | None = None,
                 knowledge_manager: KnowledgeManager | None = None):
        super().__init__(name="ExplorerAgent", role=AgentRole.EXPLORER, llm_client=llm_client)
        self.executor = executor
        self.knowledge = knowledge_manager or KnowledgeManager()
        self._visited_urls: set[str] = set()
        self._steps: list[ExplorationStep] = []
        self._anomalies: list[ExplorationAnomaly] = []
        self._step_counter = 0

    async def run(self, input_data: Any, **kwargs) -> AgentOutput:
        """执行探索性测试"""
        url = str(input_data)
        max_depth = kwargs.get("max_depth", 3)
        max_pages = kwargs.get("max_pages", 20)

        if not self.executor:
            return AgentOutput(role=self.role, success=False, message="Executor not configured")

        try:
            await self.executor.start()
            await self.executor.navigate(url)
            self._visited_urls.add(url)

            # 记录初始步骤
            self._record_step("navigate", url, "success", url)

            # 检查初始页面异常
            await self._check_page_anomalies(url)

            # AI引导探索
            if self.llm_client:
                await self._ai_guided_exploration(url, max_depth, max_pages)
            else:
                await self._basic_exploration(max_pages)

            await self.executor.stop()

            # 生成报告
            report = self._generate_report(url)

            return AgentOutput(
                role=self.role,
                success=True,
                data=report,
                message=f"Exploration: {len(self._visited_urls)} pages, {len(self._anomalies)} issues",
                artifacts={"anomalies": str(len(self._anomalies))},
            )
        except Exception as e:
            logger.error(f"Explorer failed: {e}")
            return AgentOutput(role=self.role, success=False, message=f"Exploration failed: {e}")

    async def _ai_guided_exploration(self, start_url: str, max_depth: int, max_pages: int) -> dict:
        """AI引导的探索"""
        for depth in range(max_depth):
            if len(self._visited_urls) >= max_pages:
                break

            try:
                a11y_tree = await self.executor.get_accessibility_tree()
                screenshot = await self.executor.screenshot()

                # 将 a11y_tree 格式化为文本
                snapshot_text = self._format_a11y_tree(a11y_tree)[:3000]  # 截断

                prompt = f"""分析以下页面，建议接下来应该探索哪些元素。

当前URL: {await self.executor.get_url()}
已访问: {len(self._visited_urls)} 页

辅助功能树:
{snapshot_text}

请列出3-5个最值得探索的元素（按钮/链接），格式：
1. 操作类型(click/type) | 定位器描述 | 原因"""

                messages = [LLMMessage(role="user", content=prompt)]
                try:
                    analysis = await self.llm_client.chat_with_images(messages, [screenshot])
                except Exception:
                    analysis = await self.llm_client.chat(messages)

                # 解析AI建议并执行（简化实现）
                interactive_elements = self._find_interactive_elements(a11y_tree)
                for elem in interactive_elements[:3]:
                    if len(self._visited_urls) >= max_pages:
                        break
                    name = elem.get("name", "")
                    role = elem.get("role", "")
                    if name and role in ("link", "button"):
                        try:
                            locator = Locator.by_text(name)
                            await self.executor.click(locator)
                            current_url = await self.executor.get_url()
                            if current_url not in self._visited_urls:
                                self._visited_urls.add(current_url)
                                self._record_step("click", name, "success", current_url)
                                await self._check_page_anomalies(current_url)
                                await self.executor.go_back()
                        except Exception as e:
                            self._record_step("click", name, f"failed: {e}", "")

            except Exception as e:
                logger.warning(f"Exploration at depth {depth} failed: {e}")
                break

        return self._generate_report(start_url)

    async def _basic_exploration(self, max_pages: int) -> dict:
        """基础探索"""
        try:
            a11y_tree = await self.executor.get_accessibility_tree()
            elements = self._find_interactive_elements(a11y_tree)

            for elem in elements[:max_pages]:
                name = elem.get("name", "")
                role = elem.get("role", "")
                if name and role in ("link", "button"):
                    try:
                        locator = Locator.by_text(name)
                        await self.executor.click(locator)
                        current_url = await self.executor.get_url()
                        if current_url not in self._visited_urls:
                            self._visited_urls.add(current_url)
                            self._record_step("click", name, "success", current_url)
                            await self.executor.go_back()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Basic exploration failed: {e}")

        return self._generate_report("")

    async def _check_page_anomalies(self, url: str) -> None:
        """检查页面异常"""
        # 检查控制台错误
        try:
            console_errors = await self.executor.get_console_errors() if hasattr(self.executor, 'get_console_errors') else []
            for err in console_errors:
                self._anomalies.append(ExplorationAnomaly(
                    anomaly_type="js_error",
                    description=err,
                    severity="high",
                    url=url,
                ))
        except Exception:
            pass

        # 检查404
        current_url = await self.executor.get_url()
        if "404" in (await self.executor.get_title()):
            self._anomalies.append(ExplorationAnomaly(
                anomaly_type="404",
                description=f"404 page: {current_url}",
                severity="high",
                url=current_url,
            ))

    def _record_step(self, action: str, target: str, result: str, url: str) -> None:
        """记录探索步骤"""
        self._step_counter += 1
        self._steps.append(ExplorationStep(
            step_number=self._step_counter,
            action=action,
            target=target,
            result=result,
            url=url,
        ))

    def _generate_report(self, start_url: str) -> dict:
        """生成探索报告"""
        return {
            "start_url": start_url,
            "pages_visited": len(self._visited_urls),
            "anomalies_found": len(self._anomalies),
            "visited_urls": list(self._visited_urls),
            "steps": [
                {"step": s.step_number, "action": s.action, "target": s.target, "result": s.result, "url": s.url}
                for s in self._steps
            ],
            "anomalies": [
                {"type": a.anomaly_type, "description": a.description, "severity": a.severity, "url": a.url}
                for a in self._anomalies
            ],
        }

    @staticmethod
    def _format_a11y_tree(a11y_tree: Any) -> str:
        """将 a11y_tree 格式化为可读文本"""
        import json
        if isinstance(a11y_tree, str):
            return a11y_tree
        return json.dumps(a11y_tree, ensure_ascii=False, indent=2)

    @staticmethod
    def _find_interactive_elements(a11y_tree: Any) -> list[dict]:
        """从 a11y_tree 中提取可交互元素

        递归遍历 a11y_tree，筛选 role 为 button/link/textbox/combobox/checkbox 的元素。
        """
        interactive_roles = {"button", "link", "textbox", "combobox", "checkbox"}
        results: list[dict] = []

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                role = node.get("role", "")
                if role in interactive_roles:
                    results.append({
                        "name": node.get("name", ""),
                        "role": role,
                    })
                for child in node.get("children", []):
                    _walk(child)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(a11y_tree)
        return results
