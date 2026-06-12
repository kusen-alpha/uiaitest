"""UIAI 框架架构重构模块综合单元测试

覆盖所有新模块：EventBus, PerceptionMode/RunTier, LoopDetector, CacheManager,
Watchdog, KnowledgeManager, SkillRegistry, CapabilityManager, CheckpointManager,
SensitiveDataProtector, FallbackLLM, IntentRouter, MessageCompactor, CodeRecorder,
ExecutorAgent, JudgeAgent, TestOrchestrator
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ────────────────────────────────────────────────────────────────
# 1. EventBus 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.eventbus import (
    AgentEvent,
    Event,
    EventBus,
    ExecutionEvent,
    Priority,
    WatchdogEvent,
    _HandlerEntry,
)


class TestEventBus:
    """EventBus 发布/订阅、优先级、过滤、错误隔离、历史"""

    def test_event_creation(self):
        e = Event(event_type="test", source="unit", data={"key": "val"})
        assert e.event_type == "test"
        assert e.source == "unit"
        assert e.data == {"key": "val"}
        assert e.event_id
        assert isinstance(e.timestamp, datetime)

    def test_subscribe_and_handler_count(self):
        bus = EventBus()
        hid = bus.subscribe(lambda e: None)
        assert bus.handler_count == 1
        assert isinstance(hid, str)

    def test_unsubscribe(self):
        bus = EventBus()
        hid = bus.subscribe(lambda e: None)
        assert bus.unsubscribe(hid) is True
        assert bus.handler_count == 0
        assert bus.unsubscribe("nonexistent") is False

    @pytest.mark.asyncio
    async def test_publish_sync_handler(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda e: received.append(e))
        await bus.publish(Event(event_type="t", source="s"))
        assert len(received) == 1
        assert received[0].event_type == "t"

    @pytest.mark.asyncio
    async def test_publish_async_handler(self):
        bus = EventBus()
        received = []

        async def handler(e):
            received.append(e)

        bus.subscribe(handler)
        await bus.publish(Event(event_type="t", source="s"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        bus = EventBus()
        order = []

        bus.subscribe(lambda e: order.append("low"), priority=Priority.LOW)
        bus.subscribe(lambda e: order.append("high"), priority=Priority.HIGH)
        bus.subscribe(lambda e: order.append("normal"), priority=Priority.NORMAL)

        await bus.publish(Event(event_type="t", source="s"))
        assert order == ["high", "normal", "low"]

    @pytest.mark.asyncio
    async def test_event_type_filter(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda e: received.append(e), event_type="target")
        bus.subscribe(lambda e: received.append(e), event_type="other")

        await bus.publish(Event(event_type="target", source="s"))
        assert len(received) == 1
        assert received[0].event_type == "target"

    @pytest.mark.asyncio
    async def test_source_filter(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda e: received.append(e), source="watchdog")
        bus.subscribe(lambda e: received.append(e))

        await bus.publish(Event(event_type="t", source="agent"))
        # 只有未过滤的处理器收到
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_error_isolation(self):
        """单个处理器异常不影响其他处理器"""
        bus = EventBus()
        results = []

        def bad_handler(e):
            raise RuntimeError("boom")

        bus.subscribe(bad_handler, priority=Priority.HIGH)
        bus.subscribe(lambda e: results.append("ok"), priority=Priority.LOW)

        await bus.publish(Event(event_type="t", source="s"))
        assert results == ["ok"]

    def test_history(self):
        bus = EventBus(history_size=5)
        for i in range(3):
            bus._history is not None and bus._history.append(
                Event(event_type=f"t{i}", source="s")
            )
        assert len(bus.history) == 3

    def test_clear_history(self):
        bus = EventBus(history_size=10)
        bus._history is not None and bus._history.append(Event(event_type="t", source="s"))
        bus.clear_history()
        assert len(bus.history) == 0

    def test_no_history_when_disabled(self):
        bus = EventBus()
        assert bus.history == []

    @pytest.mark.asyncio
    async def test_on_decorator(self):
        bus = EventBus()
        received = []

        @bus.on(event_type="test_event")
        def handler(e):
            received.append(e)

        await bus.publish(Event(event_type="test_event", source="s"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with EventBus() as bus:
            bus.subscribe(lambda e: None)
            bus._history is not None and bus._history.append(
                Event(event_type="t", source="s")
            )
        assert bus.handler_count == 0
        assert len(bus.history) == 0


# ────────────────────────────────────────────────────────────────
# 2. PerceptionMode / RunTier 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.platform import Platform, PerceptionMode as PlatformPerceptionMode, RunTier
from uiai.core.perception import PerceptionMode


class TestPerceptionModeAndRunTier:
    """枚举值与跨模块导入"""

    def test_perception_mode_values(self):
        assert PerceptionMode.A11Y_SNAPSHOT.value == "a11y_snapshot"
        assert PerceptionMode.DOM_SERIALIZE.value == "dom_serialize"
        assert PerceptionMode.VISUAL_SCREENSHOT.value == "visual_screenshot"
        assert PerceptionMode.HYBRID.value == "hybrid"

    def test_platform_perception_mode(self):
        assert PlatformPerceptionMode.A11Y_SNAPSHOT.value == "a11y_snapshot"
        assert PlatformPerceptionMode.HYBRID.value == "hybrid"

    def test_run_tier_values(self):
        assert RunTier.R1_SCRIPT.value == "r1_script"
        assert RunTier.R2_AGENT.value == "r2_agent"
        assert RunTier.R3_LOCAL_DEV.value == "r3_local_dev"

    def test_platform_values(self):
        assert Platform.WEB.value == "web"
        assert Platform.ANDROID.value == "android"
        assert Platform.IOS.value == "ios"


# ────────────────────────────────────────────────────────────────
# 3. LoopDetector 测试
# ────────────────────────────────────────────────────────────────

from uiai.agent.loop_detector import (
    ActionFingerprint,
    LoopDetector,
    LoopDetectorConfig,
    PageFingerprint,
)


class TestLoopDetector:
    """动作记录、循环检测、页面停滞、失败限制、渐进提示、归一化"""

    def test_record_action(self):
        ld = LoopDetector()
        ld.record_action("click", {"selector": "#btn"})
        assert len(ld._action_history) == 1

    def test_record_page_state(self):
        ld = LoopDetector()
        ld.record_page_state("https://example.com", 42, "page text")
        assert len(ld._page_history) == 1
        assert ld._page_history[0].url == "https://example.com"
        assert ld._page_history[0].element_count == 42

    def test_record_failure(self):
        ld = LoopDetector()
        for _ in range(5):
            ld.record_failure()
        assert ld._consecutive_failures == 5

    def test_check_action_loop_no_loop(self):
        ld = LoopDetector()
        ld.record_action("click", {"selector": "#btn1"})
        ld.record_action("click", {"selector": "#btn2"})
        assert ld.check_action_loop() is None

    def test_check_action_loop_detected(self):
        ld = LoopDetector(LoopDetectorConfig(action_repeat_thresholds=(3,)))
        for _ in range(3):
            ld.record_action("click", {"selector": "#btn"})
        result = ld.check_action_loop()
        assert result is not None
        assert "循环检测" in result

    def test_check_page_stall_no_stall(self):
        ld = LoopDetector()
        ld.record_page_state("https://a.com", 10, "text_a")
        ld.record_page_state("https://b.com", 10, "text_b")
        assert ld.check_page_stall() is None

    def test_check_page_stall_detected(self):
        ld = LoopDetector(LoopDetectorConfig(page_stall_threshold=3))
        for _ in range(3):
            ld.record_page_state("https://a.com", 10, "same text")
        result = ld.check_page_stall()
        assert result is not None
        assert "停滞" in result

    def test_check_failure_limit(self):
        ld = LoopDetector(LoopDetectorConfig(max_consecutive_failures=3))
        for _ in range(3):
            ld.record_failure()
        assert ld.check_failure_limit() is True

    def test_check_failure_limit_not_reached(self):
        ld = LoopDetector(LoopDetectorConfig(max_consecutive_failures=5))
        ld.record_failure()
        ld.record_failure()
        assert ld.check_failure_limit() is False

    def test_progressive_hints(self):
        ld = LoopDetector(LoopDetectorConfig(action_repeat_thresholds=(5, 8)))
        for _ in range(5):
            ld.record_action("click", {"selector": "#btn"})
        hints = ld.get_loop_hints()
        assert len(hints) == 1

        # 再增加到8次
        for _ in range(3):
            ld.record_action("click", {"selector": "#btn"})
        hints = ld.get_loop_hints()
        assert len(hints) == 1  # 第二个阈值

        # 已触发过的不再重复
        hints = ld.get_loop_hints()
        assert len(hints) == 0

    def test_normalize_action_sorts_keywords(self):
        ld = LoopDetector()
        n1 = ld.normalize_action("search", {"query": "hello world"})
        n2 = ld.normalize_action("search", {"query": "world hello"})
        assert n1 == n2

    def test_normalize_action_ignores_index(self):
        ld = LoopDetector()
        n1 = ld.normalize_action("click", {"index": 0, "selector": "#btn"})
        n2 = ld.normalize_action("click", {"index": 5, "selector": "#btn"})
        assert n1 == n2

    def test_reset(self):
        ld = LoopDetector()
        ld.record_action("click", {"selector": "#btn"})
        ld.record_page_state("url", 10, "text")
        ld.record_failure()
        ld.reset()
        assert len(ld._action_history) == 0
        assert len(ld._page_history) == 0
        assert ld._consecutive_failures == 0


# ────────────────────────────────────────────────────────────────
# 4. CacheManager 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.cache import CacheEntry, CacheManager, FeatureCache, LocateCache, PlanCache


class TestPlanCache:
    def test_set_and_get(self):
        pc = PlanCache()
        pc.set("task1", [{"step": 1}], "v1")
        result = pc.get("task1")
        assert result is not None
        assert len(result) == 1

    def test_get_miss(self):
        pc = PlanCache()
        assert pc.get("nonexistent") is None

    def test_invalidate(self):
        pc = PlanCache()
        pc.set("task1", [{"step": 1}], "v1")
        pc.invalidate("task1")
        assert pc.get("task1") is None

    def test_invalidate_by_hash(self):
        pc = PlanCache()
        pc.set("task1", [{"step": 1}], "v1")
        pc.set("task2", [{"step": 2}], "v1")
        pc.set("task3", [{"step": 3}], "v2")
        pc.invalidate_by_hash("v1")
        assert pc.get("task1") is None
        assert pc.get("task2") is None
        assert pc.get("task3") is not None

    def test_hit_rate(self):
        pc = PlanCache()
        pc.set("task1", [{"step": 1}], "v1")
        pc.get("task1")  # hit
        pc.get("nonexistent")  # miss
        assert pc.hit_rate == 0.5

    def test_ttl_expiry(self):
        pc = PlanCache(ttl_seconds=0)
        pc.set("task1", [{"step": 1}], "v1")
        time.sleep(0.01)
        assert pc.get("task1") is None

    def test_eviction(self):
        pc = PlanCache(max_entries=2)
        pc.set("task1", [1], "v1")
        pc.set("task2", [2], "v1")
        pc.set("task3", [3], "v1")  # 应淘汰一个
        assert pc.size <= 2

    def test_serialization(self):
        pc = PlanCache()
        pc.set("task1", [{"step": 1}], "v1")
        d = pc.to_dict()
        pc2 = PlanCache()
        pc2.from_dict(d)
        assert pc2.get("task1") is not None


class TestLocateCache:
    def test_set_and_get(self):
        lc = LocateCache()
        lc.set("登录按钮", {"css_selector": "#login", "xpath": "//button"}, "fh1")
        result = lc.get("登录按钮")
        assert result is not None
        assert result["css_selector"] == "#login"

    def test_invalidate(self):
        lc = LocateCache()
        lc.set("btn", {"css": "#b"}, "fh")
        lc.invalidate("btn")
        assert lc.get("btn") is None


class TestFeatureCache:
    def test_set_and_get(self):
        fc = FeatureCache()
        fc.set("搜索框", {"feature_vector": "abc", "screenshot_hash": "h1"})
        result = fc.get("搜索框")
        assert result is not None

    def test_match_exact(self):
        fc = FeatureCache()
        fc.set("搜索框", {"feature_vector": "abc", "screenshot_hash": "h1"})
        assert fc.match("搜索框", {"feature_vector": "abc", "screenshot_hash": "h1"}) is True

    def test_match_no_cache(self):
        fc = FeatureCache()
        assert fc.match("不存在", {"feature_vector": "abc"}) is False


class TestCacheManager:
    def test_stats(self):
        cm = CacheManager()
        cm.plan_cache.set("task", [1], "v1")
        stats = cm.stats()
        assert stats["plan_cache"]["entries"] == 1
        assert stats["total_entries"] == 1

    def test_clear_all(self):
        cm = CacheManager()
        cm.plan_cache.set("task", [1], "v1")
        cm.locate_cache.set("btn", {"css": "#b"}, "fh")
        cm.clear_all()
        assert cm.stats()["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_check_plan_cache_version_mismatch(self):
        cm = CacheManager()
        cm.plan_cache.set("task", [{"step": 1}], "v1")
        result = await cm.check_plan_cache("task", "v2")
        assert result is None  # 版本不匹配，自动失效

    @pytest.mark.asyncio
    async def test_check_plan_cache_version_match(self):
        cm = CacheManager()
        cm.plan_cache.set("task", [{"step": 1}], "v1")
        result = await cm.check_plan_cache("task", "v1")
        assert result is not None

    def test_disk_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cm1 = CacheManager(cache_dir=tmpdir)
            cm1.plan_cache.set("task", [{"step": 1}], "v1")
            cm1.save_to_disk()

            cm2 = CacheManager(cache_dir=tmpdir)
            cm2.load_from_disk()
            result = cm2.plan_cache.get("task")
            assert result is not None


# ────────────────────────────────────────────────────────────────
# 5. Watchdog 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.watchdog import (
    BaseWatchdog,
    CaptchaWatchdog,
    CrashWatchdog,
    DomWatchdog,
    DownloadWatchdog,
    NetworkWatchdog,
    PopupWatchdog,
    SecurityWatchdog,
    StorageWatchdog,
    VisualAnomalyWatchdog,
    WatchdogManager,
)


class TestWatchdogs:
    """9个Watchdog创建与事件处理"""

    def _make_bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_popup_watchdog(self):
        bus = self._make_bus()
        wd = PopupWatchdog(bus)
        await wd.start()
        event = Event(
            event_type=WatchdogEvent.POPUP_DETECTED,
            source="test",
            data={"dialog_type": "alert", "message": "Hello"},
        )
        result = await wd.on_event(event)
        assert result is not None
        assert result["popup_handled"] is True
        await wd.stop()

    @pytest.mark.asyncio
    async def test_captcha_watchdog_no_otp(self):
        bus = self._make_bus()
        wd = CaptchaWatchdog(bus)
        await wd.start()
        event = Event(
            event_type=WatchdogEvent.CAPTCHA_DETECTED,
            source="test",
            data={"captcha_type": "image", "element_info": {}},
        )
        result = await wd.on_event(event)
        assert result is not None
        assert result["captcha_detected"] is True
        assert result["auto_solved"] is False
        await wd.stop()

    @pytest.mark.asyncio
    async def test_crash_watchdog(self):
        bus = self._make_bus()
        wd = CrashWatchdog(bus, max_restart_attempts=1, restart_delay=0)
        await wd.start()
        event = Event(
            event_type=WatchdogEvent.CRASH_DETECTED,
            source="test",
            data={"reason": "oom", "error_message": "out of memory", "url": "https://example.com"},
        )
        result = await wd.on_event(event)
        assert result is not None
        assert result["crash_detected"] is True
        await wd.stop()

    @pytest.mark.asyncio
    async def test_security_watchdog_whitelist(self):
        bus = self._make_bus()
        wd = SecurityWatchdog(bus, allowed_domains=["example.com"], mode="whitelist")
        await wd.start()
        event = Event(
            event_type="execution:navigation",
            source="test",
            data={"url": "https://evil.com/page"},
        )
        result = await wd.on_event(event)
        assert result is not None
        assert result["security_violation"] is True
        await wd.stop()

    @pytest.mark.asyncio
    async def test_network_watchdog(self):
        bus = self._make_bus()
        wd = NetworkWatchdog(bus, max_failures=3)
        await wd.start()
        event = Event(
            event_type=WatchdogEvent.NETWORK_ERROR,
            source="test",
            data={"url": "https://api.example.com", "error_type": "timeout", "duration_ms": 35000},
        )
        result = await wd.on_event(event)
        assert result is not None
        assert result["network_error"] is True
        assert result["is_timeout"] is True
        await wd.stop()

    @pytest.mark.asyncio
    async def test_storage_watchdog(self):
        bus = self._make_bus()
        wd = StorageWatchdog(bus)
        await wd.start()
        await wd.save_state("https://example.com", {"cookies": [{"name": "sid", "value": "abc"}]})
        state = await wd.restore_state("https://example.com")
        assert state is not None
        assert "cookies" in state
        await wd.stop()

    @pytest.mark.asyncio
    async def test_download_watchdog(self):
        bus = self._make_bus()
        wd = DownloadWatchdog(bus)
        await wd.start()
        await wd.track_download("dl1", url="https://example.com/file.zip", filename="file.zip")
        event = Event(
            event_type=WatchdogEvent.DOWNLOAD_COMPLETE,
            source="test",
            data={"download_id": "dl1", "state": "completed", "save_path": "/tmp/file.zip"},
        )
        result = await wd.on_event(event)
        assert result is not None
        assert result["download_tracked"] is True
        await wd.stop()

    @pytest.mark.asyncio
    async def test_dom_watchdog(self):
        bus = self._make_bus()
        wd = DomWatchdog(bus, element_count_threshold=10)
        await wd.start()
        # 首次建立基线
        event1 = Event(
            event_type=WatchdogEvent.DOM_CHANGED,
            source="test",
            data={"element_count": 50, "structure_hash": "hash1", "url": "https://example.com"},
        )
        await wd.on_event(event1)
        # 显著变化
        event2 = Event(
            event_type=WatchdogEvent.DOM_CHANGED,
            source="test",
            data={"element_count": 80, "structure_hash": "hash2", "url": "https://example.com"},
        )
        result = await wd.on_event(event2)
        assert result is not None
        assert result["dom_changed"] is True
        await wd.stop()

    @pytest.mark.asyncio
    async def test_visual_anomaly_watchdog(self):
        bus = self._make_bus()
        wd = VisualAnomalyWatchdog(bus)
        await wd.start()
        event = Event(
            event_type=WatchdogEvent.VISUAL_ANOMALY,
            source="test",
            data={"anomaly_type": "white_screen", "details": {}, "url": "https://example.com"},
        )
        result = await wd.on_event(event)
        assert result is not None
        assert result["visual_anomaly"] is True
        await wd.stop()

    @pytest.mark.asyncio
    async def test_visual_anomaly_detect_method(self):
        bus = self._make_bus()
        wd = VisualAnomalyWatchdog(bus)
        anomalies = await wd.detect_anomalies(
            text_content="Error: NaN undefined null",
            element_count=100,
            visible_element_count=5,
        )
        assert len(anomalies) > 0


class TestWatchdogManager:
    """WatchdogManager 生命周期"""

    def _make_bus(self):
        return EventBus()

    def test_register_and_list(self):
        bus = self._make_bus()
        mgr = WatchdogManager(bus)
        mgr.register(PopupWatchdog(bus))
        assert "popup" in mgr.list_active()

    def test_register_duplicate_raises(self):
        bus = self._make_bus()
        mgr = WatchdogManager(bus)
        mgr.register(PopupWatchdog(bus))
        with pytest.raises(ValueError):
            mgr.register(PopupWatchdog(bus))

    def test_unregister(self):
        bus = self._make_bus()
        mgr = WatchdogManager(bus)
        mgr.register(PopupWatchdog(bus))
        mgr.unregister("popup")
        assert "popup" not in mgr.list_active()

    def test_unregister_nonexistent_raises(self):
        bus = self._make_bus()
        mgr = WatchdogManager(bus)
        with pytest.raises(KeyError):
            mgr.unregister("nonexistent")

    @pytest.mark.asyncio
    async def test_start_all_and_stop_all(self):
        bus = self._make_bus()
        mgr = WatchdogManager(bus)
        mgr.register(PopupWatchdog(bus))
        mgr.register(CaptchaWatchdog(bus))
        await mgr.start_all()
        assert mgr._started is True
        await mgr.stop_all()
        assert mgr._started is False

    @pytest.mark.asyncio
    async def test_create_default_watchdogs(self):
        bus = self._make_bus()
        mgr = WatchdogManager(bus)
        mgr.create_default_watchdogs()
        assert len(mgr.list_active()) == 9


# ────────────────────────────────────────────────────────────────
# 6. KnowledgeManager 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.knowledge import KnowledgeEntry, KnowledgeLevel, KnowledgeManager


class TestKnowledgeManager:
    @pytest.mark.asyncio
    async def test_add_requirement(self):
        km = KnowledgeManager()
        entry = await km.add_requirement("ecommerce", "购物车限制", "最多99件", ["购物车"])
        assert entry.level == KnowledgeLevel.REQUIREMENT
        assert entry.domain == "ecommerce"

    @pytest.mark.asyncio
    async def test_add_product(self):
        km = KnowledgeManager()
        entry = await km.add_product("finance", "转账规则", "单笔限额5万")
        assert entry.level == KnowledgeLevel.PRODUCT

    @pytest.mark.asyncio
    async def test_add_experience(self):
        km = KnowledgeManager()
        entry = await km.add_experience("ecommerce", "登录经验", "需要验证码")
        assert entry.level == KnowledgeLevel.EXPERIENCE
        assert entry.source == "agent_learned"

    @pytest.mark.asyncio
    async def test_search(self):
        km = KnowledgeManager()
        await km.add_requirement("ecommerce", "购物车限制", "最多99件商品", ["购物车"])
        await km.add_requirement("finance", "转账规则", "单笔限额5万", ["转账"])
        results = await km.search("购物车")
        assert len(results) >= 1
        assert "购物车" in results[0].title

    @pytest.mark.asyncio
    async def test_search_with_level_filter(self):
        km = KnowledgeManager()
        await km.add_requirement("ecommerce", "购物车", "最多99件")
        await km.add_experience("ecommerce", "购物车经验", "需要验证码")
        results = await km.search("购物车", level=KnowledgeLevel.REQUIREMENT)
        assert all(r.level == KnowledgeLevel.REQUIREMENT for r in results)

    @pytest.mark.asyncio
    async def test_get_relevant(self):
        km = KnowledgeManager()
        await km.add_requirement("ecommerce", "购物车限制", "最多99件", ["购物车"])
        results = await km.get_relevant("测试购物车功能")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_decay_weights(self):
        km = KnowledgeManager()
        entry = await km.add_requirement("ecommerce", "购物车", "最多99件")
        assert entry.weight == 1.0
        await km.decay_weights(decay_factor=0.5)
        assert entry.weight == 0.5

    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        km = KnowledgeManager()
        entry = await km.add_requirement("ecommerce", "购物车", "最多99件")
        entry.weight = 0.05
        removed = await km.cleanup_expired(min_weight=0.1)
        assert removed == 1

    @pytest.mark.asyncio
    async def test_build_context(self):
        km = KnowledgeManager()
        await km.add_requirement("ecommerce", "购物车限制", "最多99件", ["购物车"])
        ctx = await km.build_context("测试购物车")
        assert "相关知识" in ctx

    @pytest.mark.asyncio
    async def test_build_context_empty(self):
        km = KnowledgeManager()
        ctx = await km.build_context("测试购物车")
        assert ctx == ""

    def test_stats(self):
        km = KnowledgeManager()
        asyncio.run(km.add_requirement("ecommerce", "购物车", "最多99件"))
        stats = km.stats()
        assert stats["total_entries"] == 1

    def test_disk_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            km1 = KnowledgeManager(knowledge_dir=tmpdir)
            asyncio.run(km1.add_requirement("ecommerce", "购物车", "最多99件"))
            km1.save_to_disk()

            km2 = KnowledgeManager(knowledge_dir=tmpdir)
            km2.load_from_disk()
            stats = km2.stats()
            assert stats["total_entries"] == 1

    @pytest.mark.asyncio
    async def test_update_entry(self):
        km = KnowledgeManager()
        entry = await km.add_requirement("ecommerce", "购物车", "最多99件")
        await km.update(entry.id, content="最多100件", weight=0.8)
        assert entry.content == "最多100件"
        assert entry.weight == 0.8

    @pytest.mark.asyncio
    async def test_remove_entry(self):
        km = KnowledgeManager()
        entry = await km.add_requirement("ecommerce", "购物车", "最多99件")
        await km.remove(entry.id)
        stats = km.stats()
        assert stats["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_eviction_on_max_entries(self):
        km = KnowledgeManager(max_entries=2)
        await km.add_requirement("d1", "t1", "c1")
        await km.add_requirement("d2", "t2", "c2")
        # 第三条应触发淘汰
        await km.add_requirement("d3", "t3", "c3")
        assert km.stats()["total_entries"] <= 2


# ────────────────────────────────────────────────────────────────
# 7. SkillRegistry 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.skill import InputPrimitive, Skill, SkillRegistry


class TestSkillRegistry:
    def test_register_and_get(self):
        sr = SkillRegistry()
        skill = Skill(
            name="login",
            description="登录操作",
            primitives=[InputPrimitive.CLICK, InputPrimitive.FILL],
            steps=[{"action_type": "fill", "params": {}}],
        )
        sr.register(skill)
        assert sr.get("login") is not None
        assert sr.get("login").description == "登录操作"

    def test_register_duplicate_raises(self):
        sr = SkillRegistry()
        skill = Skill(name="s1", description="d", primitives=[], steps=[])
        sr.register(skill)
        with pytest.raises(ValueError):
            sr.register(skill)

    def test_unregister(self):
        sr = SkillRegistry()
        skill = Skill(name="s1", description="d", primitives=[], steps=[])
        sr.register(skill)
        sr.unregister("s1")
        assert sr.get("s1") is None

    def test_unregister_nonexistent_raises(self):
        sr = SkillRegistry()
        with pytest.raises(KeyError):
            sr.unregister("nope")

    def test_search(self):
        sr = SkillRegistry()
        sr.register(Skill(name="login", description="用户登录", primitives=[], steps=[]))
        sr.register(Skill(name="logout", description="用户登出", primitives=[], steps=[]))
        results = sr.search("login")
        assert len(results) == 1

    def test_list_skills(self):
        sr = SkillRegistry()
        sr.register(Skill(name="s1", description="d1", primitives=[], steps=[]))
        sr.register(Skill(name="s2", description="d2", primitives=[], steps=[]))
        assert len(sr.list_skills()) == 2

    def test_list_skills_platform_filter(self):
        sr = SkillRegistry()
        sr.register(Skill(name="s1", description="d1", primitives=[], steps=[], platform=Platform.WEB))
        sr.register(Skill(name="s2", description="d2", primitives=[], steps=[]))
        web_skills = sr.list_skills(platform=Platform.WEB)
        assert len(web_skills) == 2  # s1 明确 WEB, s2 无平台限制也匹配

    def test_get_skills_for_task(self):
        sr = SkillRegistry()
        sr.register(Skill(name="click_element", description="点击页面元素", primitives=[], steps=[]))
        sr.register(Skill(name="navigate", description="导航到URL", primitives=[], steps=[]))
        results = sr.get_skills_for_task("click_element")
        assert len(results) >= 1

    def test_register_defaults(self):
        sr = SkillRegistry()
        sr.register_defaults()
        assert sr.get("navigate") is not None
        assert sr.get("click_element") is not None
        assert sr.get("fill_form") is not None
        assert len(sr.list_skills()) == 10


# ────────────────────────────────────────────────────────────────
# 8. CapabilityManager 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.capability import Capability, CapabilityConfig, CapabilityManager


class TestCapabilityManager:
    def test_default_all_enabled(self):
        cm = CapabilityManager()
        for cap in Capability:
            assert cm.is_enabled(cap) is True

    def test_enable_disable(self):
        cm = CapabilityManager()
        cm.disable(Capability.AI_AGENT)
        assert cm.is_enabled(Capability.AI_AGENT) is False
        cm.enable(Capability.AI_AGENT)
        assert cm.is_enabled(Capability.AI_AGENT) is True

    def test_restrict_action(self):
        cm = CapabilityManager()
        cm.restrict_action(Capability.ELEMENT_INTERACTION, "double_click")
        assert cm.is_action_allowed(Capability.ELEMENT_INTERACTION, "click") is True
        assert cm.is_action_allowed(Capability.ELEMENT_INTERACTION, "double_click") is False

    def test_disabled_capability_blocks_action(self):
        cm = CapabilityManager()
        cm.disable(Capability.FILE_OPERATION)
        assert cm.is_action_allowed(Capability.FILE_OPERATION, "download") is False

    def test_get_enabled_disabled(self):
        cm = CapabilityManager()
        cm.disable(Capability.DISTRIBUTED)
        enabled = cm.get_enabled_capabilities()
        disabled = cm.get_disabled_capabilities()
        assert Capability.DISTRIBUTED not in enabled
        assert Capability.DISTRIBUTED in disabled

    def test_preset_full(self):
        cm = CapabilityManager()
        config = cm.create_preset("full")
        assert len(config.enabled_capabilities) == len(Capability)

    def test_preset_safe(self):
        cm = CapabilityManager()
        config = cm.create_preset("safe")
        assert Capability.AI_AGENT not in config.enabled_capabilities
        assert Capability.BROWSER_CONTROL in config.enabled_capabilities

    def test_preset_readonly(self):
        cm = CapabilityManager()
        config = cm.create_preset("readonly")
        assert Capability.VISUAL_PERCEPTION in config.enabled_capabilities
        assert Capability.BROWSER_CONTROL not in config.enabled_capabilities

    def test_preset_unknown_raises(self):
        cm = CapabilityManager()
        with pytest.raises(ValueError):
            cm.create_preset("nonexistent")


# ────────────────────────────────────────────────────────────────
# 9. CheckpointManager 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.checkpoint import Checkpoint, CheckpointManager


class TestCheckpointManager:
    def _make_mock_executor(self):
        executor = AsyncMock()
        executor.get_url = AsyncMock(return_value="https://example.com")
        executor.get_title = AsyncMock(return_value="Example")
        executor.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
        executor.navigate = AsyncMock()
        executor.context = None
        return executor

    @pytest.mark.asyncio
    async def test_save(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        cp = await mgr.save(step_index=1, metadata={"reason": "test"})
        assert cp.url == "https://example.com"
        assert cp.step_index == 1

    @pytest.mark.asyncio
    async def test_save_and_list(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        await mgr.save(step_index=1)
        await mgr.save(step_index=2)
        assert len(mgr.list_checkpoints()) == 2

    @pytest.mark.asyncio
    async def test_get_latest(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        await mgr.save(step_index=1)
        cp2 = await mgr.save(step_index=2)
        latest = mgr.get_latest()
        assert latest.step_index == 2

    @pytest.mark.asyncio
    async def test_get_latest_empty(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        assert mgr.get_latest() is None

    @pytest.mark.asyncio
    async def test_get_checkpoint(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        cp = await mgr.save(step_index=1)
        found = mgr.get_checkpoint(cp.id)
        assert found is not None
        assert found.id == cp.id

    @pytest.mark.asyncio
    async def test_restore(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        cp = await mgr.save(step_index=1)
        result = await mgr.restore(cp.id)
        assert result is True
        executor.navigate.assert_called()

    @pytest.mark.asyncio
    async def test_restore_nonexistent(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        result = await mgr.restore("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_max_checkpoints_eviction(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor, max_checkpoints=2)
        await mgr.save(step_index=1)
        await mgr.save(step_index=2)
        await mgr.save(step_index=3)
        assert len(mgr.list_checkpoints()) == 2
        assert mgr.list_checkpoints()[0].step_index == 2

    @pytest.mark.asyncio
    async def test_auto_checkpoint(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        # 首次不触发
        result = await mgr.auto_checkpoint(step_index=0, interval=5)
        assert result is None
        # 间隔不够
        result = await mgr.auto_checkpoint(step_index=3, interval=5)
        assert result is None
        # 间隔达到
        result = await mgr.auto_checkpoint(step_index=5, interval=5)
        assert result is not None

    @pytest.mark.asyncio
    async def test_clear(self):
        executor = self._make_mock_executor()
        mgr = CheckpointManager(executor)
        await mgr.save(step_index=1)
        mgr.clear()
        assert len(mgr.list_checkpoints()) == 0


# ────────────────────────────────────────────────────────────────
# 10. SensitiveDataProtector 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.security import SensitiveDataConfig, SensitiveDataProtector


class TestSensitiveDataProtector:
    def test_mask_dict(self):
        p = SensitiveDataProtector()
        data = {"username": "admin", "password": "secret123"}
        masked = p.mask_dict(data)
        assert masked["username"] == "admin"
        assert masked["password"] == "***"

    def test_mask_dict_nested(self):
        p = SensitiveDataProtector()
        data = {"user": {"name": "admin", "token": "abc123"}}
        masked = p.mask_dict(data)
        assert masked["user"]["name"] == "admin"
        assert masked["user"]["token"] == "***"

    def test_mask_dict_with_list(self):
        p = SensitiveDataProtector()
        data = {"items": [{"api_key": "k1", "name": "n1"}]}
        masked = p.mask_dict(data)
        assert masked["items"][0]["api_key"] == "***"
        assert masked["items"][0]["name"] == "n1"

    def test_mask_text(self):
        p = SensitiveDataProtector()
        text = "password=secret123&token=xyz"
        masked = p.mask_text(text)
        assert "secret123" not in masked
        assert "xyz" not in masked
        assert "***" in masked

    def test_is_sensitive_key(self):
        p = SensitiveDataProtector()
        assert p.is_sensitive_key("password") is True
        assert p.is_sensitive_key("api_key") is True
        assert p.is_sensitive_key("username") is False

    def test_is_sensitive_key_substring_match(self):
        p = SensitiveDataProtector()
        assert p.is_sensitive_key("user_password") is True
        assert p.is_sensitive_key("my_token_value") is True

    def test_add_remove_sensitive_key(self):
        p = SensitiveDataProtector()
        p.add_sensitive_key("custom_field")
        assert p.is_sensitive_key("custom_field") is True
        p.remove_sensitive_key("custom_field")
        assert p.is_sensitive_key("custom_field") is False

    def test_unmask_dict(self):
        p = SensitiveDataProtector()
        original = {"username": "admin", "password": "secret123"}
        masked = p.mask_dict(original)
        unmasked = p.unmask_dict(masked, original)
        assert unmasked["password"] == "secret123"

    def test_custom_mask_char(self):
        p = SensitiveDataProtector(SensitiveDataConfig(mask_char="[REDACTED]"))
        data = {"password": "secret"}
        masked = p.mask_dict(data)
        assert masked["password"] == "[REDACTED]"


# ────────────────────────────────────────────────────────────────
# 11. FallbackLLM 测试
# ────────────────────────────────────────────────────────────────

from uiai.core.security import FallbackLLM


class TestFallbackLLM:
    def _make_mock_client(self, chat_return="ok", chat_side_effect=None):
        client = AsyncMock()
        if chat_side_effect:
            client.chat = AsyncMock(side_effect=chat_side_effect)
        else:
            client.chat = AsyncMock(return_value=chat_return)
        client.chat_with_images = AsyncMock(return_value=chat_return)
        return client

    @pytest.mark.asyncio
    async def test_primary_succeeds(self):
        primary = self._make_mock_client(chat_return="primary_ok")
        fallback = self._make_mock_client(chat_return="fallback_ok")
        llm = FallbackLLM(primary, fallback)
        result = await llm.chat([{"role": "user", "content": "hi"}])
        assert result == "primary_ok"
        fallback.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_on_recoverable_error(self):
        primary = self._make_mock_client(
            chat_side_effect=Exception("rate limit exceeded")
        )
        fallback = self._make_mock_client(chat_return="fallback_ok")
        llm = FallbackLLM(primary, fallback, max_retries=1)
        result = await llm.chat([{"role": "user", "content": "hi"}])
        assert result == "fallback_ok"

    @pytest.mark.asyncio
    async def test_fallback_on_unrecoverable_error(self):
        primary = self._make_mock_client(
            chat_side_effect=Exception("401 unauthorized")
        )
        fallback = self._make_mock_client(chat_return="fallback_ok")
        llm = FallbackLLM(primary, fallback, max_retries=2)
        result = await llm.chat([{"role": "user", "content": "hi"}])
        assert result == "fallback_ok"
        # 不可恢复错误应直接降级，不重试
        assert primary.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_both_fail_raises(self):
        primary = self._make_mock_client(
            chat_side_effect=Exception("rate limit")
        )
        fallback = self._make_mock_client(
            chat_side_effect=Exception("connection error")
        )
        llm = FallbackLLM(primary, fallback, max_retries=1)
        with pytest.raises(Exception):
            await llm.chat([{"role": "user", "content": "hi"}])

    def test_is_recoverable(self):
        assert FallbackLLM._is_recoverable(Exception("rate limit")) is True
        assert FallbackLLM._is_recoverable(Exception("429 too many")) is True
        assert FallbackLLM._is_recoverable(Exception("timeout")) is True
        assert FallbackLLM._is_recoverable(Exception("503 service unavailable")) is True

    def test_is_not_recoverable(self):
        assert FallbackLLM._is_recoverable(Exception("401 unauthorized")) is False
        assert FallbackLLM._is_recoverable(Exception("403 forbidden")) is False
        assert FallbackLLM._is_recoverable(Exception("invalid api key")) is False

    @pytest.mark.asyncio
    async def test_chat_with_images_fallback(self):
        primary = AsyncMock()
        primary.chat_with_images = AsyncMock(side_effect=Exception("timeout"))
        fallback = AsyncMock()
        fallback.chat_with_images = AsyncMock(return_value="vl_ok")
        llm = FallbackLLM(primary, fallback, max_retries=1)
        result = await llm.chat_with_images(
            [{"role": "user", "content": "hi"}], [b"img"]
        )
        assert result == "vl_ok"


# ────────────────────────────────────────────────────────────────
# 12. IntentRouter 测试
# ────────────────────────────────────────────────────────────────

from uiai.agent.intent_router import IntentRouter, IntentType, ModelConfig


class TestIntentRouter:
    def test_register_model(self):
        router = IntentRouter()
        config = ModelConfig(
            model_id="test-model",
            provider="test",
            capabilities=frozenset({IntentType.PLAN}),
            priority=10,
        )
        router.register_model(config)
        assert len(router.list_models()) == 1

    def test_route(self):
        router = IntentRouter()
        router.register_model(ModelConfig(
            model_id="planner", provider="test",
            capabilities=frozenset({IntentType.PLAN}), priority=10,
        ))
        result = router.route(IntentType.PLAN)
        assert result.model_id == "planner"

    def test_route_no_model_raises(self):
        router = IntentRouter()
        with pytest.raises(ValueError):
            router.route(IntentType.LOCATE)

    def test_route_with_vl_preference(self):
        router = IntentRouter()
        router.register_model(ModelConfig(
            model_id="llm", provider="test",
            capabilities=frozenset({IntentType.LOCATE}), priority=5, is_vl=False,
        ))
        router.register_model(ModelConfig(
            model_id="vl", provider="test",
            capabilities=frozenset({IntentType.LOCATE}), priority=10, is_vl=True,
        ))
        result = router.route(IntentType.LOCATE, prefer_vl=True)
        assert result.model_id == "vl"

    def test_route_with_cheapest(self):
        router = IntentRouter()
        router.register_model(ModelConfig(
            model_id="expensive", provider="test",
            capabilities=frozenset({IntentType.EXTRACT}), priority=5, cost_per_1k=0.01,
        ))
        router.register_model(ModelConfig(
            model_id="cheap", provider="test",
            capabilities=frozenset({IntentType.EXTRACT}), priority=10, cost_per_1k=0.001,
        ))
        result = router.route(IntentType.EXTRACT, prefer_cheapest=True)
        assert result.model_id == "cheap"

    def test_route_with_fallback(self):
        router = IntentRouter()
        router.register_model(ModelConfig(
            model_id="primary", provider="test",
            capabilities=frozenset({IntentType.PLAN}), priority=10,
        ))
        router.register_model(ModelConfig(
            model_id="fallback", provider="test",
            capabilities=frozenset({IntentType.PLAN}), priority=20,
        ))
        models = router.route_with_fallback(IntentType.PLAN)
        assert len(models) == 2
        assert models[0].model_id == "primary"

    def test_set_default_models(self):
        router = IntentRouter()
        router.set_default_models()
        assert len(router.list_models()) == 3
        # LOCATE 应路由到 VL 模型
        result = router.route(IntentType.LOCATE, prefer_vl=True)
        assert result.is_vl is True


# ────────────────────────────────────────────────────────────────
# 13. MessageCompactor 测试
# ────────────────────────────────────────────────────────────────

from uiai.agent.message_compactor import CompactionConfig, CompactionStrategy, MessageCompactor


class TestMessageCompactor:
    def _make_messages(self, count: int) -> list[dict]:
        msgs = [{"role": "system", "content": "You are a helper."}]
        for i in range(count):
            msgs.append({"role": "user", "content": f"Message {i}"})
            msgs.append({"role": "assistant", "content": f"Reply {i}"})
        return msgs

    def test_should_compact_by_count(self):
        compactor = MessageCompactor(CompactionConfig(max_messages=5))
        msgs = self._make_messages(5)
        assert compactor.should_compact(msgs) is True

    def test_should_not_compact(self):
        compactor = MessageCompactor(CompactionConfig(max_messages=100, max_tokens=100000))
        msgs = self._make_messages(2)
        assert compactor.should_compact(msgs) is False

    def test_sliding_window(self):
        compactor = MessageCompactor(CompactionConfig(
            max_messages=5,
            strategy=CompactionStrategy.SLIDING_WINDOW,
            keep_recent=2,
        ))
        msgs = self._make_messages(10)
        result = compactor.compact(msgs)
        # 系统消息 + 最近2条
        system_msgs = [m for m in result if m["role"] == "system"]
        non_system = [m for m in result if m["role"] != "system"]
        assert len(system_msgs) == 1
        assert len(non_system) == 2

    def test_truncate(self):
        compactor = MessageCompactor(CompactionConfig(
            max_messages=5,
            strategy=CompactionStrategy.TRUNCATE,
            keep_recent=2,
        ))
        msgs = self._make_messages(10)
        result = compactor.compact(msgs)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1

    def test_estimate_tokens(self):
        compactor = MessageCompactor()
        msgs = [{"role": "user", "content": "Hello world"}]
        tokens = compactor.estimate_tokens(msgs)
        assert tokens > 0

    def test_compact_preserves_system_messages(self):
        compactor = MessageCompactor(CompactionConfig(
            max_messages=3,
            strategy=CompactionStrategy.SLIDING_WINDOW,
            keep_recent=1,
        ))
        msgs = [
            {"role": "system", "content": "System 1"},
            {"role": "system", "content": "System 2"},
            {"role": "user", "content": "User 1"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "User 2"},
        ]
        result = compactor.compact(msgs)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 2

    def test_summarize_without_llm_falls_back(self):
        compactor = MessageCompactor(CompactionConfig(
            max_messages=3,
            strategy=CompactionStrategy.SUMMARIZE,
            keep_recent=1,
        ))
        msgs = self._make_messages(5)
        result = compactor.compact(msgs)
        # 无LLM客户端时回退到滑动窗口
        assert len(result) < len(msgs)

    def test_multimodal_message_token_estimate(self):
        compactor = MessageCompactor()
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            }
        ]
        tokens = compactor.estimate_tokens(msgs)
        assert tokens > 0


# ────────────────────────────────────────────────────────────────
# 14. CodeRecorder 测试
# ────────────────────────────────────────────────────────────────

from uiai.agent.code_recorder import CodeAction, CodeRecorder
from uiai.core.locator import Locator, LocatorType


class TestCodeRecorder:
    def test_record_action(self):
        rec = CodeRecorder()
        loc = Locator.by_role("button", name="Submit")
        rec.record_action("click", loc, {})
        assert len(rec.actions) == 1
        assert rec.actions[0].action_type == "click"

    def test_record_navigation(self):
        rec = CodeRecorder()
        rec.record_navigation("https://example.com")
        assert len(rec.actions) == 1
        assert rec.actions[0].action_type == "navigate"
        assert "example.com" in rec.actions[0].action_code

    def test_record_action_visual_locator(self):
        rec = CodeRecorder()
        loc = Locator(LocatorType.IMAGE, "btn.png", description="图片按钮")
        rec.record_action("click", loc, {})
        assert rec.actions[0].action_code == ""
        assert "视觉模式" in rec.actions[0].comment

    def test_generate_code(self):
        rec = CodeRecorder()
        rec.record_navigation("https://example.com")
        loc = Locator.by_role("button", name="Submit")
        rec.record_action("click", loc, {})
        code = rec.generate_code()
        assert "async_playwright" in code
        assert "example.com" in code
        assert "get_by_role" in code

    def test_generate_step_code(self):
        rec = CodeRecorder()
        rec.record_navigation("https://example.com")
        steps = rec.generate_step_code()
        assert len(steps) > 0

    def test_locator_to_code_role(self):
        rec = CodeRecorder()
        loc = Locator.by_role("button", name="Login")
        code = rec._locator_to_code(loc)
        assert 'page.get_by_role("button", name="Login")' == code

    def test_locator_to_code_css(self):
        rec = CodeRecorder()
        loc = Locator.by_css("#submit-btn")
        code = rec._locator_to_code(loc)
        assert 'page.locator("#submit-btn")' == code

    def test_locator_to_code_test_id(self):
        rec = CodeRecorder()
        loc = Locator.by_test_id("login-btn")
        code = rec._locator_to_code(loc)
        assert 'page.get_by_test_id("login-btn")' == code

    def test_locator_to_code_text(self):
        rec = CodeRecorder()
        loc = Locator.by_text("Hello")
        code = rec._locator_to_code(loc)
        assert 'page.get_by_text("Hello")' == code

    def test_locator_to_code_xpath(self):
        rec = CodeRecorder()
        loc = Locator.by_xpath("//button[@id='btn']")
        code = rec._locator_to_code(loc)
        assert 'page.locator("xpath=//button[@id=\'btn\']")' == code

    def test_record_fill_action(self):
        rec = CodeRecorder()
        loc = Locator.by_css("#input")
        rec.record_action("fill", loc, {"value": "hello"})
        assert 'fill("hello")' in rec.actions[0].action_code

    def test_record_type_action(self):
        rec = CodeRecorder()
        loc = Locator.by_css("#input")
        rec.record_action("type", loc, {"text": "world"})
        assert "world" in rec.actions[0].action_code

    def test_record_assertion(self):
        rec = CodeRecorder()
        loc = Locator.by_role("button", name="Submit")
        rec.record_assertion("visible", loc, "")
        assert "is_visible" in rec.actions[0].action_code

    def test_record_comment(self):
        rec = CodeRecorder()
        rec.record_comment("This is a comment")
        assert rec.actions[0].action_type == "comment"

    def test_record_wait(self):
        rec = CodeRecorder()
        rec.record_wait("network idle", timeout=5000)
        assert rec.actions[0].action_type == "wait"

    def test_clear(self):
        rec = CodeRecorder()
        rec.record_navigation("https://example.com")
        rec.clear()
        assert len(rec.actions) == 0

    def test_save_to_file(self):
        rec = CodeRecorder()
        rec.record_navigation("https://example.com")
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_output.py")
            rec.save_to_file(filepath)
            assert Path(filepath).exists()
            content = Path(filepath).read_text(encoding="utf-8")
            assert "example.com" in content


# ────────────────────────────────────────────────────────────────
# 15. ExecutorAgent 数据模型测试
# ────────────────────────────────────────────────────────────────

from uiai.agent.executor import (
    ActionModel,
    ActionResult,
    AgentHistory,
    ExecutorOutput,
    FlashMode,
    StepResult,
)


class TestExecutorAgentModels:
    def test_flash_mode_enum(self):
        assert FlashMode.STANDARD.value == "standard"
        assert FlashMode.FLASH.value == "flash"

    def test_action_model(self):
        am = ActionModel(
            action_type="click",
            params={"selector": "#btn"},
            description="Click button",
        )
        assert am.action_type == "click"
        assert am.params["selector"] == "#btn"

    def test_executor_output(self):
        eo = ExecutorOutput(
            thinking="I need to click",
            next_goal="Click submit",
            action=[ActionModel(action_type="click", params={"selector": "#btn"}, description="click")],
            is_done=False,
        )
        assert eo.thinking == "I need to click"
        assert len(eo.action) == 1
        assert eo.is_done is False

    def test_executor_output_defaults(self):
        eo = ExecutorOutput()
        assert eo.thinking is None
        assert eo.action == []
        assert eo.is_done is False

    def test_action_result(self):
        ar = ActionResult(is_done=False, success=True, extracted_content="text")
        assert ar.success is True
        assert ar.extracted_content == "text"

    def test_step_result(self):
        sr = StepResult(step_number=1)
        assert sr.step_number == 1
        assert sr.action_results == []

    def test_agent_history(self):
        history = AgentHistory()
        step = StepResult(
            step_number=1,
            agent_output=ExecutorOutput(is_done=True),
            action_results=[ActionResult(is_done=True, success=True)],
        )
        history.add_step(step)
        assert history.number_of_steps() == 1
        assert history.is_successful() is True

    def test_agent_history_errors(self):
        history = AgentHistory()
        step = StepResult(
            step_number=1,
            agent_output=ExecutorOutput(),
            action_results=[ActionResult(is_done=False, success=False, error="fail")],
        )
        history.add_step(step)
        assert len(history.errors()) == 1

    def test_agent_history_total_duration(self):
        history = AgentHistory()
        history.add_step(StepResult(step_number=1, duration_seconds=1.5))
        history.add_step(StepResult(step_number=2, duration_seconds=2.5))
        duration = history.total_duration_seconds()
        assert duration >= 0

    def test_agent_history_mark_done(self):
        history = AgentHistory()
        history.mark_done()
        assert history._end_time is not None


# ────────────────────────────────────────────────────────────────
# 16. JudgeAgent 数据模型测试
# ────────────────────────────────────────────────────────────────

from uiai.agent.judge import JudgementResult


class TestJudgeAgentModels:
    def test_judgement_result_defaults(self):
        jr = JudgementResult()
        assert jr.reasoning is None
        assert jr.verdict is False
        assert jr.failure_reason is None
        assert jr.impossible_task is False
        assert jr.reached_captcha is False

    def test_judgement_result_success(self):
        jr = JudgementResult(
            reasoning="Task completed successfully",
            verdict=True,
        )
        assert jr.verdict is True
        assert jr.failure_reason is None

    def test_judgement_result_failure(self):
        jr = JudgementResult(
            reasoning="Task failed due to captcha",
            verdict=False,
            failure_reason="Captcha blocked execution",
            reached_captcha=True,
        )
        assert jr.verdict is False
        assert jr.reached_captcha is True

    def test_judgement_result_impossible(self):
        jr = JudgementResult(
            reasoning="Website does not have this feature",
            verdict=False,
            failure_reason="Feature not found",
            impossible_task=True,
        )
        assert jr.impossible_task is True


# ────────────────────────────────────────────────────────────────
# 17. TestOrchestrator 测试
# ────────────────────────────────────────────────────────────────

from uiai.agent.base import AgentOutput, AgentRole, AgentState, BaseAgent
from uiai.orchestrator.agent_registry import AgentRegistry
from uiai.orchestrator.orchestrator import TestOrchestrator


class TestAgentRegistry:
    def test_register_and_get(self):
        registry = AgentRegistry()
        agent = MagicMock(spec=BaseAgent)
        agent.name = "TestAgent"
        agent.role = AgentRole.PLANNER
        registry.register(agent)
        assert registry.get("TestAgent") is not None

    def test_get_by_role(self):
        registry = AgentRegistry()
        agent1 = MagicMock(spec=BaseAgent)
        agent1.name = "Planner1"
        agent1.role = AgentRole.PLANNER
        agent2 = MagicMock(spec=BaseAgent)
        agent2.name = "Executor1"
        agent2.role = AgentRole.EXECUTOR
        registry.register(agent1)
        registry.register(agent2)
        planners = registry.get_by_role(AgentRole.PLANNER)
        assert len(planners) == 1

    def test_get_first_by_role(self):
        registry = AgentRegistry()
        agent = MagicMock(spec=BaseAgent)
        agent.name = "Planner1"
        agent.role = AgentRole.PLANNER
        registry.register(agent)
        result = registry.get_first_by_role(AgentRole.PLANNER)
        assert result is not None

    def test_get_first_by_role_none(self):
        registry = AgentRegistry()
        assert registry.get_first_by_role(AgentRole.HEALER) is None

    def test_unregister(self):
        registry = AgentRegistry()
        agent = MagicMock(spec=BaseAgent)
        agent.name = "TestAgent"
        agent.role = AgentRole.PLANNER
        registry.register(agent)
        registry.unregister("TestAgent")
        assert registry.get("TestAgent") is None

    def test_list_all(self):
        registry = AgentRegistry()
        a1 = MagicMock(spec=BaseAgent)
        a1.name = "A1"
        a1.role = AgentRole.PLANNER
        a2 = MagicMock(spec=BaseAgent)
        a2.name = "A2"
        a2.role = AgentRole.EXECUTOR
        registry.register(a1)
        registry.register(a2)
        assert len(registry.list_all()) == 2

    def test_len(self):
        registry = AgentRegistry()
        assert len(registry) == 0


class TestTestOrchestrator:
    """TestOrchestrator 初始化与Agent注册"""

    def test_initialization(self):
        orch = TestOrchestrator()
        assert orch.event_bus is not None
        assert orch.agent_registry is not None
        assert orch._cache_manager is not None
        assert orch._watchdog_manager is not None
        assert orch._knowledge_manager is not None
        assert orch._skill_registry is not None
        assert orch._capability_manager is not None
        assert orch._sensitive_protector is not None
        assert orch._loop_detector is not None

    def test_default_skills_registered(self):
        orch = TestOrchestrator()
        assert orch._skill_registry.get("navigate") is not None

    def test_capability_control(self):
        orch = TestOrchestrator()
        orch.enable_capability(Capability.AI_AGENT)
        assert orch._capability_manager.is_enabled(Capability.AI_AGENT) is True
        orch.disable_capability(Capability.AI_AGENT)
        assert orch._capability_manager.is_enabled(Capability.AI_AGENT) is False

    def test_apply_preset(self):
        orch = TestOrchestrator()
        orch.apply_preset("safe")
        assert orch._capability_manager.is_enabled(Capability.VISUAL_PERCEPTION) is True
        assert orch._capability_manager.is_enabled(Capability.AI_AGENT) is False

    def test_register_agent(self):
        orch = TestOrchestrator()
        agent = MagicMock(spec=BaseAgent)
        agent.name = "MockAgent"
        agent.role = AgentRole.PLANNER
        orch.register_agent(agent)
        assert orch.agent_registry.get("MockAgent") is not None

    def test_audit_log(self):
        orch = TestOrchestrator()
        orch._log_audit("test_action", {"key": "value"})
        assert len(orch._audit_log) == 1
        assert orch._audit_log[0]["action"] == "test_action"

    def test_intent_router_initialized(self):
        orch = TestOrchestrator()
        assert orch._intent_router is not None
        assert len(orch._intent_router.list_models()) == 3

    def test_message_compactor_initialized(self):
        orch = TestOrchestrator()
        assert orch._message_compactor is not None
