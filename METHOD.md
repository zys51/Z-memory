# 方法说明（Method Description）

> 本文档用于比赛提交的「方法 · 论文 · 仓库」披露与复现核验。
> 系统名：Hybrid-Mem（BM25 + text-embedding-v4 + RRF 混合检索记忆系统）

---

## 0. 概述

一个符合 Agent Memory Leaderboard（AML）'Add/Search' 契约的轻量记忆检索服务：写入时把对话切块并建立「关键词（BM25）+ 语义向量（text-embedding-v4）」双索引；检索时混合两路信号经 RRF 融合，辅以时间感知排序，返回最相关、自包含的原始证据片段供平台统一生成答案。

---

## 1. 参赛赛道与组别

- 赛道：文本
- 组别：开源方法榜 / 学术榜
- 模型合规：
  - Embedding：'text-embedding-v4'（阿里云 DashScope，OpenAI 兼容接口）✅ 符合规则
  - LLM 组件：**未使用**（检索不调用任何 LLM）✅ 规避 gpt-4o-mini 依赖
  - Reranker：**未使用**

---

## 2. 架构总览

```
平台调用
   │  POST /add          POST /search
   ▼                     ▼
┌─────────────────────────────────────────────┐
│ FastAPI (app/main.py)  ·  鉴权 X-Api-Key/Bearer/T
oken │
└─────────────────────────────────────────────┘
   │                     │
   ▼                     ▼
MemoryEngine (app/engine.py)
   ├─ Add：切块 → text-embedding-v4 → 落库 + 双索引
   └─ Search：BM25 + 稠密余弦 → RRF 融合 → 时间感知 → top_k
        │
        ├─ Storage (app/store.py)      SQLite（行存储 + request_id 幂等）
        ├─ BM25 (app/bm25.py)          纯 Python 稀疏索引
        └─ Embedder (app/embedder.py)  text-embedding-v4 客户端
```

---

## 3. 记忆写入（Add）

1. 接收 `{request_id, messages, user_id, session_id}`。
2. **幂等**：`request_id` 命中已处理表则直接返回成功，不重复写入。
3. **切块**：按句子聚合、每块 ≤800 字符，长块按空格硬切；保留块级时间戳（支持消息自带 `created_at`/`timestamp`，否则用到达时间）。
4. **嵌入**：每块调 `text-embedding-v4` 得文档向量（批量、同步完成）。
5. **落库**：原始块 + ISO-8601 `created_at` + float32 向量写入 SQLite；**落库成功后才标记 request_id 已处理**（失败可由平台安全重试）。
6. **同步返回**：持久化与索引完成后才回显 `{success, request_id, user_id, session_id}`。

---

## 4. 记忆检索（Search）

1. 查询文本 → `text-embedding-v4` 查询向量。
2. **双路召回**（仅在该 `user_id` 命名空间内）：
   - 稀疏：BM25（Okapi）关键词打分；
   - 稠密：查询向量与所有块向量的余弦相似度。
3. **相关性门控（abstain）**：BM25 命中 或 余弦 ≥ 阈值（默认 0.15）才算候选；否则返回空数组 `{"data": []}`，避免硬凑低质结果（对齐「认知安全/稳健拒答」）。
4. **RRF 融合**：对稠密、稀疏两路排序做 Reciprocal Rank Fusion；排序键为 `(分数, 时间戳)`，分数相同时更近优先。
5. **时间感知**：查询含「现在/最近/最新/当前」等信号时，给更近记忆加一个有界加分（权重 0.5，相关性仍主导）。
6. 返回 `{"data": [{id, content, created_at}]}`，相关度降序、≤ `top_k`（上限 100）。

---

## 5. 关键工程细节

| 关注点 | 实现 |
|---|---|
| user_id 隔离 | 检索只在 `WHERE user_id = ?` 内进行，绝不跨用户 |
| 幂等 | `processed` 表唯一键 + 二次检查（并发安全） |
| 同步语义 | Add 完成后才返回 200 |
| 时间戳 | 统一 ISO-8601；兼容 Unix 毫秒/秒/ISO 输入 |
| 失败重试 | 嵌入/落库失败不标记已处理，平台可重试 |
| 并发 | asyncio 锁保护索引读写；网络调用在锁外 |

---

## 6. 复现方式

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # 填 DASHSCOPE_API_KEY（text-embedding-v4）
python run.py           # 监听 0.0.0.0:8080
# 契约测试：pip install -r requirements-dev.txt && python -m pytest tests -v  （14 个用例）
```

---

## 7. 局限与后续（已知改进方向）

- 未使用 LLM 做事实抽取/记忆压缩/冲突消解，治理能力（D 维度）主要靠时间感知 + 平台 Answer 模型「prefer most recent」。
- 未引入 reranker（规则允许），如 `bge-reranker-v2-m3` 可进一步提精排质量（可后续加入，需 `ENABLE_RERANK=1`）。
- 多跳组合（B 维度）依赖返回多个互补证据块 + Answer 模型推理，尚未做显式关系图。
