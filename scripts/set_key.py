"""把真实 DashScope Key 写入 .env（替换或新增 DASHSCOPE_API_KEY 行）。

用法：
  python scripts/set_key.py
粘贴 Key 后回车即可（输入不回显），避免手改 .env 出错。
"""
from __future__ import annotations

import re
import sys
from getpass import getpass
from pathlib import Path


def main() -> None:
    key = getpass("粘贴你的 DashScope API Key（sk-...），粘贴后回车: ").strip()
    if not key:
        print("[FAIL] 未输入任何内容")
        sys.exit(1)
    if not key.startswith("sk-") or len(key) < 20:
        print(f"[WARN] 疑似不是有效 Key：长度 {len(key)}、前缀 {key[:6]}，请确认粘贴完整")

    env_path = Path(__file__).resolve().parents[1] / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    for ln in lines:
        if re.match(r"^\s*DASHSCOPE_API_KEY=", ln):
            out.append(f"DASHSCOPE_API_KEY={key}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"DASHSCOPE_API_KEY={key}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"[OK] 已写入 .env（Key 长度 {len(key)}）")


if __name__ == "__main__":
    main()
