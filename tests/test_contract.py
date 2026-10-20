"""AML Add/Search 契约测试（离线，用 hash 嵌入，不依赖网络）。"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.embedder import Embedder
from app.engine import MemoryEngine
from app.main import create_app
from app.store import Storage

KEY = "test-key"


@pytest.fixture()
def client(tmp_path):
    storage = Storage(str(tmp_path / "mem.db"))
    embedder = Embedder(api_key="", dim=64)  # 离线 hash 嵌入
    app = create_app(storage=storage, embedder=embedder, api_key=KEY)
    with TestClient(app) as c:
        yield c
    storage.close()


def _add(client, request_id, user_id, session_id, contents, key=KEY):
    return client.post(
        "/add",
        headers={"X-Api-Key": key},
        json={
            "request_id": request_id,
            "messages": [{"role": "user", "content": c} for c in contents],
            "user_id": user_id,
            "session_id": session_id,
        },
    )


def test_health_unauthenticated(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_add_requires_auth(client):
    r = client.post(
        "/add",
        json={"request_id": "r1", "messages": [], "user_id": "u1", "session_id": "s1"},
    )
    assert r.status_code == 401


def test_add_echoes_fields(client):
    r = _add(client, "r1", "u1", "s1", ["I live in Beijing"])
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["request_id"] == "r1"
    assert body["user_id"] == "u1"
    assert body["session_id"] == "s1"


def test_search_bearer_auth(client):
    _add(client, "r1", "u1", "s1", ["My dog is named Max"])
    r = client.post(
        "/search",
        headers={"Authorization": "Bearer " + KEY},
        json={"query": "what is my dog called", "user_id": "u1", "top_k": 10},
    )
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


def test_search_wrong_key_rejected(client):
    r = client.post(
        "/search",
        headers={"X-Api-Key": "wrong"},
        json={"query": "x", "user_id": "u1", "top_k": 5},
    )
    assert r.status_code == 401


def test_idempotent_add(client):
    _add(client, "same", "u1", "s1", ["I prefer coffee"])
    _add(client, "same", "u1", "s1", ["I prefer coffee"])
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "coffee", "user_id": "u1", "top_k": 100},
    )
    matches = [d["content"] for d in r.json()["data"] if "coffee" in d["content"].lower()]
    assert len(matches) == 1  # 同一 request_id 不重复写入


def test_user_id_isolation(client):
    _add(client, "r1", "alice", "s1", ["Alice lives in Beijing"])
    _add(client, "r2", "bob", "s1", ["Bob lives in Shanghai"])
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "where does Alice live", "user_id": "bob", "top_k": 10},
    )
    data = r.json()["data"]
    assert all("Alice" not in d["content"] for d in data)  # 不泄露他人记忆


def test_top_k_clamp(client):
    for i in range(5):
        _add(client, f"r{i}", "u1", "s1", [f"fact number {i} about apples"])
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "apples", "user_id": "u1", "top_k": 1000},
    )
    assert len(r.json()["data"]) <= 100


def test_relevance_order(client):
    _add(client, "r1", "u1", "s1", ["I live in Beijing"])
    _add(client, "r2", "u1", "s1", ["I like coffee"])
    _add(client, "r3", "u1", "s1", ["My dog is named Max"])
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "Which city do I live in", "user_id": "u1", "top_k": 3},
    )
    data = r.json()["data"]
    assert data and "Beijing" in data[0]["content"]


def test_created_at_is_iso8601(client):
    _add(client, "r1", "u1", "s1", ["hello world"])
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "hello", "user_id": "u1", "top_k": 10},
    )
    for d in r.json()["data"]:
        # fromisoformat 能解析即视为合法 ISO-8601
        datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))


def test_empty_result_when_no_match(client):
    _add(client, "r1", "u1", "s1", ["The sky is blue"])
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "zzzzqqqq unrelated", "user_id": "u1", "top_k": 10},
    )
    assert r.json()["data"] == []


def test_search_missing_query_422(client):
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "", "user_id": "u1", "top_k": 10},
    )
    assert r.status_code == 422


def test_recency_ranking(client):
    # 旧记忆「住北京」 vs 新记忆「住上海」：问「现在住哪」应把新的排前面
    client.post(
        "/add",
        headers={"X-Api-Key": KEY},
        json={
            "request_id": "r-old",
            "messages": [{"role": "user", "content": "I live in Beijing", "timestamp": 1700000000000}],
            "user_id": "u1",
            "session_id": "s1",
        },
    )
    client.post(
        "/add",
        headers={"X-Api-Key": KEY},
        json={
            "request_id": "r-new",
            "messages": [{"role": "user", "content": "I live in Shanghai", "timestamp": 1800000000000}],
            "user_id": "u1",
            "session_id": "s1",
        },
    )
    r = client.post(
        "/search",
        headers={"X-Api-Key": KEY},
        json={"query": "Where do I live now", "user_id": "u1", "top_k": 10},
    )
    data = r.json()["data"]
    assert data and "Shanghai" in data[0]["content"]


class _FlakyEmbedder(Embedder):
    """第一次 embed 抛异常，之后正常（模拟嵌入接口瞬时故障）。"""

    def __init__(self):
        super().__init__(api_key="", dim=64)
        self.fail = True

    async def embed(self, texts, text_type="document"):
        if self.fail:
            raise RuntimeError("embed API down")
        return await super().embed(texts, text_type)


def test_retry_after_embed_failure(tmp_path):
    """嵌入失败时不应标记已处理，平台重试同一 request_id 能成功写入。"""
    storage = Storage(str(tmp_path / "m.db"))
    embedder = _FlakyEmbedder()
    engine = MemoryEngine(storage, embedder)

    async def scenario():
        with pytest.raises(RuntimeError):
            await engine.add("u1", "s1", "r1", [{"role": "user", "content": "I live in Beijing"}])
        # 失败后：未标记已处理、未写入
        assert not storage.is_processed("r1")
        assert storage.get_user_memories("u1") == []
        # 重试成功
        embedder.fail = False
        r = await engine.add("u1", "s1", "r1", [{"role": "user", "content": "I live in Beijing"}])
        assert r["count"] == 1
        assert len(storage.get_user_memories("u1")) == 1

    asyncio.run(scenario())
    storage.close()


def test_lru_eviction(tmp_path):
    """内存缓存 LRU 淘汰：缓存不超上限，被淘汰用户仍能从 SQLite 重新加载检索。"""
    storage = Storage(str(tmp_path / "m.db"))
    embedder = Embedder(api_key="", dim=64)
    engine = MemoryEngine(storage, embedder, max_cached_users=3)

    async def scenario():
        for i in range(5):
            await engine.add(f"u{i}", "s1", f"r{i}", [{"role": "user", "content": f"user {i} likes thing{i}"}])
        for i in range(5):
            res = await engine.search(f"u{i}", f"thing{i}", 5)
            assert res and f"thing{i}" in res[0]["content"]
        assert len(engine._users) <= 3  # 缓存不超上限
        # 最早的用户已被淘汰，但重新搜索仍能命中（从 SQLite 重载）
        res0 = await engine.search("u0", "thing0", 5)
        assert res0 and "thing0" in res0[0]["content"]
        assert len(engine._users) <= 3

    asyncio.run(scenario())
    storage.close()
