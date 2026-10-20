"""诊断 DashScope Key 与 Base URL 是否匹配。

用你的 Key 依次试 4 个地域的 compatible-mode 端点，打印每个结果，
一次定位 401 到底是「地域不匹配」还是「Key 本身无效/类型错」。

用法：
  python scripts/test_endpoints.py
（Key 从 .env 读取）
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import httpx

from app import config

CANDIDATES = [
    ("华北2·北京(中国)", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("新加坡/国际", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    ("美国·弗吉尼亚", "https://dashscope-us.aliyuncs.com/compatible-mode/v1"),
    ("中国香港", "https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1"),
]


async def main() -> None:
    key = config.DASHSCOPE_API_KEY
    if not key:
        print("[FAIL] .env 里没有 DASHSCOPE_API_KEY")
        sys.exit(1)

    print(f"Key 前缀: {key[:8]}...（共 {len(key)} 字符）")
    if not key.startswith("sk-"):
        print("[WARN] Key 不是 sk- 开头，可能是 RAM AccessKey(LTAI...) 而非百炼 API-KEY")
    print()

    async with httpx.AsyncClient(timeout=15) as client:
        for name, base in CANDIDATES:
            try:
                resp = await client.post(
                    base + "/embeddings",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": "text-embedding-v4", "input": ["hello"]},
                )
                if resp.status_code == 200:
                    data = resp.json()["data"]
                    dim = len(data[0]["embedding"])
                    print(f"[OK]   {name}")
                    print(f"      {base}")
                    print(f"      成功！维度={dim}  ← 把 .env 的 DASHSCOPE_BASE_URL 改成这个地址")
                else:
                    print(f"[{resp.status_code}] {name}")
                    print(f"      {base}")
                    print(f"      {resp.text[:220]}")
            except Exception as exc:
                print(f"[ERR]  {name}")
                print(f"      {base}")
                print(f"      {type(exc).__name__}: {exc}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
