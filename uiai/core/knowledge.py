"""知识管理系统 - 三级知识体系与业务 RAG 集成

提供需求级、产品级、经验级三层知识管理，支持知识条目的增删改查、
关键词/标签搜索、权重衰减、过期清理、上下文构建和磁盘持久化。
同时支持从外部 RAG 服务导入知识以及从 YAML/JSON 文件同步业务规则。

知识目录结构::

    .uiai_knowledge/
      ├── requirements/   # 需求级知识
      ├── products/       # 产品级知识
      └── experiences/    # 经验级知识
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    """生成唯一标识符"""
    return uuid.uuid4().hex[:16]


def _content_hash(content: str) -> str:
    """对内容生成 SHA256 哈希摘要，用于版本校验"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────
# KnowledgeLevel — 知识级别枚举
# ────────────────────────────────────────────


class KnowledgeLevel(str, Enum):
    """知识级别

    REQUIREMENT: 需求级 — 来自需求文档、用户故事等
    PRODUCT:     产品级 — 来自产品文档、设计规范等
    EXPERIENCE:  经验级 — 来自测试执行中的经验积累
    """

    REQUIREMENT = "requirement"
    PRODUCT = "product"
    EXPERIENCE = "experience"


# ────────────────────────────────────────────
# KnowledgeEntry — 知识条目
# ────────────────────────────────────────────


@dataclass
class KnowledgeEntry:
    """知识条目

    Attributes:
        id: 唯一标识符
        level: 知识级别
        domain: 业务领域（如 "ecommerce"、"finance"）
        title: 简短描述
        content: 完整知识内容
        tags: 搜索标签
        created_at: 创建时间
        updated_at: 更新时间
        hit_count: 被使用次数
        weight: 重要性权重（随时间衰减）
        source: 知识来源（如 "manual"、"agent_learned"、"rag_import"）
        version_hash: 内容版本哈希，用于失效判断
    """

    id: str
    level: KnowledgeLevel
    domain: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    hit_count: int = 0
    weight: float = 1.0
    source: Optional[str] = None
    version_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if self.version_hash is None:
            self.version_hash = _content_hash(self.content)


def _entry_to_dict(entry: KnowledgeEntry) -> dict:
    """将 KnowledgeEntry 序列化为可 JSON 化的字典"""
    d = asdict(entry)
    d["level"] = entry.level.value
    d["created_at"] = entry.created_at.isoformat()
    d["updated_at"] = entry.updated_at.isoformat()
    return d


def _entry_from_dict(d: dict) -> KnowledgeEntry:
    """从字典反序列化 KnowledgeEntry"""
    d = dict(d)  # 浅拷贝，避免修改原始数据
    d["level"] = KnowledgeLevel(d["level"])
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    d["updated_at"] = datetime.fromisoformat(d["updated_at"])
    return KnowledgeEntry(**d)


# ────────────────────────────────────────────
# KnowledgeManager — 知识管理器
# ────────────────────────────────────────────


class KnowledgeManager:
    """知识管理器

    管理三级知识条目的生命周期，提供搜索、上下文构建、权重衰减、
    过期清理、磁盘持久化和业务 RAG 集成等能力。

    使用示例::

        km = KnowledgeManager()

        # 添加知识
        entry = await km.add_requirement(
            domain="ecommerce",
            title="购物车数量限制",
            content="购物车最多添加 99 件商品",
            tags=["购物车", "数量限制"],
        )

        # 搜索知识
        results = await km.search("购物车", domain="ecommerce")

        # 构建上下文
        context = await km.build_context("测试购物车添加商品功能")
    """

    _KNOWLEDGE_DIR = ".uiai_knowledge"
    _DATA_FILENAME = "knowledge.json"
    _LEVEL_DIRS: dict[KnowledgeLevel, str] = {
        KnowledgeLevel.REQUIREMENT: "requirements",
        KnowledgeLevel.PRODUCT: "products",
        KnowledgeLevel.EXPERIENCE: "experiences",
    }

    def __init__(
        self,
        knowledge_dir: Optional[str] = None,
        max_entries: int = 500,
    ) -> None:
        """初始化知识管理器

        Args:
            knowledge_dir: 知识持久化目录，默认为 .uiai_knowledge/
            max_entries: 最大知识条目数
        """
        self._knowledge_dir = Path(knowledge_dir) if knowledge_dir else Path(self._KNOWLEDGE_DIR)
        self._max_entries = max_entries
        self._entries: dict[str, KnowledgeEntry] = {}

    # ── 添加知识 ──────────────────────────────────────────

    async def add(self, entry: KnowledgeEntry) -> None:
        """添加知识条目

        当条目数达到上限时，按权重淘汰权重最低的条目。

        Args:
            entry: 知识条目
        """
        if len(self._entries) >= self._max_entries:
            self._evict_lowest_weight()
        self._entries[entry.id] = entry
        logger.debug(
            "知识条目已添加: id=%s level=%s domain=%s title=%s",
            entry.id, entry.level.value, entry.domain, entry.title,
        )

    async def add_requirement(
        self,
        domain: str,
        title: str,
        content: str,
        tags: Optional[list[str]] = None,
    ) -> KnowledgeEntry:
        """添加需求级知识

        Args:
            domain: 业务领域
            title: 简短描述
            content: 完整知识内容
            tags: 搜索标签

        Returns:
            创建的知识条目
        """
        entry = KnowledgeEntry(
            id=_generate_id(),
            level=KnowledgeLevel.REQUIREMENT,
            domain=domain,
            title=title,
            content=content,
            tags=tags or [],
            source="manual",
        )
        await self.add(entry)
        return entry

    async def add_product(
        self,
        domain: str,
        title: str,
        content: str,
        tags: Optional[list[str]] = None,
    ) -> KnowledgeEntry:
        """添加产品级知识

        Args:
            domain: 业务领域
            title: 简短描述
            content: 完整知识内容
            tags: 搜索标签

        Returns:
            创建的知识条目
        """
        entry = KnowledgeEntry(
            id=_generate_id(),
            level=KnowledgeLevel.PRODUCT,
            domain=domain,
            title=title,
            content=content,
            tags=tags or [],
            source="manual",
        )
        await self.add(entry)
        return entry

    async def add_experience(
        self,
        domain: str,
        title: str,
        content: str,
        tags: Optional[list[str]] = None,
        source: str = "agent_learned",
    ) -> KnowledgeEntry:
        """添加经验级知识

        Args:
            domain: 业务领域
            title: 简短描述
            content: 完整知识内容
            tags: 搜索标签
            source: 知识来源，默认 "agent_learned"

        Returns:
            创建的知识条目
        """
        entry = KnowledgeEntry(
            id=_generate_id(),
            level=KnowledgeLevel.EXPERIENCE,
            domain=domain,
            title=title,
            content=content,
            tags=tags or [],
            source=source,
        )
        await self.add(entry)
        return entry

    # ── 搜索与检索 ────────────────────────────────────────

    async def search(
        self,
        query: str,
        level: Optional[KnowledgeLevel] = None,
        domain: Optional[str] = None,
        top_k: int = 5,
    ) -> list[KnowledgeEntry]:
        """按关键词/标签搜索知识条目

        对 query 进行分词后，与条目的 title、content、tags 进行匹配，
        计算综合相关度分数后返回 top_k 结果。

        Args:
            query: 搜索查询文本
            level: 限定知识级别，None 表示不限
            domain: 限定业务领域，None 表示不限
            top_k: 返回最大条目数

        Returns:
            按相关度降序排列的知识条目列表
        """
        candidates: list[tuple[float, KnowledgeEntry]] = []
        for entry in self._entries.values():
            # 级别过滤
            if level is not None and entry.level != level:
                continue
            # 领域过滤
            if domain is not None and entry.domain != domain:
                continue
            score = self._match_score(query, entry)
            if score > 0:
                candidates.append((score, entry))

        # 按分数降序排序，取 top_k
        candidates.sort(key=lambda x: x[0], reverse=True)
        results = [entry for _, entry in candidates[:top_k]]

        # 更新命中计数
        for entry in results:
            entry.hit_count += 1
            entry.updated_at = _now()

        return results

    async def get_relevant(
        self,
        task_description: str,
        top_k: int = 5,
    ) -> list[KnowledgeEntry]:
        """获取与任务描述相关的知识条目

        综合考虑关键词匹配度、权重和命中次数，返回最相关的知识。

        Args:
            task_description: 任务描述文本
            top_k: 返回最大条目数

        Returns:
            按综合相关度降序排列的知识条目列表
        """
        scored: list[tuple[float, KnowledgeEntry]] = []
        for entry in self._entries.values():
            match_score = self._match_score(task_description, entry)
            if match_score <= 0:
                continue
            # 综合分数 = 匹配分数 × 权重 × (1 + log(1 + hit_count))
            composite = match_score * entry.weight * (1 + math.log1p(entry.hit_count))
            scored.append((composite, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [entry for _, entry in scored[:top_k]]

        for entry in results:
            entry.hit_count += 1
            entry.updated_at = _now()

        return results

    # ── 更新与删除 ────────────────────────────────────────

    async def update(
        self,
        entry_id: str,
        content: Optional[str] = None,
        weight: Optional[float] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        """更新知识条目

        Args:
            entry_id: 知识条目 ID
            content: 新内容，None 表示不更新
            weight: 新权重，None 表示不更新
            tags: 新标签列表，None 表示不更新

        Raises:
            KeyError: 条目 ID 不存在
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            raise KeyError(f"知识条目不存在: {entry_id}")

        if content is not None:
            entry.content = content
            entry.version_hash = _content_hash(content)
        if weight is not None:
            entry.weight = weight
        if tags is not None:
            entry.tags = tags
        entry.updated_at = _now()

        logger.debug("知识条目已更新: id=%s", entry_id)

    async def remove(self, entry_id: str) -> None:
        """删除知识条目

        Args:
            entry_id: 知识条目 ID
        """
        removed = self._entries.pop(entry_id, None)
        if removed is not None:
            logger.debug("知识条目已删除: id=%s title=%s", entry_id, removed.title)
        else:
            logger.warning("删除失败，知识条目不存在: %s", entry_id)

    # ── 权重衰减与过期清理 ────────────────────────────────

    async def decay_weights(self, decay_factor: float = 0.95) -> None:
        """对所有知识条目的权重进行衰减

        定期调用此方法，使长期未使用的知识权重逐渐降低，
        最终在 cleanup_expired 中被清理。

        Args:
            decay_factor: 衰减因子，0 < decay_factor < 1，默认 0.95
        """
        for entry in self._entries.values():
            entry.weight *= decay_factor
            # 避免浮点精度导致权重无限趋近但不为零
            if entry.weight < 1e-6:
                entry.weight = 0.0
        logger.debug("权重衰减完成，衰减因子=%.4f", decay_factor)

    async def cleanup_expired(self, min_weight: float = 0.1) -> int:
        """清理权重低于阈值的知识条目

        Args:
            min_weight: 最低权重阈值，低于此值的条目将被移除

        Returns:
            被清理的条目数量
        """
        expired_ids = [
            eid for eid, entry in self._entries.items()
            if entry.weight < min_weight
        ]
        for eid in expired_ids:
            del self._entries[eid]
        if expired_ids:
            logger.info("已清理 %d 条低权重知识（阈值=%.2f）", len(expired_ids), min_weight)
        return len(expired_ids)

    # ── 上下文构建 ────────────────────────────────────────

    async def build_context(
        self,
        task_description: str,
        max_tokens: int = 2000,
    ) -> str:
        """为 LLM 构建知识上下文字符串

        根据任务描述检索相关知识，按优先级（需求级 > 产品级 > 经验级）
        和相关度排序，在 max_tokens 预算内组装上下文。

        Args:
            task_description: 任务描述文本
            max_tokens: 最大 token 预算

        Returns:
            格式化的知识上下文字符串
        """
        relevant = await self.get_relevant(task_description, top_k=20)

        # 按级别优先级排序：需求级 > 产品级 > 经验级
        level_priority = {
            KnowledgeLevel.REQUIREMENT: 0,
            KnowledgeLevel.PRODUCT: 1,
            KnowledgeLevel.EXPERIENCE: 2,
        }
        relevant.sort(key=lambda e: level_priority.get(e.level, 99))

        sections: list[str] = []
        current_tokens = 0
        header = "## 相关知识\n"
        header_tokens = self._token_estimate(header)
        current_tokens += header_tokens
        sections.append(header)

        for entry in relevant:
            block = (
                f"### [{entry.level.value}] {entry.title}\n"
                f"- 领域: {entry.domain}\n"
                f"- 来源: {entry.source or '未知'}\n"
                f"- 权重: {entry.weight:.2f}\n\n"
                f"{entry.content}\n\n"
            )
            block_tokens = self._token_estimate(block)
            if current_tokens + block_tokens > max_tokens:
                break
            sections.append(block)
            current_tokens += block_tokens

        if len(sections) <= 1:
            return ""

        return "".join(sections)

    # ── 统计 ──────────────────────────────────────────────

    def stats(self) -> dict:
        """获取知识统计信息

        Returns:
            包含各级别条目数、总条目数、平均权重等统计信息的字典
        """
        level_counts: dict[str, int] = {lv.value: 0 for lv in KnowledgeLevel}
        domain_counts: dict[str, int] = {}
        total_weight = 0.0
        total_hits = 0

        for entry in self._entries.values():
            level_counts[entry.level.value] += 1
            domain_counts[entry.domain] = domain_counts.get(entry.domain, 0) + 1
            total_weight += entry.weight
            total_hits += entry.hit_count

        count = len(self._entries)
        return {
            "total_entries": count,
            "max_entries": self._max_entries,
            "level_counts": level_counts,
            "domain_counts": domain_counts,
            "avg_weight": round(total_weight / count, 4) if count > 0 else 0.0,
            "total_hits": total_hits,
        }

    # ── 持久化 ────────────────────────────────────────────

    def save_to_disk(self) -> None:
        """将知识条目持久化到磁盘（JSON 格式）

        同时创建各级别子目录，并将每个条目按级别保存到对应子目录中。
        """
        self._knowledge_dir.mkdir(parents=True, exist_ok=True)

        # 创建级别子目录
        for dir_name in self._LEVEL_DIRS.values():
            (self._knowledge_dir / dir_name).mkdir(parents=True, exist_ok=True)

        # 保存主索引文件
        data = {
            "version": 1,
            "saved_at": _now().isoformat(),
            "max_entries": self._max_entries,
            "entries": {
                eid: _entry_to_dict(e) for eid, e in self._entries.items()
            },
        }
        index_file = self._knowledge_dir / self._DATA_FILENAME
        tmp_file = index_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_file.replace(index_file)
            logger.info("知识库已保存到 %s（共 %d 条）", index_file, len(self._entries))
        except OSError:
            logger.exception("知识库保存失败")
            if tmp_file.exists():
                tmp_file.unlink()

        # 按级别保存独立文件，便于人工查阅
        for level, dir_name in self._LEVEL_DIRS.items():
            level_entries = [
                _entry_to_dict(e) for e in self._entries.values() if e.level == level
            ]
            if not level_entries:
                continue
            level_file = self._knowledge_dir / dir_name / f"{level.value}.json"
            level_tmp = level_file.with_suffix(".tmp")
            try:
                with open(level_tmp, "w", encoding="utf-8") as f:
                    json.dump(level_entries, f, ensure_ascii=False, indent=2)
                level_tmp.replace(level_file)
            except OSError:
                logger.exception("级别文件保存失败: %s", level_file)
                if level_tmp.exists():
                    level_tmp.unlink()

    def load_from_disk(self) -> None:
        """从磁盘加载知识条目"""
        index_file = self._knowledge_dir / self._DATA_FILENAME
        if not index_file.exists():
            logger.info("知识库文件不存在，跳过加载: %s", index_file)
            return
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") != 1:
                logger.warning("知识库版本不兼容，跳过加载")
                return
            self._max_entries = data.get("max_entries", self._max_entries)
            entries_data = data.get("entries", {})
            self._entries.clear()
            for eid, edata in entries_data.items():
                self._entries[eid] = _entry_from_dict(edata)
            logger.info("知识库已从 %s 加载（共 %d 条）", index_file, len(self._entries))
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            logger.exception("知识库加载失败，将使用空知识库")
            self._entries.clear()

    # ── 业务 RAG 集成 ─────────────────────────────────────

    async def import_from_rag(
        self,
        rag_endpoint: str,
        domain: str,
        query: str,
    ) -> list[KnowledgeEntry]:
        """从外部 RAG 服务导入知识

        通过 HTTP 请求访问 RAG 服务，将返回的知识片段转为经验级条目。

        Args:
            rag_endpoint: RAG 服务端点 URL
            domain: 业务领域
            query: 查询文本

        Returns:
            导入的知识条目列表
        """
        import urllib.request
        import urllib.error

        url = f"{rag_endpoint.rstrip('/')}/query"
        payload = json.dumps({"query": query, "domain": domain}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            logger.error("RAG 服务请求失败: endpoint=%s error=%s", rag_endpoint, exc)
            return []

        # 期望返回格式: {"results": [{"title": ..., "content": ..., "tags": [...]}]}
        fragments = result.get("results", [])
        imported: list[KnowledgeEntry] = []

        for frag in fragments:
            entry = KnowledgeEntry(
                id=_generate_id(),
                level=KnowledgeLevel.EXPERIENCE,
                domain=domain,
                title=frag.get("title", query[:50]),
                content=frag.get("content", ""),
                tags=frag.get("tags", []),
                source="rag_import",
            )
            if entry.content:
                await self.add(entry)
                imported.append(entry)

        if imported:
            logger.info("从 RAG 导入 %d 条知识（domain=%s）", len(imported), domain)
        return imported

    async def sync_business_rules(self, rules_file: str) -> int:
        """从 YAML/JSON 文件同步业务规则

        支持两种格式：
        - JSON: 直接解析
        - YAML: 需要 PyYAML 依赖

        文件格式示例（JSON）::

            {
              "domain": "ecommerce",
              "level": "requirement",
              "rules": [
                {
                  "title": "购物车数量限制",
                  "content": "购物车最多添加 99 件商品",
                  "tags": ["购物车", "限制"]
                }
              ]
            }

        Args:
            rules_file: 规则文件路径（JSON 或 YAML）

        Returns:
            同步的规则数量
        """
        rules_path = Path(rules_file)
        if not rules_path.exists():
            logger.error("规则文件不存在: %s", rules_file)
            return 0

        try:
            raw = rules_path.read_text(encoding="utf-8")
        except OSError:
            logger.exception("规则文件读取失败: %s", rules_file)
            return 0

        # 根据后缀选择解析器
        suffix = rules_path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                logger.error("YAML 解析需要 PyYAML 依赖，请安装: pip install pyyaml")
                return 0
            data = yaml.safe_load(raw)
        elif suffix == ".json":
            data = json.loads(raw)
        else:
            logger.error("不支持的规则文件格式: %s（支持 .json/.yaml/.yml）", suffix)
            return 0

        domain = data.get("domain", "general")
        level_str = data.get("level", "requirement")
        try:
            level = KnowledgeLevel(level_str)
        except ValueError:
            logger.warning("无效的知识级别 '%s'，使用默认 'requirement'", level_str)
            level = KnowledgeLevel.REQUIREMENT

        rules = data.get("rules", [])
        synced = 0

        for rule in rules:
            title = rule.get("title", "")
            content = rule.get("content", "")
            if not title or not content:
                continue
            entry = KnowledgeEntry(
                id=_generate_id(),
                level=level,
                domain=domain,
                title=title,
                content=content,
                tags=rule.get("tags", []),
                source="rag_import",
            )
            await self.add(entry)
            synced += 1

        if synced:
            logger.info("从 %s 同步 %d 条业务规则（domain=%s level=%s）",
                        rules_file, synced, domain, level.value)
        return synced

    # ── 内部方法 ──────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简易中文分词

        策略：先按空格/标点切分，再对纯中文片段按 2-gram 滑动窗口拆分，
        同时保留原始片段作为完整词参与匹配。

        Args:
            text: 待分词文本

        Returns:
            词项列表
        """
        # 按空格和常见标点切分
        segments = re.split(r"[\s,，、；;：:！!？?。.·]+", text.lower())
        segments = [s for s in segments if s]

        terms: list[str] = []
        for seg in segments:
            terms.append(seg)  # 保留完整片段
            # 对包含中文的片段做 2-gram 拆分，提取更细粒度的匹配词
            chinese_chars = [ch for ch in seg if "\u4e00" <= ch <= "\u9fff"]
            if len(chinese_chars) >= 2:
                for i in range(len(chinese_chars) - 1):
                    terms.append(chinese_chars[i] + chinese_chars[i + 1])
        return terms

    def _match_score(self, query: str, entry: KnowledgeEntry) -> float:
        """计算查询与知识条目的相关度分数

        匹配策略：
        1. 完整查询在 title/content 中出现 → 高分
        2. 查询分词后各词在 title/content/tags 中的命中数 → 按比例计分
        3. 条目标签作为关键词反向匹配查询文本 → 额外加分

        Args:
            query: 查询文本
            entry: 知识条目

        Returns:
            相关度分数（0 表示不相关）
        """
        if not query:
            return 0.0

        query_lower = query.lower()
        title_lower = entry.title.lower()
        content_lower = entry.content.lower()
        tags_lower = [t.lower() for t in entry.tags]

        score = 0.0

        # 完整查询匹配
        if query_lower in title_lower:
            score += 3.0
        if query_lower in content_lower:
            score += 1.5

        # 分词匹配
        terms = self._tokenize(query_lower)

        if terms:
            title_hits = sum(1 for t in terms if t in title_lower)
            content_hits = sum(1 for t in terms if t in content_lower)
            tag_hits = sum(1 for t in terms if any(t in tag for tag in tags_lower))

            total_terms = len(terms)
            score += (title_hits / total_terms) * 2.0
            score += (content_hits / total_terms) * 1.0
            score += (tag_hits / total_terms) * 2.5

        # 标签反向匹配：条目标签出现在查询文本中也算相关
        for tag in tags_lower:
            if tag in query_lower:
                score += 1.5

        return score

    @staticmethod
    def _token_estimate(text: str) -> int:
        """估算文本的 token 数量

        粗略估算：英文约 4 字符 = 1 token，中文约 1.5 字符 = 1 token。
        综合取 text 长度 / 3 作为近似值。

        Args:
            text: 待估算文本

        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        # 中文字符占比越高，token/字符比越高
        chinese_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        non_chinese = len(text) - chinese_chars
        # 中文约 1.5 字符/token，英文约 4 字符/token
        return int(chinese_chars / 1.5 + non_chinese / 4.0) + 1

    def _evict_lowest_weight(self) -> None:
        """淘汰权重最低的知识条目"""
        if not self._entries:
            return
        worst_id = min(self._entries, key=lambda k: self._entries[k].weight)
        removed = self._entries.pop(worst_id)
        logger.debug(
            "淘汰低权重知识: id=%s title=%s weight=%.4f",
            worst_id, removed.title, removed.weight,
        )
