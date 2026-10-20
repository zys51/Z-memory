"""本地召回质量评估 harness。

把每条「历史」写入记忆，再用「问题」检索，判断 gold 答案的关键词是否命中 top-k 结果。
可用离线 hash 嵌入跑通流程；接入真实嵌入时把 embedder 的 api_key 换成 DashScope key 即可。

用法：
  python scripts/eval_recall.py --data data/sample_eval.jsonl --top-k 10

数据格式（JSONL，每行一条）：
  {"history":[{"role":"user","content":"..."}, ...], "question":"...", "gold":"..."}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app import config
from app.bm25 import tokenize
from app.embedder import Embedder
from app.engine import MemoryEngine
from app.store import Storage

_STOPS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "be", "been", "do", "does", "did", "i", "you", "he", "she",
    "it", "we", "they", "me", "my", "your", "his", "her", "its", "our", "their",
    "what", "which", "who", "when", "where", "how", "why", "that", "this",
    "am", "at", "as", "by", "from", "with", "about", "also", "so", "but",
}


def key_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in _STOPS]


def hit(tokens: list[str], chunk: str) -> bool:
    ct = set(tokenize(chunk))
    return bool(tokens) and all(t in ct for t in tokens)


async def run(data_path: str, top_k: int, dim: int, db_path: str, offline: bool) -> None:
    # 清理上次评测的临时库，避免残留旧维度向量导致维度不匹配
    for p in (Path(db_path), Path(db_path + "-wal"), Path(db_path + "-shm")):
        if p.exists():
            p.unlink()
    storage = Storage(db_path)
    api_key = "" if offline else config.DASHSCOPE_API_KEY
    embedder = Embedder(api_key=api_key, dim=dim)
    engine = MemoryEngine(storage, embedder)

    total = 0
    hit_at_k = {k: 0 for k in (1, 5, 10, top_k)}
    per_record: list[dict] = []

    for line in Path(data_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        history = rec.get("history", [])
        question = rec["question"]
        gold = rec.get("gold", "")
        gt = key_tokens(gold)

        user = f"eval-u{total}"
        await engine.add(user, "s1", f"req-{total}", history)
        results = await engine.search(user, question, top_k)
        total += 1

        ok = {k: any(hit(gt, r["content"]) for r in results[:k]) for k in hit_at_k}
        for k, v in ok.items():
            if v:
                hit_at_k[k] += 1
        per_record.append({"question": question, "gold": gold, "top1": results[0]["content"] if results else ""})

    mode = "offline hash embed" if offline else f"real embed ({embedder.model})"
    print(f"records={total} top_k={top_k} dim={dim} ({mode})")
    for k in sorted(hit_at_k):
        print(f"  recall@{k}: {hit_at_k[k]}/{total} = {hit_at_k[k] / max(1, total):.2%}")

    print("\n--- 逐条 top1（抽查） ---")
    for r in per_record[:20]:
        print(f"  Q: {r['question']!r}  gold={r['gold']!r}  top1={r['top1']!r}")

    storage.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/sample_eval.jsonl")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--dim", type=int, default=0)  # 0 = 用模型默认维度
    p.add_argument("--db", default="data/eval_tmp.db")
    p.add_argument("--offline", action="store_true", help="用离线 hash 嵌入（无需 Key）")
    args = p.parse_args()
    asyncio.run(run(args.data, args.top_k, args.dim, args.db, args.offline))


if __name__ == "__main__":
    main()
