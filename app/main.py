"""FastAPI 服务：/health、/add、/search（含 /v1 别名）+ 鉴权。

契约要点：
- /health 免鉴权返回 2xx
- /add 同步持久化后回显 request_id / user_id / session_id（幂等）
- /search 返回 {"data": [...]}，user_id 严格隔离，top_k 上限 100
- 鉴权支持 X-Api-Key / Authorization: Bearer / Token
"""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import config
from .embedder import Embedder
from .engine import MemoryEngine
from .store import Storage


class AddRequest(BaseModel):
    request_id: Optional[str] = None
    messages: list = Field(default_factory=list)
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class SearchRequest(BaseModel):
    query: Optional[str] = None
    user_id: Optional[str] = None
    top_k: Optional[int] = 100


def create_app(
    storage: Storage | None = None,
    embedder: Embedder | None = None,
    api_key: str | None = None,
) -> FastAPI:
    storage = storage or Storage(config.DB_PATH)
    embedder = embedder or Embedder()
    api_key = config.AML_API_KEY if api_key is None else api_key
    engine = MemoryEngine(
        storage,
        embedder,
        dense_threshold=config.DENSE_THRESHOLD,
        max_cached_users=config.MAX_CACHED_USERS,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await embedder.aclose()  # 关闭嵌入客户端的连接池

    app = FastAPI(title="AML Memory Service", version="1.0.0", lifespan=lifespan)

    async def authorize(request: Request) -> None:
        if not api_key:
            return  # 未配置 Key：本地开发不鉴权
        candidates = [
            request.headers.get("X-Api-Key", ""),
            request.headers.get("Authorization", ""),
        ]
        for val in candidates:
            v = (val or "").strip()
            if not v:
                continue
            low = v.lower()
            if low.startswith("bearer "):
                v = v[7:].strip()
            elif low.startswith("token "):
                v = v[6:].strip()
            if hmac.compare_digest(v, api_key):
                return
        raise HTTPException(status_code=401, detail={"reason": "invalid API key"})

    @app.get("/")
    @app.get("/health")
    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "aml-memory-service",
            "protocol": "agent-memory-leaderboard",
        }

    @app.post("/add")
    @app.post("/v1/add")
    async def add(req: AddRequest, _: None = Depends(authorize)) -> dict[str, Any]:
        user_id = req.user_id or ""
        request_id = req.request_id or ""
        session_id = req.session_id or ""
        try:
            await engine.add(user_id, session_id, request_id, req.messages or [])
        except Exception as exc:  # 嵌入 API 失败等 → 500，平台可重试
            return JSONResponse(status_code=500, content={"detail": {"reason": str(exc)}})
        return {
            "success": True,
            "request_id": request_id,
            "user_id": user_id,
            "session_id": session_id,
        }

    @app.post("/search")
    @app.post("/v1/search")
    async def search(req: SearchRequest, _: None = Depends(authorize)) -> dict[str, Any]:
        query = (req.query or "").strip()
        user_id = (req.user_id or "").strip()
        top_k = req.top_k

        if not query or not user_id:
            raise HTTPException(status_code=422, detail={"reason": "query and user_id are required"})
        if isinstance(top_k, bool):
            raise HTTPException(status_code=422, detail={"reason": "top_k must be a positive integer"})
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail={"reason": "top_k must be a positive integer"})
        if top_k < 1:
            raise HTTPException(status_code=422, detail={"reason": "top_k must be positive"})
        top_k = min(top_k, config.TOP_K_MAX)

        try:
            data = await engine.search(user_id, query, top_k)
        except Exception as exc:
            return JSONResponse(status_code=500, content={"detail": {"reason": str(exc)}})
        return {"data": data}

    return app


app = create_app()
