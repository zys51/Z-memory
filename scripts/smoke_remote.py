"""对已部署的 Add/Search 服务做冒烟自测（模拟官方 Smoke 检查点）。

用法：
  python scripts/smoke_remote.py --url http://公网IP:8080 --key 你的AML_API_KEY

检查点：健康检查 / 鉴权(X-Api-Key、Bearer、错误Key) / Add回显 / 幂等 /
        Search相关性与隔离 / top_k上限 / created_at 存在。
"""
from __future__ import annotations

import argparse
import sys

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="部署服务地址，如 http://1.2.3.4:8080")
    p.add_argument("--key", required=True, help="AML_API_KEY（.env 里配的那个）")
    args = p.parse_args()

    base = args.url.rstrip("/")
    key = args.key
    c = httpx.Client(timeout=30)

    # 1) 健康检查（免鉴权）
    r = c.get(base + "/health")
    check("GET /health 免鉴权 200", r.status_code == 200, f"status={r.status_code}")

    # 2) Add + 回显
    body = {
        "request_id": "smoke-1",
        "messages": [{"role": "user", "content": "My favorite color is blue"}],
        "user_id": "smoke-user",
        "session_id": "s1",
    }
    r = c.post(base + "/add", headers={"X-Api-Key": key}, json=body)
    echo_ok = r.status_code == 200 and r.json().get("request_id") == "smoke-1"
    check("POST /add 回显 request_id", echo_ok, f"status={r.status_code}")

    # 3) 幂等（重复 request_id）
    r = c.post(base + "/add", headers={"X-Api-Key": key}, json=body)
    check("POST /add 幂等(重复成功)", r.status_code == 200 and r.json().get("success") is True, f"status={r.status_code}")

    # 4) Search 相关命中
    r = c.post(
        base + "/search",
        headers={"X-Api-Key": key},
        json={"query": "What is my favorite color", "user_id": "smoke-user", "top_k": 5},
    )
    data = r.json().get("data", []) if r.status_code == 200 else []
    hit = any("blue" in (d.get("content", "").lower()) for d in data)
    check("POST /search 相关命中", hit, f"count={len(data)}")

    # 5) user_id 隔离
    r = c.post(
        base + "/search",
        headers={"X-Api-Key": key},
        json={"query": "favorite color", "user_id": "other-user", "top_k": 5},
    )
    iso = r.status_code == 200 and r.json().get("data", []) == []
    check("user_id 隔离(他人为空)", iso)

    # 6) 错误 Key → 401
    r = c.post(base + "/add", headers={"X-Api-Key": "wrong-key"}, json=body)
    check("错误 Key 返回 401", r.status_code == 401, f"status={r.status_code}")

    # 7) Bearer 鉴权
    r = c.post(
        base + "/add",
        headers={"Authorization": "Bearer " + key},
        json={"request_id": "smoke-2", "messages": [{"role": "user", "content": "I like coffee"}], "user_id": "smoke-user2", "session_id": "s1"},
    )
    check("Bearer 鉴权可用", r.status_code == 200, f"status={r.status_code}")

    # 8) top_k 上限 100
    r = c.post(
        base + "/search",
        headers={"X-Api-Key": key},
        json={"query": "blue", "user_id": "smoke-user", "top_k": 1000},
    )
    data = r.json().get("data", []) if r.status_code == 200 else []
    check("top_k 上限 100", len(data) <= 100, f"count={len(data)}")

    # 9) created_at 存在
    check("created_at 字段存在", all(d.get("created_at") for d in data) if data else True)

    c.close()

    # 汇总
    print()
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")
    npass = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{npass}/{len(CHECKS)} 通过")
    if npass != len(CHECKS):
        print("存在失败项，请先修复再提交官方 Smoke。")
        sys.exit(1)
    print("冒烟自测全部通过，可以提交官方评测了。")


if __name__ == "__main__":
    main()
