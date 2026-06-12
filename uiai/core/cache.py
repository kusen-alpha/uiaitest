"""三层缓存系统 - 参考 Midscene.js 的三层缓存架构

PlanCache:  任务流程缓存，缓存完整的任务工作流
LocateCache: 元素定位缓存，缓存元素定位结果（特征 + 坐标）
FeatureCache: 元素视觉特征缓存，缓存元素视觉特征用于快速匹配
CacheManager: 统一缓存管理器，协调三层缓存的生命周期
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


def _hash_key(text: str) -> str:
    """对文本生成 SHA256 哈希摘要，用作缓存键"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry_to_dict(entry: CacheEntry) -> dict:
    """将 CacheEntry 序列化为可 JSON 化的字典"""
    d = asdict(entry)
    d["created_at"] = entry.created_at.isoformat()
    d["updated_at"] = entry.updated_at.isoformat()
    return d


def _entry_from_dict(d: dict) -> CacheEntry:
    """从字典反序列化 CacheEntry"""
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    d["updated_at"] = datetime.fromisoformat(d["updated_at"])
    return CacheEntry(**d)


# ────────────────────────────────────────────
# CacheEntry — 缓存条目
# ────────────────────────────────────────────

@dataclass
class CacheEntry:
    """缓存条目

    Attributes:
        key: 缓存键（任务描述哈希或元素描述）
        value: 缓存值
        created_at: 创建时间
        updated_at: 更新时间
        hit_count: 命中次数
        version_hash: 版本哈希，用于失效判断（页面结构哈希等）
    """
    key: str
    value: Any
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    hit_count: int = 0
    version_hash: Optional[str] = None


# ────────────────────────────────────────────
# PlanCache — 任务流程缓存
# ────────────────────────────────────────────

class PlanCache:
    """任务流程缓存

    缓存完整的任务工作流（YAML 可序列化的动作步骤列表）。
    - 键: 任务描述的哈希
    - 值: 动作步骤列表 (list[dict])
    - 失效条件: 页面结构哈希变化 或 流程修订
    """

    def __init__(self, max_entries: int = 1000, ttl_seconds: int = 86400) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._max_entries = max_entries
        self._ttl = timedelta(seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0

    def get(self, task_desc: str) -> Optional[list[dict]]:
        """获取任务流程缓存

        Args:
            task_desc: 任务描述文本

        Returns:
            缓存的工作流步骤列表，未命中或已过期返回 None
        """
        key = _hash_key(task_desc)
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if self._is_expired(entry):
            del self._store[key]
            self._misses += 1
            return None
        entry.hit_count += 1
        entry.updated_at = _now()
        self._hits += 1
        return entry.value

    def set(self, task_desc: str, workflow: list[dict], version_hash: str) -> None:
        """设置任务流程缓存

        Args:
            task_desc: 任务描述文本
            workflow: 工作流步骤列表
            version_hash: 页面结构版本哈希
        """
        key = _hash_key(task_desc)
        self._evict_if_full()
        now = _now()
        self._store[key] = CacheEntry(
            key=key,
            value=workflow,
            created_at=now,
            updated_at=now,
            version_hash=version_hash,
        )

    def invalidate(self, task_desc: str) -> None:
        """使指定任务的缓存失效"""
        key = _hash_key(task_desc)
        self._store.pop(key, None)

    def invalidate_by_hash(self, version_hash: str) -> None:
        """使所有与给定版本哈希匹配的缓存条目失效

        当页面结构发生变化时，所有关联旧版本哈希的流程缓存都将被清除。
        """
        keys_to_remove = [
            k for k, v in self._store.items()
            if v.version_hash == version_hash
        ]
        for k in keys_to_remove:
            del self._store[k]

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def _is_expired(self, entry: CacheEntry) -> bool:
        return _now() - entry.updated_at > self._ttl

    def _evict_if_full(self) -> None:
        """当缓存满时，按权重衰减策略淘汰（最久未使用 + 命中次数最低）"""
        if len(self._store) < self._max_entries:
            return
        # 按 (更新时间, 命中次数) 排序，淘汰最久未用且命中最低的
        worst_key = min(
            self._store,
            key=lambda k: (self._store[k].updated_at, self._store[k].hit_count),
        )
        del self._store[worst_key]

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def clear_expired(self) -> int:
        """清除所有过期条目，返回清除数量"""
        expired_keys = [k for k, v in self._store.items() if self._is_expired(v)]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {k: _entry_to_dict(v) for k, v in self._store.items()}

    def from_dict(self, data: dict) -> None:
        """从字典反序列化"""
        for k, v in data.items():
            self._store[k] = _entry_from_dict(v)


# ────────────────────────────────────────────
# LocateCache — 元素定位缓存
# ────────────────────────────────────────────

class LocateCache:
    """元素定位缓存

    缓存元素定位结果（特征 + 坐标）。
    - 键: 元素描述
    - 值: dict(css_selector, xpath, rect, feature_hash)
    - 失效条件: 元素位置/形态变化
    """

    def __init__(self, max_entries: int = 1000, ttl_seconds: int = 86400) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._max_entries = max_entries
        self._ttl = timedelta(seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0

    def get(self, description: str) -> Optional[dict]:
        """获取元素定位缓存

        Args:
            description: 元素描述文本

        Returns:
            缓存的定位信息字典，未命中或已过期返回 None
        """
        entry = self._store.get(description)
        if entry is None:
            self._misses += 1
            return None
        if self._is_expired(entry):
            del self._store[description]
            self._misses += 1
            return None
        entry.hit_count += 1
        entry.updated_at = _now()
        self._hits += 1
        return entry.value

    def set(self, description: str, location: dict, feature_hash: str) -> None:
        """设置元素定位缓存

        Args:
            description: 元素描述文本
            location: 定位信息 (css_selector, xpath, rect, feature_hash)
            feature_hash: 元素特征哈希，用于失效判断
        """
        self._evict_if_full()
        now = _now()
        self._store[description] = CacheEntry(
            key=description,
            value=location,
            created_at=now,
            updated_at=now,
            version_hash=feature_hash,
        )

    def invalidate(self, description: str) -> None:
        """使指定元素的定位缓存失效"""
        self._store.pop(description, None)

    def invalidate_by_hash(self, feature_hash: str) -> None:
        """使所有与给定特征哈希匹配的缓存条目失效"""
        keys_to_remove = [
            k for k, v in self._store.items()
            if v.version_hash == feature_hash
        ]
        for k in keys_to_remove:
            del self._store[k]

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def _is_expired(self, entry: CacheEntry) -> bool:
        return _now() - entry.updated_at > self._ttl

    def _evict_if_full(self) -> None:
        if len(self._store) < self._max_entries:
            return
        worst_key = min(
            self._store,
            key=lambda k: (self._store[k].updated_at, self._store[k].hit_count),
        )
        del self._store[worst_key]

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def clear_expired(self) -> int:
        expired_keys = [k for k, v in self._store.items() if self._is_expired(v)]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)

    def to_dict(self) -> dict:
        return {k: _entry_to_dict(v) for k, v in self._store.items()}

    def from_dict(self, data: dict) -> None:
        for k, v in data.items():
            self._store[k] = _entry_from_dict(v)


# ────────────────────────────────────────────
# FeatureCache — 元素视觉特征缓存
# ────────────────────────────────────────────

class FeatureCache:
    """元素视觉特征缓存

    缓存元素视觉特征用于快速匹配。
    - 键: 元素描述
    - 值: dict(feature_vector, bounding_box, screenshot_hash)
    - 失效条件: 视觉样式发生重大变化
    """

    def __init__(self, max_entries: int = 1000, ttl_seconds: int = 86400) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._max_entries = max_entries
        self._ttl = timedelta(seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0

    def get(self, description: str) -> Optional[dict]:
        """获取元素视觉特征缓存

        Args:
            description: 元素描述文本

        Returns:
            缓存的特征信息字典，未命中或已过期返回 None
        """
        entry = self._store.get(description)
        if entry is None:
            self._misses += 1
            return None
        if self._is_expired(entry):
            del self._store[description]
            self._misses += 1
            return None
        entry.hit_count += 1
        entry.updated_at = _now()
        self._hits += 1
        return entry.value

    def set(self, description: str, features: dict) -> None:
        """设置元素视觉特征缓存

        Args:
            description: 元素描述文本
            features: 特征信息 (feature_vector, bounding_box, screenshot_hash)
        """
        self._evict_if_full()
        now = _now()
        self._store[description] = CacheEntry(
            key=description,
            value=features,
            created_at=now,
            updated_at=now,
            version_hash=features.get("screenshot_hash"),
        )

    def invalidate(self, description: str) -> None:
        """使指定元素的视觉特征缓存失效"""
        self._store.pop(description, None)

    def match(self, description: str, current_features: dict, threshold: float = 0.8) -> bool:
        """判断当前特征是否与缓存特征匹配

        通过比较特征向量的哈希值和截图哈希来评估相似度。
        当特征向量哈希完全一致时直接返回 True；
        否则通过截图哈希相似度与阈值比较。

        Args:
            description: 元素描述文本
            current_features: 当前采集的特征字典
            threshold: 相似度阈值，默认 0.8

        Returns:
            是否匹配
        """
        cached = self.get(description)
        if cached is None:
            return False

        # 特征向量哈希完全一致 → 直接匹配
        if cached.get("feature_vector") == current_features.get("feature_vector"):
            return True

        # 截图哈希相似度比较
        cached_hash = cached.get("screenshot_hash", "")
        current_hash = current_features.get("screenshot_hash", "")
        if cached_hash and current_hash:
            similarity = self._hash_similarity(cached_hash, current_hash)
            return similarity >= threshold

        return False

    @staticmethod
    def _hash_similarity(hash_a: str, hash_b: str) -> float:
        """计算两个哈希字符串的相似度（基于汉明距离）

        将哈希视为位序列，计算相同位的比例作为相似度。
        """
        if len(hash_a) != len(hash_b) or not hash_a:
            return 0.0
        matching = sum(a == b for a, b in zip(hash_a, hash_b))
        return matching / len(hash_a)

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def _is_expired(self, entry: CacheEntry) -> bool:
        return _now() - entry.updated_at > self._ttl

    def _evict_if_full(self) -> None:
        if len(self._store) < self._max_entries:
            return
        worst_key = min(
            self._store,
            key=lambda k: (self._store[k].updated_at, self._store[k].hit_count),
        )
        del self._store[worst_key]

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def clear_expired(self) -> int:
        expired_keys = [k for k, v in self._store.items() if self._is_expired(v)]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)

    def to_dict(self) -> dict:
        return {k: _entry_to_dict(v) for k, v in self._store.items()}

    def from_dict(self, data: dict) -> None:
        for k, v in data.items():
            self._store[k] = _entry_from_dict(v)


# ────────────────────────────────────────────
# CacheManager — 统一缓存管理器
# ────────────────────────────────────────────

class CacheManager:
    """统一缓存管理器

    协调 PlanCache、LocateCache、FeatureCache 三层缓存的生命周期，
    提供异步访问接口、持久化、统计和清理功能。

    Attributes:
        plan_cache: 任务流程缓存
        locate_cache: 元素定位缓存
        feature_cache: 元素视觉特征缓存
    """

    _CACHE_FILENAME = "cache.json"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_entries: int = 1000,
        ttl_seconds: int = 86400,
    ) -> None:
        """初始化缓存管理器

        Args:
            cache_dir: 缓存持久化目录，默认为 .uiai_cache/
            max_entries: 每层缓存最大条目数
            ttl_seconds: 缓存过期时间（秒），默认 86400（24 小时）
        """
        self._cache_dir = Path(cache_dir) if cache_dir else Path(".uiai_cache")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

        self.plan_cache = PlanCache(max_entries=max_entries, ttl_seconds=ttl_seconds)
        self.locate_cache = LocateCache(max_entries=max_entries, ttl_seconds=ttl_seconds)
        self.feature_cache = FeatureCache(max_entries=max_entries, ttl_seconds=ttl_seconds)

    # ── Plan 缓存接口 ──────────────────────

    async def get_plan(self, task_desc: str) -> Optional[list[dict]]:
        """异步获取任务流程缓存"""
        return self.plan_cache.get(task_desc)

    async def set_plan(self, task_desc: str, workflow: list[dict], version_hash: str) -> None:
        """异步设置任务流程缓存"""
        self.plan_cache.set(task_desc, workflow, version_hash)

    async def check_plan_cache(self, task_desc: str, current_hash: str) -> Optional[list[dict]]:
        """带版本校验的任务流程缓存查询

        先获取缓存，再比对版本哈希。若版本不一致则自动失效并返回 None。

        Args:
            task_desc: 任务描述文本
            current_hash: 当前页面结构版本哈希

        Returns:
            缓存的工作流步骤列表，版本不匹配或未命中返回 None
        """
        key = _hash_key(task_desc)
        with self._lock:
            entry = self.plan_cache._store.get(key)
        if entry is None:
            return None
        # 版本哈希不匹配 → 失效
        if entry.version_hash != current_hash:
            self.plan_cache.invalidate(task_desc)
            logger.info("PlanCache 版本不匹配，已失效: task=%s", task_desc[:50])
            return None
        return self.plan_cache.get(task_desc)

    # ── Locate 缓存接口 ──────────────────────

    async def get_locate(self, description: str) -> Optional[dict]:
        """异步获取元素定位缓存"""
        return self.locate_cache.get(description)

    async def set_locate(self, description: str, location: dict, feature_hash: str) -> None:
        """异步设置元素定位缓存"""
        self.locate_cache.set(description, location, feature_hash)

    async def check_locate_cache(self, description: str) -> Optional[dict]:
        """快速定位缓存查询

        Args:
            description: 元素描述文本

        Returns:
            缓存的定位信息字典
        """
        return self.locate_cache.get(description)

    # ── Feature 缓存接口 ──────────────────────

    async def get_feature(self, description: str) -> Optional[dict]:
        """异步获取元素视觉特征缓存"""
        return self.feature_cache.get(description)

    async def set_feature(self, description: str, features: dict) -> None:
        """异步设置元素视觉特征缓存"""
        self.feature_cache.set(description, features)

    # ── 统计与维护 ──────────────────────

    def stats(self) -> dict:
        """获取缓存统计信息

        Returns:
            包含各层缓存命中率、条目数等统计信息的字典
        """
        return {
            "plan_cache": {
                "entries": self.plan_cache.size,
                "hit_rate": round(self.plan_cache.hit_rate, 4),
            },
            "locate_cache": {
                "entries": self.locate_cache.size,
                "hit_rate": round(self.locate_cache.hit_rate, 4),
            },
            "feature_cache": {
                "entries": self.feature_cache.size,
                "hit_rate": round(self.feature_cache.hit_rate, 4),
            },
            "total_entries": (
                self.plan_cache.size + self.locate_cache.size + self.feature_cache.size
            ),
        }

    def clear_all(self) -> None:
        """清除所有缓存"""
        self.plan_cache.clear()
        self.locate_cache.clear()
        self.feature_cache.clear()
        logger.info("所有缓存已清除")

    def clear_expired(self) -> None:
        """清除所有过期条目"""
        plan_removed = self.plan_cache.clear_expired()
        locate_removed = self.locate_cache.clear_expired()
        feature_removed = self.feature_cache.clear_expired()
        total = plan_removed + locate_removed + feature_removed
        if total > 0:
            logger.info("已清除 %d 条过期缓存 (plan=%d, locate=%d, feature=%d)",
                        total, plan_removed, locate_removed, feature_removed)

    # ── 持久化 ──────────────────────

    def save_to_disk(self) -> None:
        """将缓存持久化到磁盘（JSON 格式）"""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "saved_at": _now().isoformat(),
            "plan_cache": self.plan_cache.to_dict(),
            "locate_cache": self.locate_cache.to_dict(),
            "feature_cache": self.feature_cache.to_dict(),
        }
        cache_file = self._cache_dir / self._CACHE_FILENAME
        tmp_file = cache_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_file.replace(cache_file)
            logger.info("缓存已保存到 %s", cache_file)
        except OSError:
            logger.exception("缓存保存失败")
            if tmp_file.exists():
                tmp_file.unlink()

    def load_from_disk(self) -> None:
        """从磁盘加载缓存"""
        cache_file = self._cache_dir / self._CACHE_FILENAME
        if not cache_file.exists():
            logger.info("缓存文件不存在，跳过加载: %s", cache_file)
            return
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") != 1:
                logger.warning("缓存版本不兼容，跳过加载")
                return
            self.plan_cache.from_dict(data.get("plan_cache", {}))
            self.locate_cache.from_dict(data.get("locate_cache", {}))
            self.feature_cache.from_dict(data.get("feature_cache", {}))
            # 加载后立即清理过期条目
            self.clear_expired()
            logger.info("缓存已从 %s 加载", cache_file)
        except (json.JSONDecodeError, OSError, KeyError):
            logger.exception("缓存加载失败，将使用空缓存")
            self.clear_all()
