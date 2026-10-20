# Z memory

一个符合 Agent Memory Leaderboard（AML）`Add/Search` 契约的轻量记忆检索服务。

- **写入（Add）**：把对话切块，用 `text-embedding-v4` 建向量索引，同时维护 BM25 关键词索引。
- **检索（Search）**：稠密 + 稀疏双路召回，经 RRF 融合并按时间感知排序，返回原始证据片段（不生成最终答案）。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # 填 DASHSCOPE_API_KEY（text-embedding-v4）
python run.py                    # 监听 0.0.0.0:8080
```

## 接口

- `POST /add` — 写入记忆（同步持久化、`request_id` 幂等）
- `POST /search` — 检索证据（`user_id` 严格隔离，`top_k` ≤ 100）

## 测试

```bash
pip install -r requirements-dev.txt
python -m pytest tests -v       # 15 个契约测试
```

## 方法说明

详见 [METHOD.md](METHOD.md)。
