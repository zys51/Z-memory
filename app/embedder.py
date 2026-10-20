"""text-embedding-v4 嵌入客户端（阿里云 DashScope OpenAI 兼容接口），含离线 hash 回退。

- 提交/正式评测时必须配置 DASHSCOPE_API_KEY（走真实嵌入）。
- 未配置 Key 时自动使用确定性 hash 向量，仅用于本地开发与契约测试。
"""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from . import config

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def hash_embed(texts: list[str], dim: int) -> list[list[float]]:
    """离线确定性回退（仅开发/测试用，不代表检索质量）。"""
    dim = dim or 1024
    out: list[list[float]] = []
    for text in texts:
        v = [0.0] * dim
        for t in _TOKEN_RE.findall(text.lower()):
            h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            v[idx] += sign
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


class Embedder:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        batch: int | None = None,
        timeout: float | None = None,
    ):
        self.api_key = config.DASHSCOPE_API_KEY if api_key is None else api_key
        self.base_url = (config.DASHSCOPE_BASE_URL if base_url is None else base_url).rstrip("/")
        self.model = config.EMBED_MODEL if model is None else model
        self.dim = config.EMBED_DIM if dim is None else int(dim or 0)
        self.batch = config.EMBED_BATCH if batch is None else int(batch or 10)
        self.timeout = config.EMBED_TIMEOUT if timeout is None else float(timeout or 30)
        self.offline = not self.api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def embed(self, texts: list[str], text_type: str = "document") -> list[list[float]]:
        if not texts:
            return []
        if self.offline:
            return hash_embed(texts, self.dim)

        client = await self._get_client()  # 复用连接，避免每次 Add 都重新建 TLS 连接
        results: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            chunk = texts[i : i + self.batch]
            payload: dict = {"model": self.model, "input": chunk}
            if self.dim and self.dim > 0:
                payload["dimensions"] = self.dim
            resp = await client.post(
                self.base_url + "/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data = sorted(data, key=lambda d: d.get("index", 0))
            results.extend([d["embedding"] for d in data])
        return results
