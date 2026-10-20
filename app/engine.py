"""记忆引擎：Add 写入（切块+嵌入+存储）、Search 检索（稠密+稀疏+RRF 融合）。"""
from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from .bm25 import BM25, tokenize
from .embedder import Embedder
from .store import Storage
from .vector_utils import cosine, pack_vec, unpack_vec

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_MAX_CHUNK_CHARS = 800
_MAX_SENTENCES = 4

# 时间敏感查询信号：命中则给更近的记忆加一个「有界」的排序加分
_RECENCY_WORDS = (
    "latest", "recent", "recently", "newest", "now", "current", "currently",
    "today", "yesterday", "this month", "this week", "this year", "these days",
    "nowadays", "presently", "most recent", "lately",
)


def is_recency_query(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _RECENCY_WORDS)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def chunk_text(text: str, max_chars: int = _MAX_CHUNK_CHARS, max_sentences: int = _MAX_SENTENCES) -> list[str]:
    """把一段文本切成若干检索块：按句子聚合，再对超长块按空格硬切。"""
    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if buf:
            chunks.append(" ".join(buf))
            buf, buf_len = [], 0

    for s in sentences:
        if buf and buf_len + len(s) + 1 > max_chars:
            flush()
        buf.append(s)
        buf_len += len(s) + 1
        if len(buf) >= max_sentences:
            flush()
    flush()

    result: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            result.append(c)
            continue
        # 超长块：按空格硬切
        words = c.split(" ")
        part: list[str] = []
        plen = 0
        for w in words:
            if part and plen + len(w) + 1 > max_chars:
                result.append(" ".join(part))
                part, plen = [], 0
            part.append(w)
            plen += len(w) + 1
        if part:
            result.append(" ".join(part))
    return result


def parse_ts(value: Any) -> float | None:
    """把 ISO 字符串 / Unix 毫秒 / Unix 秒 统一转成 Unix 秒。失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e11 else v  # >1e11 视为毫秒
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return parse_ts(float(s))
        except ValueError:
            pass
        s2 = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s2).timestamp()
        except ValueError:
            return None
    return None


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class UserIndex:
    def __init__(self) -> None:
        self.ids: list[int] = []
        self.contents: list[str] = []
        self.created_at: list[str] = []
        self.created_ts: list[float] = []
        self.vectors: list[list[float]] = []
        self.bm25 = BM25()
        self.loaded = False


class MemoryEngine:
    def __init__(
        self,
        storage: Storage,
        embedder: Embedder,
        dense_threshold: float = 0.15,
        max_cached_users: int = 32,
    ):
        self.storage = storage
        self.embedder = embedder
        self.dense_threshold = dense_threshold
        self._max_cached = max_cached_users
        # 用 OrderedDict 做 LRU 缓存：内存只保留最近使用的若干用户索引，避免 Full 评测
        # 大量 user_id 时内存无限增长（数据在 SQLite，淘汰后可随时重新加载）
        self._users: OrderedDict[str, UserIndex] = OrderedDict()
        self._lock = asyncio.Lock()

    def _get_index(self, user_id: str) -> UserIndex | None:
        idx = self._users.get(user_id)
        if idx is not None:
            self._users.move_to_end(user_id)  # 标记为最近使用
        return idx

    def _load_user(self, user_id: str) -> UserIndex:
        idx = self._get_index(user_id)
        if idx is not None and idx.loaded:
            return idx
        idx = UserIndex()
        rows = self.storage.get_user_memories(user_id)
        idx.ids = [r["id"] for r in rows]
        idx.contents = [r["content"] for r in rows]
        idx.created_at = [r["created_at"] for r in rows]
        idx.created_ts = [r["created_ts"] for r in rows]
        idx.vectors = [unpack_vec(r["embedding"]) for r in rows]
        idx.bm25 = BM25()
        for c in idx.contents:
            idx.bm25.add(tokenize(c))
        idx.loaded = True
        self._users[user_id] = idx
        self._users.move_to_end(user_id)
        while len(self._users) > self._max_cached:
            self._users.popitem(last=False)  # 淘汰最久未用的用户索引
        return idx

    def _chunk_messages(self, messages: list) -> list[tuple[str, float]]:
        """把消息列表切成 (内容, 时间戳) 块。"""
        chunks: list[tuple[str, float]] = []
        now = time.time()
        prev_ts = now - 1.0
        for m in messages or []:
            if not isinstance(m, dict):
                continue
            content = m.get("content")
            if not isinstance(content, str):
                content = "" if content is None else str(content)
            ts = parse_ts(m.get("created_at", m.get("timestamp")))
            if ts is None:
                ts = max(now, prev_ts + 1e-3)
            for c in chunk_text(content):
                chunks.append((c, ts))
            prev_ts = max(prev_ts, ts)
        return chunks

    async def add(
        self,
        user_id: str,
        session_id: str,
        request_id: str,
        messages: list,
    ) -> dict[str, Any]:
        # 1) 快速幂等检查（命中直接返回，避免重复嵌入）
        async with self._lock:
            if request_id and self.storage.is_processed(request_id):
                return {"success": True, "skipped": True, "count": 0}

        # 2) 切块（无锁，纯计算）
        chunks = self._chunk_messages(messages)

        # 3) 嵌入（网络调用放锁外，避免串行化并发写入）
        embeddings = (
            await self.embedder.embed([c for c, _ in chunks], text_type="document")
            if chunks
            else []
        )

        # 4) 落库 + 更新内存索引（拿锁，二次幂等检查防并发）
        async with self._lock:
            if request_id and self.storage.is_processed(request_id):
                return {"success": True, "skipped": True, "count": 0}

            if not chunks:
                if request_id:
                    self.storage.mark_processed(request_id, time.time())
                return {"success": True, "skipped": False, "count": 0}

            rows: list[dict[str, Any]] = []
            for (content, ts), vec in zip(chunks, embeddings):
                rows.append(
                    {
                        "user_id": user_id,
                        "session_id": session_id or "",
                        "request_id": request_id or "",
                        "content": content,
                        "created_ts": ts,
                        "created_at": iso(ts),
                        "embedding": pack_vec(vec),
                    }
                )
            ids = self.storage.insert_memories(rows)

            # 只有落库成功后才标记已处理：失败时平台可安全重试该 request_id
            if request_id:
                self.storage.mark_processed(request_id, time.time())

            # 同步更新内存索引（若已加载）
            idx = self._get_index(user_id)
            if idx is not None and idx.loaded:
                for row, mid, vec in zip(rows, ids, embeddings):
                    idx.ids.append(mid)
                    idx.contents.append(row["content"])
                    idx.created_at.append(row["created_at"])
                    idx.created_ts.append(row["created_ts"])
                    idx.vectors.append(list(vec))
                    idx.bm25.add(tokenize(row["content"]))

            return {"success": True, "skipped": False, "count": len(ids)}

    async def search(self, user_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
        # 查询嵌入放锁外（网络调用）
        qvec = (await self.embedder.embed([query], text_type="query"))[0]

        # 读索引 + 计算全程拿锁，保证与 add 的写入互斥，避免读到不一致的中间态
        async with self._lock:
            idx = self._load_user(user_id)
            if not idx.ids:
                return []

            dense = cosine(idx.vectors, qvec)
            tokens = tokenize(query)
            bm25_scores = idx.bm25.scores(tokens)

            # 相关性门控：BM25 命中 或 稠密相似度达标 才算候选，否则返回空（abstain）
            candidates = [
                i for i in range(len(dense))
                if bm25_scores[i] > 0.0 or dense[i] >= self.dense_threshold
            ]
            if not candidates:
                return []

            m = 200
            # 排序时用 (分数, 时间戳) 作键：分数相同时更近的优先（打破稳定排序偏向旧记忆的问题）
            dense_order = sorted(
                candidates, key=lambda i: (dense[i], idx.created_ts[i]), reverse=True
            )[:m]
            bm25_order = [
                i
                for i in sorted(
                    candidates, key=lambda i: (bm25_scores[i], idx.created_ts[i]), reverse=True
                )
                if bm25_scores[i] > 0.0
            ][:m]

            # RRF（Reciprocal Rank Fusion）合并两种排序
            rrf: dict[int, float] = {}
            k = 60
            for rank, i in enumerate(dense_order):
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (k + rank + 1)
            for rank, i in enumerate(bm25_order):
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (k + rank + 1)

            # 时间敏感查询：加一个有界的「更近优先」信号（权重 0.5，相关性仍主导）
            if is_recency_query(query):
                recency_order = sorted(
                    candidates, key=lambda i: idx.created_ts[i], reverse=True
                )[:m]
                for rank, i in enumerate(recency_order):
                    rrf[i] = rrf.get(i, 0.0) + 0.5 / (k + rank + 1)

            ranked = sorted(rrf.items(), key=lambda x: -x[1])
            out: list[dict[str, Any]] = []
            for i, _ in ranked[:top_k]:
                out.append(
                    {
                        "id": idx.ids[i],
                        "content": idx.contents[i],
                        "created_at": idx.created_at[i],
                    }
                )
            return out
