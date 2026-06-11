"""告警系统 - 测试失败/Flaky检测/通过率监控告警"""
from __future__ import annotations
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    TEST_FAILED = "test_failed"
    PASS_RATE_DROP = "pass_rate_drop"
    FLAKY_DETECTED = "flaky_detected"
    WORKER_OFFLINE = "worker_offline"
    HEALING_RATE_HIGH = "healing_rate_high"
    SUITE_TIMEOUT = "suite_timeout"


@dataclass
class Alert:
    """告警消息"""
    alert_type: AlertType
    level: AlertLevel
    title: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type.value,
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class AlertChannel(ABC):
    """告警通道基类"""

    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """发送告警"""


class ConsoleAlertChannel(AlertChannel):
    """控制台告警通道"""

    async def send(self, alert: Alert) -> bool:
        icon = {"info": "ℹ", "warning": "⚠", "critical": "🚨"}.get(alert.level.value, "!")
        print(f"{icon} [{alert.level.value.upper()}] {alert.title}: {alert.message}")
        return True


class WebhookAlertChannel(AlertChannel):
    """Webhook告警通道（飞书/钉钉/企微/Slack）"""

    def __init__(self, url: str, headers: dict | None = None):
        self.url = url
        self.headers = headers or {}

    async def send(self, alert: Alert) -> bool:
        try:
            import aiohttp
            payload = self._format_payload(alert)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.url, json=payload, headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning(f"Webhook alert failed: {e}")
            return False

    def _format_payload(self, alert: Alert) -> dict:
        """格式化为通用Webhook payload"""
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"content": f"[{alert.level.value.upper()}] {alert.title}"},
                    "template": {"warning": "orange", "critical": "red", "info": "blue"}.get(alert.level.value, "blue"),
                },
                "elements": [
                    {"tag": "div", "text": {"content": alert.message}},
                    {"tag": "div", "text": {"content": f"时间: {alert.timestamp}"}},
                ],
            },
        }


class AlertManager:
    """告警管理器

    管理告警规则和通道：
    1. 定义告警规则（通过率阈值、Flaky阈值等）
    2. 多通道发送（控制台/Webhook/邮件等）
    3. 告警抑制（避免重复告警）
    """

    def __init__(self):
        self._channels: list[AlertChannel] = []
        self._rules: list[dict] = []
        self._sent_alerts: dict[str, datetime] = {}  # 抑制重复
        self._suppress_interval = 300  # 5分钟内不重复告警

    def add_channel(self, channel: AlertChannel) -> None:
        self._channels.append(channel)

    def add_rule(self, alert_type: AlertType, condition: Any, level: AlertLevel = AlertLevel.WARNING) -> None:
        self._rules.append({"type": alert_type, "condition": condition, "level": level})

    async def emit(self, alert: Alert) -> None:
        """发送告警"""
        # 抑制检查
        key = f"{alert.alert_type.value}:{alert.title}"
        now = datetime.now()
        if key in self._sent_alerts:
            elapsed = (now - self._sent_alerts[key]).total_seconds()
            if elapsed < self._suppress_interval:
                return

        self._sent_alerts[key] = now

        for channel in self._channels:
            try:
                await channel.send(alert)
            except Exception as e:
                logger.warning(f"Alert channel error: {e}")

    async def check_pass_rate(self, pass_rate: float, suite_name: str) -> None:
        """检查通过率"""
        if pass_rate < 0.5:
            await self.emit(Alert(
                alert_type=AlertType.PASS_RATE_DROP,
                level=AlertLevel.CRITICAL,
                title=f"通过率严重下降: {suite_name}",
                message=f"通过率仅 {pass_rate:.1%}，请立即检查！",
                data={"suite_name": suite_name, "pass_rate": pass_rate},
            ))
        elif pass_rate < 0.8:
            await self.emit(Alert(
                alert_type=AlertType.PASS_RATE_DROP,
                level=AlertLevel.WARNING,
                title=f"通过率下降: {suite_name}",
                message=f"通过率 {pass_rate:.1%}，低于80%阈值",
                data={"suite_name": suite_name, "pass_rate": pass_rate},
            ))

    async def check_flaky(self, flaky_count: int, total_count: int) -> None:
        """检查Flaky测试"""
        if total_count > 0 and flaky_count / total_count > 0.2:
            await self.emit(Alert(
                alert_type=AlertType.FLAKY_DETECTED,
                level=AlertLevel.WARNING,
                title="Flaky测试比例过高",
                message=f"检测到 {flaky_count}/{total_count} 个Flaky测试 ({flaky_count/total_count:.1%})",
                data={"flaky_count": flaky_count, "total_count": total_count},
            ))
