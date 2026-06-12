"""Watchdog 守卫系统 - 浏览器自动化全生命周期监控与自动处理

提供 9 个专用 Watchdog，覆盖弹窗、验证码、崩溃、安全、网络、存储、
下载、DOM 变更、UI 异常等场景。所有 Watchdog 通过 EventBus 解耦通信，
由 WatchdogManager 统一管理生命周期。
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from uiai.core.eventbus import EventBus, Event

from uiai.core.eventbus import Event as _Event
from uiai.core.eventbus import WatchdogEvent

logger = logging.getLogger(__name__)


# ── 基类 ──────────────────────────────────────────────────────


class BaseWatchdog(ABC):
    """Watchdog 抽象基类

    所有守卫必须实现 name 属性和 on_event / start / stop 三个生命周期方法。
    on_event 返回可选字典，用于向 Agent 上下文注入信息。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """守卫名称，全局唯一标识"""

    @abstractmethod
    async def on_event(self, event: _Event) -> Optional[dict]:
        """处理事件

        Args:
            event: 来自 EventBus 的事件对象。

        Returns:
            需要注入到 Agent 上下文的额外数据，无则返回 None。
        """

    @abstractmethod
    async def start(self) -> None:
        """初始化守卫（注册事件订阅等）"""

    @abstractmethod
    async def stop(self) -> None:
        """清理守卫（取消订阅、释放资源等）"""


# ── 1. PopupWatchdog ─────────────────────────────────────────


class PopupWatchdog(BaseWatchdog):
    """JS 弹窗自动处理

    监听 WatchdogEvent.POPUP_DETECTED，自动关闭 alert / confirm / prompt，
    并将弹窗文本注入 Agent 上下文。
    """

    def __init__(self, event_bus: EventBus, *, default_prompt_value: str = "") -> None:
        self._bus = event_bus
        self._default_prompt_value = default_prompt_value
        self._handler_id: str | None = None
        self._popup_history: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "popup"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_popup,
            event_type=WatchdogEvent.POPUP_DETECTED,
        )
        logger.info("PopupWatchdog 已启动")

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        logger.info("PopupWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        """由 _handle_popup 委托调用"""
        dialog_type = event.data.get("dialog_type", "alert")
        message = event.data.get("message", "")
        default_value = event.data.get("default_value", "")

        self._popup_history.append({
            "dialog_type": dialog_type,
            "message": message,
            "default_value": default_value,
            "timestamp": event.timestamp.isoformat(),
        })

        # 根据 dialog 类型决定处理方式
        accept = True
        prompt_value = self._default_prompt_value or default_value

        if dialog_type == "prompt" and prompt_value:
            # prompt 弹窗需要输入值后确认
            action = f"已自动输入 '{prompt_value}' 并确认"
        elif dialog_type == "confirm":
            action = "已自动确认"
        else:
            action = "已自动关闭"

        logger.info("PopupWatchdog: %s 弹窗 — %s (内容: %s)", dialog_type, action, message[:200])

        return {
            "popup_handled": True,
            "dialog_type": dialog_type,
            "message": message,
            "action": action,
            "prompt_value": prompt_value if dialog_type == "prompt" else None,
        }

    async def _handle_popup(self, event: _Event) -> None:
        """EventBus 回调入口"""
        await self.on_event(event)


# ── 2. CaptchaWatchdog ───────────────────────────────────────


class CaptchaWatchdog(BaseWatchdog):
    """CAPTCHA 验证码检测

    检测页面中的验证码元素，支持 2FA/OTP 自动处理（pyotp），
    无法自动解决时通过事件通知人工介入。
    """

    # 常见验证码选择器特征
    _CAPTCHA_SELECTORS: list[str] = [
        'iframe[src*="captcha"]',
        'iframe[src*="recaptcha"]',
        'iframe[src*="hcaptcha"]',
        '[class*="captcha"]',
        '[id*="captcha"]',
        '[class*="verify"]',
        '[id*="verify-code"]',
        'img[src*="captcha"]',
        'img[alt*="验证码"]',
        'img[alt*="captcha"]',
    ]

    # OTP 输入框特征
    _OTP_SELECTORS: list[str] = [
        'input[autocomplete="one-time-code"]',
        'input[name*="otp"]',
        'input[name*="code"]',
        'input[placeholder*="验证码"]',
        'input[placeholder*="OTP"]',
    ]

    def __init__(
        self,
        event_bus: EventBus,
        *,
        totp_secret: str | None = None,
        hotp_secret: str | None = None,
        hotp_counter: int = 0,
    ) -> None:
        self._bus = event_bus
        self._totp_secret = totp_secret
        self._hotp_secret = hotp_secret
        self._hotp_counter = hotp_counter
        self._handler_id: str | None = None
        self._detection_count: int = 0

    @property
    def name(self) -> str:
        return "captcha"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_captcha,
            event_type=WatchdogEvent.CAPTCHA_DETECTED,
        )
        logger.info("CaptchaWatchdog 已启动 (TOTP=%s)", "已配置" if self._totp_secret else "未配置")

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        logger.info("CaptchaWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        captcha_type = event.data.get("captcha_type", "unknown")
        element_info = event.data.get("element_info", {})
        self._detection_count += 1

        # 尝试自动处理 2FA/OTP
        otp_code = await self._try_generate_otp(captcha_type)

        if otp_code:
            logger.info("CaptchaWatchdog: 自动生成 OTP 验证码 (类型=%s)", captcha_type)
            return {
                "captcha_detected": True,
                "captcha_type": captcha_type,
                "auto_solved": True,
                "otp_code": otp_code,
                "element_info": element_info,
            }

        # 无法自动解决 → 通知人工介入
        logger.warning("CaptchaWatchdog: 无法自动解决验证码 (类型=%s)，需人工介入", captcha_type)
        await self._bus.publish(_Event(
            event_type=WatchdogEvent.CAPTCHA_DETECTED,
            source="captcha_watchdog",
            data={
                "captcha_type": captcha_type,
                "auto_solved": False,
                "needs_human": True,
                "element_info": element_info,
            },
        ))

        return {
            "captcha_detected": True,
            "captcha_type": captcha_type,
            "auto_solved": False,
            "needs_human": True,
            "element_info": element_info,
        }

    async def _try_generate_otp(self, captcha_type: str) -> str | None:
        """尝试生成 OTP 验证码"""
        if captcha_type not in ("totp", "2fa", "otp"):
            return None

        # 尝试 TOTP
        if self._totp_secret:
            try:
                import pyotp
                totp = pyotp.TOTP(self._totp_secret)
                return totp.now()
            except ImportError:
                logger.warning("pyotp 未安装，无法自动生成 TOTP 验证码")
            except Exception:
                logger.exception("TOTP 验证码生成失败")

        # 尝试 HOTP
        if self._hotp_secret:
            try:
                import pyotp
                hotp = pyotp.HOTP(self._hotp_secret)
                code = hotp.at(self._hotp_counter)
                self._hotp_counter += 1
                return code
            except ImportError:
                logger.warning("pyotp 未安装，无法自动生成 HOTP 验证码")
            except Exception:
                logger.exception("HOTP 验证码生成失败")

        return None

    async def _handle_captcha(self, event: _Event) -> None:
        await self.on_event(event)

    @property
    def captcha_selectors(self) -> list[str]:
        """获取验证码检测选择器列表"""
        return list(self._CAPTCHA_SELECTORS)

    @property
    def otp_selectors(self) -> list[str]:
        """获取 OTP 输入框选择器列表"""
        return list(self._OTP_SELECTORS)


# ── 3. CrashWatchdog ─────────────────────────────────────────


class CrashWatchdog(BaseWatchdog):
    """浏览器崩溃恢复

    检测浏览器崩溃事件，自动重启浏览器并恢复到最近检查点。
    依赖 CheckpointManager（可选）进行状态恢复。
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        max_restart_attempts: int = 3,
        restart_delay: float = 2.0,
        checkpoint_manager: Any | None = None,
    ) -> None:
        self._bus = event_bus
        self._max_restart_attempts = max_restart_attempts
        self._restart_delay = restart_delay
        self._checkpoint_manager = checkpoint_manager
        self._handler_id: str | None = None
        self._crash_count: int = 0
        self._restart_count: int = 0
        self._last_crash_time: float | None = None

    @property
    def name(self) -> str:
        return "crash"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_crash,
            event_type=WatchdogEvent.CRASH_DETECTED,
        )
        logger.info("CrashWatchdog 已启动 (最大重启次数=%d)", self._max_restart_attempts)

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        logger.info("CrashWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        crash_reason = event.data.get("reason", "unknown")
        error_message = event.data.get("error_message", "")
        url = event.data.get("url", "")

        self._crash_count += 1
        self._last_crash_time = time.monotonic()

        logger.error(
            "CrashWatchdog: 检测到浏览器崩溃 (原因=%s, 错误=%s, URL=%s)",
            crash_reason, error_message[:200], url[:200],
        )

        # 检查重启次数限制
        if self._restart_count >= self._max_restart_attempts:
            logger.critical(
                "CrashWatchdog: 已达最大重启次数 (%d)，放弃恢复",
                self._max_restart_attempts,
            )
            return {
                "crash_detected": True,
                "recovered": False,
                "reason": f"已达最大重启次数 {self._max_restart_attempts}",
                "crash_reason": crash_reason,
            }

        # 尝试恢复
        recovered = await self._attempt_recovery(url)

        return {
            "crash_detected": True,
            "recovered": recovered,
            "crash_reason": crash_reason,
            "restart_count": self._restart_count,
        }

    async def _attempt_recovery(self, last_url: str = "") -> bool:
        """尝试恢复浏览器"""
        self._restart_count += 1
        logger.info("CrashWatchdog: 第 %d 次尝试恢复...", self._restart_count)

        await asyncio.sleep(self._restart_delay)

        # 如果有 CheckpointManager，尝试恢复到最近检查点
        if self._checkpoint_manager is not None:
            try:
                checkpoint = self._checkpoint_manager.get_latest()
                if checkpoint:
                    await self._bus.publish(_Event(
                        event_type="execution:checkpoint_restore",
                        source="crash_watchdog",
                        data={"checkpoint_id": checkpoint.get("id"), "url": last_url},
                    ))
                    logger.info("CrashWatchdog: 已恢复到检查点 %s", checkpoint.get("id"))
                    return True
            except Exception:
                logger.exception("CrashWatchdog: 检查点恢复失败")

        # 无 CheckpointManager 或恢复失败，尝试直接导航回原 URL
        if last_url:
            await self._bus.publish(_Event(
                event_type="execution:navigation",
                source="crash_watchdog",
                data={"url": last_url, "reason": "crash_recovery"},
            ))
            logger.info("CrashWatchdog: 已请求导航回 %s", last_url[:200])
            return True

        return False

    async def _handle_crash(self, event: _Event) -> None:
        await self.on_event(event)


# ── 4. SecurityWatchdog ──────────────────────────────────────


class SecurityWatchdog(BaseWatchdog):
    """域名安全守卫

    拦截导航到非白名单域名的请求，支持通配符模式匹配。
    配置 allowed_domains（白名单）和 prohibited_domains（黑名单）。
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        allowed_domains: list[str] | None = None,
        prohibited_domains: list[str] | None = None,
        mode: str = "whitelist",
    ) -> None:
        """
        Args:
            event_bus: 事件总线实例。
            allowed_domains: 白名单域名列表，支持通配符 (如 *.example.com)。
            prohibited_domains: 黑名单域名列表，支持通配符。
            mode: 安全模式，"whitelist" 或 "blacklist"。
                  whitelist — 仅允许白名单域名；
                  blacklist — 仅禁止黑名单域名。
        """
        self._bus = event_bus
        self._allowed_domains = allowed_domains or []
        self._prohibited_domains = prohibited_domains or []
        self._mode = mode
        self._handler_id: str | None = None
        self._violation_count: int = 0
        self._violation_history: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "security"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_navigation,
            event_type="execution:navigation",
        )
        logger.info(
            "SecurityWatchdog 已启动 (模式=%s, 白名单=%d, 黑名单=%d)",
            self._mode, len(self._allowed_domains), len(self._prohibited_domains),
        )

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        logger.info("SecurityWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        url = event.data.get("url", "")
        if not url:
            return None

        domain = self._extract_domain(url)
        if not domain:
            return None

        violation = self._check_violation(domain)

        if violation:
            self._violation_count += 1
            record = {
                "domain": domain,
                "url": url,
                "violation_type": violation,
                "timestamp": event.timestamp.isoformat(),
            }
            self._violation_history.append(record)

            logger.warning("SecurityWatchdog: 域名安全违规 (%s) — %s", violation, domain)

            await self._bus.publish(_Event(
                event_type=WatchdogEvent.SECURITY_VIOLATION,
                source="security_watchdog",
                data=record,
            ))

            return {
                "security_violation": True,
                "violation_type": violation,
                "domain": domain,
                "url": url,
                "blocked": True,
            }

        return None

    def _check_violation(self, domain: str) -> str | None:
        """检查域名是否违规

        Returns:
            违规类型字符串，无违规返回 None。
        """
        if self._mode == "whitelist":
            if self._allowed_domains and not self._match_domain(domain, self._allowed_domains):
                return "domain_not_in_whitelist"
        if self._mode == "blacklist" or self._prohibited_domains:
            if self._match_domain(domain, self._prohibited_domains):
                return "domain_in_blacklist"
        return None

    @staticmethod
    def _match_domain(domain: str, patterns: list[str]) -> bool:
        """检查域名是否匹配模式列表（支持通配符）"""
        for pattern in patterns:
            if fnmatch.fnmatch(domain, pattern):
                return True
            # 也匹配裸域名本身
            if domain == pattern:
                return True
        return False

    @staticmethod
    def _extract_domain(url: str) -> str:
        """从 URL 中提取域名"""
        # 简单提取，不依赖 urllib 以减少依赖
        match = re.match(r"https?://([^/:]+)", url)
        if match:
            return match.group(1)
        return ""

    async def _handle_navigation(self, event: _Event) -> None:
        await self.on_event(event)


# ── 5. NetworkWatchdog ───────────────────────────────────────


class NetworkWatchdog(BaseWatchdog):
    """网络异常检测

    检测请求失败和超时，跟踪失败计数，触发重试或降级策略。
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        max_failures: int = 5,
        timeout_threshold_ms: int = 30000,
        retry_on_failure: bool = True,
    ) -> None:
        self._bus = event_bus
        self._max_failures = max_failures
        self._timeout_threshold_ms = timeout_threshold_ms
        self._retry_on_failure = retry_on_failure
        self._handler_id: str | None = None
        self._failed_requests: dict[str, int] = {}  # domain -> count
        self._total_failures: int = 0
        self._degraded_domains: set[str] = set()

    @property
    def name(self) -> str:
        return "network"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_network_error,
            event_type=WatchdogEvent.NETWORK_ERROR,
        )
        logger.info("NetworkWatchdog 已启动 (最大失败次数=%d)", self._max_failures)

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        self._failed_requests.clear()
        self._degraded_domains.clear()
        logger.info("NetworkWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        url = event.data.get("url", "")
        error_type = event.data.get("error_type", "unknown")
        status_code = event.data.get("status_code")
        duration_ms = event.data.get("duration_ms", 0)

        domain = self._extract_domain(url)
        is_timeout = duration_ms > self._timeout_threshold_ms

        # 更新失败计数
        if domain:
            self._failed_requests[domain] = self._failed_requests.get(domain, 0) + 1
        self._total_failures += 1

        failure_count = self._failed_requests.get(domain, 0)

        # 判断是否需要降级
        degraded = failure_count >= self._max_failures
        if degraded and domain:
            self._degraded_domains.add(domain)

        log_level = logging.WARNING if degraded else logging.INFO
        logger.log(
            log_level,
            "NetworkWatchdog: 网络异常 (类型=%s, 状态码=%s, 域名=%s, 失败次数=%d, 超时=%s)",
            error_type, status_code, domain, failure_count, is_timeout,
        )

        result: dict[str, Any] = {
            "network_error": True,
            "error_type": error_type,
            "url": url,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "is_timeout": is_timeout,
            "failure_count": failure_count,
            "degraded": degraded,
        }

        # 触发重试
        if self._retry_on_failure and not degraded:
            result["retry_suggested"] = True

        return result

    @staticmethod
    def _extract_domain(url: str) -> str:
        """从 URL 中提取域名"""
        match = re.match(r"https?://([^/:]+)", url)
        if match:
            return match.group(1)
        return ""

    async def _handle_network_error(self, event: _Event) -> None:
        await self.on_event(event)

    def get_failure_stats(self) -> dict[str, int]:
        """获取各域名失败统计"""
        return dict(self._failed_requests)

    def is_domain_degraded(self, domain: str) -> bool:
        """检查域名是否处于降级状态"""
        return domain in self._degraded_domains


# ── 6. StorageWatchdog ───────────────────────────────────────


class StorageWatchdog(BaseWatchdog):
    """存储状态管理

    管理 Cookie / LocalStorage 的保存与恢复，在关键导航节点自动保存存储状态，
    支持存储状态持久化到文件。
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        auto_save: bool = True,
        persist_path: str | None = None,
        save_on_navigation: bool = True,
    ) -> None:
        self._bus = event_bus
        self._auto_save = auto_save
        self._persist_path = persist_path
        self._save_on_navigation = save_on_navigation
        self._nav_handler_id: str | None = None
        self._storage_handler_id: str | None = None
        self._snapshots: dict[str, dict[str, Any]] = {}  # url -> storage state
        self._save_count: int = 0
        self._restore_count: int = 0

    @property
    def name(self) -> str:
        return "storage"

    async def start(self) -> None:
        if self._save_on_navigation:
            self._nav_handler_id = self._bus.subscribe(
                self._handle_navigation,
                event_type="execution:navigation",
            )
        self._storage_handler_id = self._bus.subscribe(
            self._handle_storage_event,
            event_type=WatchdogEvent.STORAGE_CHANGED,
        )
        logger.info("StorageWatchdog 已启动 (自动保存=%s)", self._auto_save)

    async def stop(self) -> None:
        for hid in (self._nav_handler_id, self._storage_handler_id):
            if hid:
                self._bus.unsubscribe(hid)
        self._nav_handler_id = None
        self._storage_handler_id = None
        logger.info("StorageWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        return None  # StorageWatchdog 主要通过专用方法操作

    async def save_state(self, url: str, state: dict[str, Any]) -> None:
        """保存存储状态快照

        Args:
            url: 关联的 URL。
            state: 包含 cookies、localStorage 等的存储状态字典。
        """
        self._snapshots[url] = {
            "state": state,
            "saved_at": time.monotonic(),
        }
        self._save_count += 1
        logger.debug("StorageWatchdog: 已保存存储状态 (URL=%s)", url[:200])

        # 持久化到文件
        if self._persist_path:
            await self._persist_to_file()

        await self._bus.publish(_Event(
            event_type=WatchdogEvent.STORAGE_CHANGED,
            source="storage_watchdog",
            data={"action": "save", "url": url},
        ))

    async def restore_state(self, url: str) -> dict[str, Any] | None:
        """恢复存储状态

        Args:
            url: 需要恢复状态的 URL。

        Returns:
            存储状态字典，无快照时返回 None。
        """
        snapshot = self._snapshots.get(url)
        if snapshot is None:
            logger.warning("StorageWatchdog: 无存储快照 (URL=%s)", url[:200])
            return None

        self._restore_count += 1
        logger.info("StorageWatchdog: 已恢复存储状态 (URL=%s)", url[:200])

        await self._bus.publish(_Event(
            event_type=WatchdogEvent.STORAGE_CHANGED,
            source="storage_watchdog",
            data={"action": "restore", "url": url},
        ))

        return snapshot["state"]

    async def _persist_to_file(self) -> None:
        """将存储状态持久化到文件"""
        if not self._persist_path:
            return
        try:
            import json
            from pathlib import Path
            path = Path(self._persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            # 序列化快照（去除 saved_at 等非序列化字段）
            serializable = {}
            for url, snap in self._snapshots.items():
                serializable[url] = snap.get("state", {})
            path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("StorageWatchdog: 持久化存储状态失败")

    async def load_from_file(self) -> int:
        """从文件加载存储状态

        Returns:
            加载的快照数量。
        """
        if not self._persist_path:
            return 0
        try:
            import json
            from pathlib import Path
            path = Path(self._persist_path)
            if not path.exists():
                return 0
            data = json.loads(path.read_text(encoding="utf-8"))
            count = 0
            for url, state in data.items():
                self._snapshots[url] = {"state": state, "saved_at": time.monotonic()}
                count += 1
            logger.info("StorageWatchdog: 从文件加载了 %d 个存储快照", count)
            return count
        except Exception:
            logger.exception("StorageWatchdog: 加载存储状态文件失败")
            return 0

    async def _handle_navigation(self, event: _Event) -> None:
        """导航事件触发自动保存"""
        if not self._auto_save:
            return
        url = event.data.get("url", "")
        if url:
            # 通知外部需要保存当前存储状态
            await self._bus.publish(_Event(
                event_type=WatchdogEvent.STORAGE_CHANGED,
                source="storage_watchdog",
                data={"action": "auto_save_requested", "url": url},
            ))

    async def _handle_storage_event(self, event: _Event) -> None:
        """存储变更事件处理"""
        pass  # 主要用于记录日志，实际操作通过 save_state / restore_state

    def get_snapshot_urls(self) -> list[str]:
        """获取所有已保存快照的 URL 列表"""
        return list(self._snapshots.keys())


# ── 7. DownloadWatchdog ──────────────────────────────────────


@dataclass
class _DownloadEntry:
    """下载追踪条目"""
    download_id: str
    url: str
    filename: str = ""
    save_path: str = ""
    state: str = "started"  # started / in_progress / completed / failed / canceled
    progress: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None
    error: str = ""


class DownloadWatchdog(BaseWatchdog):
    """文件下载追踪

    跟踪下载进度，等待下载完成，记录下载路径。
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        download_dir: str = "./downloads",
        wait_timeout: float = 300.0,
    ) -> None:
        self._bus = event_bus
        self._download_dir = download_dir
        self._wait_timeout = wait_timeout
        self._handler_id: str | None = None
        self._downloads: dict[str, _DownloadEntry] = {}
        self._completed_downloads: list[_DownloadEntry] = []
        self._wait_events: dict[str, asyncio.Event] = {}

    @property
    def name(self) -> str:
        return "download"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_download,
            event_type=WatchdogEvent.DOWNLOAD_COMPLETE,
        )
        logger.info("DownloadWatchdog 已启动 (下载目录=%s)", self._download_dir)

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        # 清理等待事件
        for ev in self._wait_events.values():
            ev.set()
        self._wait_events.clear()
        logger.info("DownloadWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        download_id = event.data.get("download_id", "")
        state = event.data.get("state", "completed")
        save_path = event.data.get("save_path", "")
        filename = event.data.get("filename", "")
        error = event.data.get("error", "")

        entry = self._downloads.get(download_id)

        if entry is None:
            # 新下载条目
            entry = _DownloadEntry(
                download_id=download_id,
                url=event.data.get("url", ""),
                filename=filename,
                save_path=save_path,
                state=state,
            )
            self._downloads[download_id] = entry

        # 更新状态
        entry.state = state
        if save_path:
            entry.save_path = save_path
        if filename:
            entry.filename = filename
        if error:
            entry.error = error

        if state == "completed":
            entry.completed_at = time.monotonic()
            entry.progress = 1.0
            self._completed_downloads.append(entry)
            logger.info("DownloadWatchdog: 下载完成 (id=%s, 文件=%s)", download_id, filename)
        elif state == "failed":
            entry.completed_at = time.monotonic()
            logger.error("DownloadWatchdog: 下载失败 (id=%s, 错误=%s)", download_id, error)
        elif state == "in_progress":
            entry.progress = event.data.get("progress", entry.progress)

        # 通知等待者
        wait_event = self._wait_events.get(download_id)
        if wait_event and state in ("completed", "failed", "canceled"):
            wait_event.set()

        return {
            "download_tracked": True,
            "download_id": download_id,
            "state": state,
            "filename": entry.filename,
            "save_path": entry.save_path,
        }

    async def track_download(self, download_id: str, url: str = "", filename: str = "") -> None:
        """开始追踪一个下载

        Args:
            download_id: 下载唯一标识。
            url: 下载 URL。
            filename: 建议文件名。
        """
        entry = _DownloadEntry(
            download_id=download_id,
            url=url,
            filename=filename,
            state="started",
        )
        self._downloads[download_id] = entry
        self._wait_events[download_id] = asyncio.Event()
        logger.debug("DownloadWatchdog: 开始追踪下载 (id=%s)", download_id)

    async def wait_for_download(self, download_id: str, timeout: float | None = None) -> _DownloadEntry | None:
        """等待下载完成

        Args:
            download_id: 下载唯一标识。
            timeout: 等待超时秒数，None 使用默认值。

        Returns:
            下载条目，超时返回 None。
        """
        wait_event = self._wait_events.get(download_id)
        if wait_event is None:
            return self._downloads.get(download_id)

        timeout = timeout or self._wait_timeout
        try:
            await asyncio.wait_for(wait_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("DownloadWatchdog: 等待下载超时 (id=%s, 超时=%ss)", download_id, timeout)
            return None

        return self._downloads.get(download_id)

    async def _handle_download(self, event: _Event) -> None:
        await self.on_event(event)

    def get_download(self, download_id: str) -> _DownloadEntry | None:
        """获取下载条目"""
        return self._downloads.get(download_id)

    def list_downloads(self, state: str | None = None) -> list[_DownloadEntry]:
        """列出下载条目

        Args:
            state: 按状态过滤，None 表示全部。
        """
        if state:
            return [d for d in self._downloads.values() if d.state == state]
        return list(self._downloads.values())


# ── 8. DomWatchdog ────────────────────────────────────────────


class DomWatchdog(BaseWatchdog):
    """DOM 变更监控

    监控页面结构变化，当 DOM 发生显著变更时触发缓存失效。
    通过比较元素数量和结构哈希判断变更程度。
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        element_count_threshold: int = 50,
        structure_change_threshold: float = 0.3,
        check_interval: float = 5.0,
    ) -> None:
        """
        Args:
            event_bus: 事件总线实例。
            element_count_threshold: 元素数量变化阈值（绝对值）。
            structure_change_threshold: 结构哈希变化比例阈值 (0~1)。
            check_interval: 检查间隔秒数（用于外部定时触发场景）。
        """
        self._bus = event_bus
        self._element_count_threshold = element_count_threshold
        self._structure_change_threshold = structure_change_threshold
        self._check_interval = check_interval
        self._handler_id: str | None = None
        self._baseline: dict[str, Any] | None = None
        self._change_count: int = 0
        self._cache_invalidations: int = 0

    @property
    def name(self) -> str:
        return "dom"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_dom_event,
            event_type=WatchdogEvent.DOM_CHANGED,
        )
        logger.info("DomWatchdog 已启动 (元素阈值=%d, 结构阈值=%.1f%%)",
                     self._element_count_threshold, self._structure_change_threshold * 100)

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        self._baseline = None
        logger.info("DomWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        current_count = event.data.get("element_count", 0)
        current_hash = event.data.get("structure_hash", "")
        current_url = event.data.get("url", "")
        current_snapshot = {
            "element_count": current_count,
            "structure_hash": current_hash,
            "url": current_url,
        }

        # 首次建立基线
        if self._baseline is None:
            self._baseline = current_snapshot
            logger.debug("DomWatchdog: 已建立 DOM 基线 (元素=%d)", current_count)
            return None

        # 比较变更
        significant = self._detect_significant_change(current_snapshot)

        if significant:
            self._change_count += 1
            self._cache_invalidations += 1
            logger.info(
                "DomWatchdog: 检测到显著 DOM 变更 (URL=%s, 元素=%d→%d)",
                current_url[:100], self._baseline["element_count"], current_count,
            )

            # 更新基线
            self._baseline = current_snapshot

            return {
                "dom_changed": True,
                "significant": True,
                "cache_invalidation": True,
                "previous_count": self._baseline.get("element_count", 0),
                "current_count": current_count,
                "change_type": significant,
            }

        # 更新基线（即使不显著也跟踪）
        self._baseline = current_snapshot
        return None

    def _detect_significant_change(self, current: dict[str, Any]) -> str | None:
        """检测显著变更

        Returns:
            变更类型字符串，无显著变更返回 None。
        """
        if self._baseline is None:
            return None

        # 元素数量变化
        count_diff = abs(current["element_count"] - self._baseline["element_count"])
        if count_diff >= self._element_count_threshold:
            return "element_count_change"

        # 结构哈希变化
        if current["structure_hash"] and self._baseline["structure_hash"]:
            if current["structure_hash"] != self._baseline["structure_hash"]:
                # 简单哈希比较：不同即认为有变化
                # 更精细的比较可通过相似度算法实现
                baseline_count = self._baseline["element_count"] or 1
                change_ratio = count_diff / baseline_count
                if change_ratio >= self._structure_change_threshold:
                    return "structure_change"

        return None

    async def set_baseline(self, element_count: int, structure_hash: str, url: str = "") -> None:
        """手动设置 DOM 基线

        Args:
            element_count: 当前页面元素数量。
            structure_hash: 当前页面结构哈希。
            url: 关联 URL。
        """
        self._baseline = {
            "element_count": element_count,
            "structure_hash": structure_hash,
            "url": url,
        }
        logger.debug("DomWatchdog: 手动设置基线 (元素=%d)", element_count)

    async def _handle_dom_event(self, event: _Event) -> None:
        await self.on_event(event)

    @staticmethod
    def compute_structure_hash(html: str) -> str:
        """计算 DOM 结构哈希

        提取标签结构（去除文本内容和属性值），计算 SHA256 哈希。
        用于快速判断页面结构是否发生变化。

        Args:
            html: 页面 HTML 字符串。

        Returns:
            结构哈希十六进制字符串。
        """
        # 去除文本内容，只保留标签结构
        tags_only = re.sub(r">[^<]+<", "><", html)
        # 去除属性值
        tags_only = re.sub(r'="[^"]*"', '=""', tags_only)
        return hashlib.sha256(tags_only.encode("utf-8")).hexdigest()


# ── 9. VisualAnomalyWatchdog ─────────────────────────────────


class VisualAnomalyWatchdog(BaseWatchdog):
    """UI 样式异常检测

    检测：空图片占位符、元素堆叠（重叠 toast）、内容异常（NaN/乱码）、白屏错误。
    使用简单启发式规则，无需 AI 模型。
    """

    # 异常文本模式
    _ANOMALY_TEXT_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bNaN\b", re.IGNORECASE),
        re.compile(r"\bundefined\b"),
        re.compile(r"\bnull\b"),
        re.compile(r"[\ufffd]{2,}"),  # Unicode 替换字符（乱码）
        re.compile(r"[�]{2,}"),       # 乱码
    ]

    # 空图片占位符特征
    _BROKEN_IMAGE_SELECTORS: list[str] = [
        'img[src=""]',
        'img:not([src])',
        'img[src*="placeholder"]',
        'img[alt=""]',
    ]

    def __init__(
        self,
        event_bus: EventBus,
        *,
        white_screen_threshold: float = 0.95,
        max_overlapping_toasts: int = 3,
    ) -> None:
        """
        Args:
            event_bus: 事件总线实例。
            white_screen_threshold: 白屏判定阈值（空白像素占比 0~1）。
            max_overlapping_toasts: 最大允许重叠 toast 数量。
        """
        self._bus = event_bus
        self._white_screen_threshold = white_screen_threshold
        self._max_overlapping_toasts = max_overlapping_toasts
        self._handler_id: str | None = None
        self._anomaly_count: int = 0
        self._anomaly_history: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "visual_anomaly"

    async def start(self) -> None:
        self._handler_id = self._bus.subscribe(
            self._handle_visual_event,
            event_type=WatchdogEvent.VISUAL_ANOMALY,
        )
        logger.info("VisualAnomalyWatchdog 已启动")

    async def stop(self) -> None:
        if self._handler_id:
            self._bus.unsubscribe(self._handler_id)
            self._handler_id = None
        logger.info("VisualAnomalyWatchdog 已停止")

    async def on_event(self, event: _Event) -> Optional[dict]:
        anomaly_type = event.data.get("anomaly_type", "")
        details = event.data.get("details", {})
        url = event.data.get("url", "")

        self._anomaly_count += 1
        record = {
            "anomaly_type": anomaly_type,
            "details": details,
            "url": url,
            "timestamp": event.timestamp.isoformat(),
        }
        self._anomaly_history.append(record)

        logger.warning(
            "VisualAnomalyWatchdog: 检测到 UI 异常 (类型=%s, URL=%s)",
            anomaly_type, url[:200],
        )

        return {
            "visual_anomaly": True,
            "anomaly_type": anomaly_type,
            "details": details,
        }

    async def detect_anomalies(
        self,
        *,
        text_content: str = "",
        element_count: int = 0,
        visible_element_count: int = 0,
        image_elements: list[dict[str, Any]] | None = None,
        toast_elements: list[dict[str, Any]] | None = None,
        url: str = "",
    ) -> list[dict[str, Any]]:
        """主动检测页面异常

        Args:
            text_content: 页面可见文本内容。
            element_count: 页面总元素数。
            visible_element_count: 可见元素数。
            image_elements: 图片元素信息列表。
            toast_elements: Toast/通知元素信息列表。
            url: 当前页面 URL。

        Returns:
            检测到的异常列表。
        """
        anomalies: list[dict[str, Any]] = []

        # 1. 白屏检测
        if element_count > 0 and visible_element_count == 0:
            anomalies.append({
                "anomaly_type": "white_screen",
                "details": {"element_count": element_count, "visible_element_count": 0},
            })
        elif element_count > 10:
            visible_ratio = visible_element_count / element_count
            if visible_ratio < (1 - self._white_screen_threshold):
                anomalies.append({
                    "anomaly_type": "near_white_screen",
                    "details": {
                        "visible_ratio": round(visible_ratio, 3),
                        "element_count": element_count,
                        "visible_element_count": visible_element_count,
                    },
                })

        # 2. 内容异常检测
        text_anomalies = self._detect_text_anomalies(text_content)
        anomalies.extend(text_anomalies)

        # 3. 空图片占位符检测
        if image_elements:
            broken_images = self._detect_broken_images(image_elements)
            anomalies.extend(broken_images)

        # 4. 元素堆叠检测
        if toast_elements and len(toast_elements) > self._max_overlapping_toasts:
            anomalies.append({
                "anomaly_type": "element_stacking",
                "details": {
                    "toast_count": len(toast_elements),
                    "max_allowed": self._max_overlapping_toasts,
                },
            })

        # 发布异常事件
        for anomaly in anomalies:
            anomaly["url"] = url
            await self._bus.publish(_Event(
                event_type=WatchdogEvent.VISUAL_ANOMALY,
                source="visual_anomaly_watchdog",
                data=anomaly,
            ))

        return anomalies

    def _detect_text_anomalies(self, text: str) -> list[dict[str, Any]]:
        """检测文本内容异常"""
        anomalies: list[dict[str, Any]] = []
        if not text:
            return anomalies

        for pattern in self._ANOMALY_TEXT_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                anomalies.append({
                    "anomaly_type": "content_anomaly",
                    "details": {
                        "pattern": pattern.pattern,
                        "match_count": len(matches),
                        "sample": matches[:3],
                    },
                })

        return anomalies

    @staticmethod
    def _detect_broken_images(image_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """检测空图片占位符"""
        anomalies: list[dict[str, Any]] = []
        broken = []

        for img in image_elements:
            src = img.get("src", "")
            natural_width = img.get("natural_width", 0)
            natural_height = img.get("natural_height", 0)

            if not src or (natural_width == 0 and natural_height == 0 and src != ""):
                broken.append(img.get("selector", "unknown"))

        if broken:
            anomalies.append({
                "anomaly_type": "broken_images",
                "details": {"count": len(broken), "selectors": broken[:10]},
            })

        return anomalies

    async def _handle_visual_event(self, event: _Event) -> None:
        await self.on_event(event)


# ── WatchdogManager ───────────────────────────────────────────


class WatchdogManager:
    """Watchdog 管理器

    统一管理所有 Watchdog 的生命周期，提供注册、注销、启动、停止等操作。
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        """
        Args:
            event_bus: 事件总线实例。
            config: 全局配置字典，用于初始化各 Watchdog 的参数。
        """
        self._bus = event_bus
        self._config = config or {}
        self._watchdogs: dict[str, BaseWatchdog] = {}
        self._started: bool = False

    def register(self, watchdog: BaseWatchdog) -> None:
        """注册 Watchdog

        Args:
            watchdog: Watchdog 实例。

        Raises:
            ValueError: 同名 Watchdog 已注册。
        """
        if watchdog.name in self._watchdogs:
            raise ValueError(f"Watchdog '{watchdog.name}' 已注册，请先注销")
        self._watchdogs[watchdog.name] = watchdog
        logger.info("WatchdogManager: 已注册 %s", watchdog.name)

    def unregister(self, name: str) -> None:
        """注销 Watchdog

        Args:
            name: Watchdog 名称。

        Raises:
            KeyError: 指定名称的 Watchdog 不存在。
        """
        if name not in self._watchdogs:
            raise KeyError(f"Watchdog '{name}' 不存在")
        del self._watchdogs[name]
        logger.info("WatchdogManager: 已注销 %s", name)

    async def start_all(self) -> None:
        """启动所有已注册的 Watchdog"""
        if self._started:
            logger.warning("WatchdogManager: 已处于启动状态，跳过重复启动")
            return

        for wd in self._watchdogs.values():
            try:
                await wd.start()
            except Exception:
                logger.exception("WatchdogManager: 启动 %s 失败", wd.name)

        self._started = True
        logger.info("WatchdogManager: 所有 Watchdog 已启动 (共 %d 个)", len(self._watchdogs))

    async def stop_all(self) -> None:
        """停止所有已注册的 Watchdog"""
        if not self._started:
            return

        for wd in self._watchdogs.values():
            try:
                await wd.stop()
            except Exception:
                logger.exception("WatchdogManager: 停止 %s 失败", wd.name)

        self._started = False
        logger.info("WatchdogManager: 所有 Watchdog 已停止")

    def get_watchdog(self, name: str) -> BaseWatchdog | None:
        """获取指定名称的 Watchdog

        Args:
            name: Watchdog 名称。

        Returns:
            Watchdog 实例，不存在返回 None。
        """
        return self._watchdogs.get(name)

    def list_active(self) -> list[str]:
        """列出所有已注册的 Watchdog 名称"""
        return list(self._watchdogs.keys())

    def create_default_watchdogs(self) -> None:
        """根据配置创建默认的 9 个 Watchdog 并注册

        使用 self._config 中的参数初始化各 Watchdog。
        """
        watchdog_config = self._config.get("watchdog", {})

        # 1. PopupWatchdog
        popup_cfg = watchdog_config.get("popup", {})
        self.register(PopupWatchdog(
            self._bus,
            default_prompt_value=popup_cfg.get("default_prompt_value", ""),
        ))

        # 2. CaptchaWatchdog
        captcha_cfg = watchdog_config.get("captcha", {})
        self.register(CaptchaWatchdog(
            self._bus,
            totp_secret=captcha_cfg.get("totp_secret"),
            hotp_secret=captcha_cfg.get("hotp_secret"),
            hotp_counter=captcha_cfg.get("hotp_counter", 0),
        ))

        # 3. CrashWatchdog
        crash_cfg = watchdog_config.get("crash", {})
        self.register(CrashWatchdog(
            self._bus,
            max_restart_attempts=crash_cfg.get("max_restart_attempts", 3),
            restart_delay=crash_cfg.get("restart_delay", 2.0),
        ))

        # 4. SecurityWatchdog
        security_cfg = watchdog_config.get("security", {})
        self.register(SecurityWatchdog(
            self._bus,
            allowed_domains=security_cfg.get("allowed_domains"),
            prohibited_domains=security_cfg.get("prohibited_domains"),
            mode=security_cfg.get("mode", "whitelist"),
        ))

        # 5. NetworkWatchdog
        network_cfg = watchdog_config.get("network", {})
        self.register(NetworkWatchdog(
            self._bus,
            max_failures=network_cfg.get("max_failures", 5),
            timeout_threshold_ms=network_cfg.get("timeout_threshold_ms", 30000),
            retry_on_failure=network_cfg.get("retry_on_failure", True),
        ))

        # 6. StorageWatchdog
        storage_cfg = watchdog_config.get("storage", {})
        self.register(StorageWatchdog(
            self._bus,
            auto_save=storage_cfg.get("auto_save", True),
            persist_path=storage_cfg.get("persist_path"),
            save_on_navigation=storage_cfg.get("save_on_navigation", True),
        ))

        # 7. DownloadWatchdog
        download_cfg = watchdog_config.get("download", {})
        self.register(DownloadWatchdog(
            self._bus,
            download_dir=download_cfg.get("download_dir", "./downloads"),
            wait_timeout=download_cfg.get("wait_timeout", 300.0),
        ))

        # 8. DomWatchdog
        dom_cfg = watchdog_config.get("dom", {})
        self.register(DomWatchdog(
            self._bus,
            element_count_threshold=dom_cfg.get("element_count_threshold", 50),
            structure_change_threshold=dom_cfg.get("structure_change_threshold", 0.3),
            check_interval=dom_cfg.get("check_interval", 5.0),
        ))

        # 9. VisualAnomalyWatchdog
        visual_cfg = watchdog_config.get("visual_anomaly", {})
        self.register(VisualAnomalyWatchdog(
            self._bus,
            white_screen_threshold=visual_cfg.get("white_screen_threshold", 0.95),
            max_overlapping_toasts=visual_cfg.get("max_overlapping_toasts", 3),
        ))

        logger.info("WatchdogManager: 已创建 %d 个默认 Watchdog", len(self._watchdogs))
