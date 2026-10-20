"""验证阿里云 DashScope text-embedding-v4 可用性。

用法：
  $env:DASHSCOPE_API_KEY="sk-xxxx"     # Windows PowerShell
  python scripts/test_embedding.py

成功会打印嵌入维度；失败会给出错误信息。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app import config
from app.embedder import Embedder


async def main() -> None:
    key = config.DASHSCOPE_API_KEY  # 优先读 .env / 环境变量（config 已 load_dotenv）
    if not key:
        print("[FAIL] 未找到 DASHSCOPE_API_KEY")
        print("  请在 .env 里填入: DASHSCOPE_API_KEY=sk-xxxx")
        sys.exit(1)

    embedder = Embedder(api_key=key)
    try:
        vecs = await embedder.embed(
            ["Hello, world!", "The weather is nice today."], text_type="document"
        )
    except Exception as exc:
        print(f"[FAIL] 调用失败：{type(exc).__name__}: {exc}")
        print("  请检查：Key 是否正确、是否已开通 Model Studio、Base URL 是否可达")
        sys.exit(1)

    if embedder.offline:
        print("[FAIL] 仍处于离线回退模式，Key 未生效")
        sys.exit(1)

    print(f"[OK] 成功：嵌入 {len(vecs)} 条文本，维度={len(vecs[0])}，模型={embedder.model}")


if __name__ == "__main__":
    asyncio.run(main())
