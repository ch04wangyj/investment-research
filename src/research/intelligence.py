"""Auditable research-intelligence library and versioned agent skill packs.

The learning boundary is intentionally explicit: agents retrieve curated
metadata, summaries, and source links. They do not rewrite their own prompts or
silently absorb untraceable text into model context.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from typing import Any

from config.settings import get_settings
from src.research.daily_reads import collect_daily_reads
from src.research.schemas import EvidenceItem
from src.research.strategy_research import collect_strategy_research

QUALITY_SCORE = {
    "primary": 100,
    "institutional": 85,
    "media": 70,
    "search": 55,
    "unknown": 35,
}

_REFRESH_LOCK = Lock()

SKILL_PACKS = [
    {
        "id": "source-ranked-research",
        "version": "1.0.0",
        "title": "来源分层与证据链",
        "description": "先读一手披露，再读机构资料，最后用媒体与搜索线索补充背景。",
        "agent_roles": ["fundamentals-researcher", "macro-researcher", "report-writer", "research-auditor"],
        "guardrails": ["保留来源 URL、质量标签和时间", "搜索摘要不能替代原文", "冲突证据必须保留"],
        "status": "active",
    },
    {
        "id": "macro-cycle-map",
        "version": "1.0.0",
        "title": "宏观周期问题树",
        "description": "按增长、通胀、政策、流动性、信用和外部环境拆解宏观判断。",
        "agent_roles": ["macro-researcher", "fixed-income-researcher"],
        "guardrails": ["宏观叙事至少绑定一个指标", "政策表述与市场定价分开记录"],
        "status": "active",
    },
    {
        "id": "fixed-income-framework",
        "version": "1.0.0",
        "title": "固收曲线、信用与机构行为",
        "description": "基于本地华泰固收框架提炼，覆盖资金面、曲线、信用、转债、机构行为与产品风险预算。",
        "agent_roles": ["fixed-income-researcher", "fund-product-analyst"],
        "guardrails": ["产品排行仅用于初筛", "短期年化不能外推", "产品名称不能替代持仓穿透"],
        "status": "active",
    },
    {
        "id": "frontier-strategy-review",
        "version": "1.0.0",
        "title": "前沿策略审查",
        "description": "收集论文和市场观点，但在采用前检查样本外稳健性、交易成本、流动性和可解释性。",
        "agent_roles": ["report-writer", "research-auditor"],
        "guardrails": ["禁止把回测收益直接视为可交易收益", "记录论文来源与发布时间", "优先可复核方法"],
        "status": "active",
    },
    {
        "id": "publication-gate",
        "version": "1.0.0",
        "title": "出版门禁",
        "description": "检查事实锚、来源覆盖、多空观点、数据缺口和归档产物完整性。",
        "agent_roles": ["research-auditor"],
        "guardrails": ["审计未通过不得标记为已出版", "MD、HTML、PDF 必须真实存在", "门禁不冒充人工逐条核验"],
        "status": "active",
    },
]

LOCAL_REFERENCE_LIBRARY = [
    {
        "kind": "local_reference",
        "category": "fixed_income",
        "title": "华泰固收分析框架合集2025版",
        "summary": "本地参考资料，已提炼为固收问题树和产品风险预算 skill pack；不复制原文。",
        "url": "",
        "source": "E:/外刊",
        "quality": "institutional",
        "tags": ["fixed_income", "macro", "liquidity", "credit", "convertible", "asset_allocation"],
        "as_of": "2025",
    },
]


class ResearchIntelligenceRepository:
    """SQLite-backed metadata library for curated research context."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or (get_settings().sqlite_dir / "research_intelligence.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _create_tables(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_documents (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    document_count INTEGER NOT NULL,
                    error TEXT
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_research_category ON research_documents(category)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_research_quality ON research_documents(quality)")

    def upsert_documents(self, documents: list[dict[str, Any]]) -> int:
        collected_at = datetime.now().isoformat()
        with self._connect() as connection:
            for document in documents:
                normalized = _normalize_document(document, collected_at=collected_at)
                connection.execute(
                    """
                    INSERT INTO research_documents (
                        id, kind, category, title, summary, url, source, quality,
                        tags_json, as_of, collected_at, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        kind=excluded.kind,
                        category=excluded.category,
                        title=excluded.title,
                        summary=excluded.summary,
                        source=excluded.source,
                        quality=excluded.quality,
                        tags_json=excluded.tags_json,
                        as_of=excluded.as_of,
                        collected_at=excluded.collected_at,
                        content_hash=excluded.content_hash
                    """,
                    (
                        normalized["id"],
                        normalized["kind"],
                        normalized["category"],
                        normalized["title"],
                        normalized["summary"],
                        normalized["url"],
                        normalized["source"],
                        normalized["quality"],
                        json.dumps(normalized["tags"], ensure_ascii=False),
                        normalized["as_of"],
                        normalized["collected_at"],
                        normalized["content_hash"],
                    ),
                )
        return len(documents)

    def record_refresh(self, started_at: str, status: str, document_count: int, error: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO refresh_runs (started_at, completed_at, status, document_count, error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (started_at, datetime.now().isoformat(), status, document_count, error),
            )

    def search(
        self,
        *,
        query: str = "",
        category: str = "all",
        quality: str = "all",
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        clauses = []
        parameters: list[Any] = []
        if category != "all":
            clauses.append("category = ?")
            parameters.append(category)
        if quality != "all":
            clauses.append("quality = ?")
            parameters.append(quality)
        sql = "SELECT * FROM research_documents"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        documents = [_row_to_document(row) for row in rows]
        normalized_query = query.strip().lower()
        for document in documents:
            text = " ".join(
                [
                    document["title"],
                    document["summary"],
                    document["source"],
                    document["category"],
                    " ".join(document["tags"]),
                ]
            ).lower()
            document["relevance"] = _relevance(text, normalized_query, document["quality"])
        if normalized_query:
            documents = [document for document in documents if document["relevance"] > 0]
        return sorted(
            documents,
            key=lambda document: (document["relevance"], document["as_of"], document["collected_at"]),
            reverse=True,
        )[: max(1, min(limit, 100))]

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM research_documents").fetchone()[0]
            categories = {
                row["category"]: row["count"]
                for row in connection.execute(
                    "SELECT category, COUNT(*) AS count FROM research_documents GROUP BY category"
                )
            }
            qualities = {
                row["quality"]: row["count"]
                for row in connection.execute(
                    "SELECT quality, COUNT(*) AS count FROM research_documents GROUP BY quality"
                )
            }
            latest = connection.execute(
                "SELECT completed_at, status, document_count, error FROM refresh_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {
            "total_documents": total,
            "categories": categories,
            "qualities": qualities,
            "latest_refresh": dict(latest) if latest else None,
        }


def refresh_research_intelligence(
    *,
    max_items_per_section: int = 5,
    repository: ResearchIntelligenceRepository | None = None,
) -> dict[str, Any]:
    """Refresh the public research catalog and local reference metadata."""

    repository = repository or ResearchIntelligenceRepository()
    started_at = datetime.now().isoformat()
    documents = list(LOCAL_REFERENCE_LIBRARY)
    try:
        daily = collect_daily_reads(max_items_per_section=max_items_per_section)
        strategy = collect_strategy_research(max_items_per_section=max_items_per_section)
        documents.extend(_flatten_sections(daily.get("sections", []), kind="daily_read"))
        documents.extend(_flatten_sections(strategy.get("sections", []), kind="strategy_research"))
        repository.upsert_documents(documents)
        repository.record_refresh(started_at, "completed", len(documents))
    except Exception as exc:
        repository.upsert_documents(documents)
        repository.record_refresh(started_at, "degraded", len(documents), str(exc))
    return intelligence_overview(repository=repository)


def should_auto_refresh_research_intelligence(
    repository: ResearchIntelligenceRepository | None = None,
) -> bool:
    settings = get_settings()
    if not settings.intelligence_auto_refresh_enabled:
        return False
    repository = repository or ResearchIntelligenceRepository()
    latest = repository.stats().get("latest_refresh")
    if not latest:
        return True
    try:
        last_completed = datetime.fromisoformat(str(latest["completed_at"]))
    except (KeyError, TypeError, ValueError):
        return True
    return datetime.now() - last_completed >= timedelta(hours=max(1, settings.intelligence_refresh_hours))


def maybe_refresh_research_intelligence(
    repository: ResearchIntelligenceRepository | None = None,
) -> bool:
    """Start a non-blocking refresh when the configured interval has elapsed."""

    repository = repository or ResearchIntelligenceRepository()
    if not should_auto_refresh_research_intelligence(repository):
        return False
    if not _REFRESH_LOCK.acquire(blocking=False):
        return False

    def _refresh() -> None:
        try:
            refresh_research_intelligence(repository=repository)
        finally:
            _REFRESH_LOCK.release()

    Thread(target=_refresh, name="research-intelligence-refresh", daemon=True).start()
    return True


def intelligence_overview(
    *,
    repository: ResearchIntelligenceRepository | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    repository = repository or ResearchIntelligenceRepository()
    repository.upsert_documents(LOCAL_REFERENCE_LIBRARY)
    refresh_scheduled = maybe_refresh_research_intelligence(repository)
    return {
        "generated_at": datetime.now().isoformat(),
        "positioning": "可审计的持续学习：自动刷新公开资料目录，按来源质量检索；Agent skills 只通过版本化白名单更新。",
        "stats": repository.stats(),
        "skills": SKILL_PACKS,
        "documents": repository.search(limit=limit),
        "auto_refresh": {
            "enabled": get_settings().intelligence_auto_refresh_enabled,
            "scheduled": refresh_scheduled,
            "interval_hours": get_settings().intelligence_refresh_hours,
        },
        "learning_protocol": [
            "只保存摘要、链接、来源质量、标签、时间和内容哈希。",
            "搜索线索不能替代公告、财报、论文或研报原文。",
            "Agent 不自行改写 prompt；skill pack 经过版本化发布后才生效。",
            "自动刷新失败时保留上一版知识库，并显式标记降级。",
        ],
    }


def search_research_intelligence(
    *,
    query: str = "",
    category: str = "all",
    quality: str = "all",
    limit: int = 40,
    repository: ResearchIntelligenceRepository | None = None,
) -> dict[str, Any]:
    repository = repository or ResearchIntelligenceRepository()
    return {
        "query": query,
        "category": category,
        "quality": quality,
        "items": repository.search(query=query, category=category, quality=quality, limit=limit),
    }


def retrieve_research_context(
    query: str,
    *,
    limit: int = 4,
    repository: ResearchIntelligenceRepository | None = None,
) -> list[EvidenceItem]:
    """Retrieve versioned context for downstream agents without network I/O."""

    repository = repository or ResearchIntelligenceRepository()
    maybe_refresh_research_intelligence(repository)
    documents = repository.search(query=query, limit=limit)
    return [
        EvidenceItem(
            channel="channel_analysis",
            title=document["title"],
            summary=document["summary"],
            url=document["url"],
            source=document["source"],
            quality=document["quality"],
            query="local_research_intelligence",
            as_of=document["as_of"],
            score=min(100, document["relevance"]),
        )
        for document in documents
    ]


def _flatten_sections(sections: list[dict[str, Any]], *, kind: str) -> list[dict[str, Any]]:
    documents = []
    for section in sections:
        category = str(section.get("id") or kind)
        for item in section.get("items", []):
            documents.append(
                {
                    "kind": kind,
                    "category": category,
                    "title": str(item.get("title", "")),
                    "summary": str(item.get("summary", "")),
                    "url": str(item.get("url", "")),
                    "source": str(item.get("source", "")),
                    "quality": str(item.get("quality", "unknown")),
                    "tags": list(item.get("tags") or item.get("method_tags") or []),
                    "as_of": str(item.get("as_of", "")),
                }
            )
    return documents


def _normalize_document(document: dict[str, Any], *, collected_at: str) -> dict[str, Any]:
    title = str(document.get("title", "")).strip()[:300]
    summary = str(document.get("summary", "")).strip()[:1000]
    url = str(document.get("url", "")).strip()
    source = str(document.get("source", "")).strip()
    quality = str(document.get("quality", "unknown"))
    if quality not in QUALITY_SCORE:
        quality = "unknown"
    tags = sorted({str(tag).strip() for tag in document.get("tags", []) if str(tag).strip()})[:12]
    content_hash = hashlib.sha256(f"{title}\n{summary}\n{url}".encode("utf-8")).hexdigest()
    return {
        "id": hashlib.sha256(f"{document.get('kind', '')}:{url or title}".encode("utf-8")).hexdigest(),
        "kind": str(document.get("kind", "research")),
        "category": str(document.get("category", "general")),
        "title": title,
        "summary": summary,
        "url": url,
        "source": source,
        "quality": quality,
        "tags": tags,
        "as_of": str(document.get("as_of", "")),
        "collected_at": collected_at,
        "content_hash": content_hash,
    }


def _row_to_document(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "category": row["category"],
        "title": row["title"],
        "summary": row["summary"],
        "url": row["url"],
        "source": row["source"],
        "quality": row["quality"],
        "tags": json.loads(row["tags_json"]),
        "as_of": row["as_of"],
        "collected_at": row["collected_at"],
        "content_hash": row["content_hash"],
    }


def _relevance(text: str, query: str, quality: str) -> float:
    base = QUALITY_SCORE.get(quality, QUALITY_SCORE["unknown"]) * 0.4
    if not query:
        return base
    tokens = [token for token in query.lower().split() if token]
    matches = sum(token in text for token in tokens)
    return base + matches * 18 if matches else 0
