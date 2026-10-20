# Agent Memory Challenge 2026 · 参赛执行方案

> 本文件是**唯一执行依据**。后续所有操作（写代码、部署、评测、提交）都照本文档执行。
> 目标：文本赛道 · 开源方法榜（学术榜），走完 Add/Search 服务 → 部署 → Smoke → Full → 提交材料全流程。

---

## 0. 一句话目标

写一个符合 AML 官方 `Add/Search` 契约的记忆检索服务，部署到公网，通过 Smoke 后跑 1 次 Full 评测，并在截止日前提交开源仓库与材料。

---

## 1. 关键结论与时间线

| 项目 | 值 |
|---|---|
| 今天日期 | 2026-10-19 |
| 材料提交截止 | **2026-10-31 23:59（UTC+8）** |
| 评测停止 | **2026-11-04 23:59（UTC+8）** |
| 公榜 | 11 月中旬 |
| 可用时间 | **约 12 天** |
| Full 次数 | 每 Key 每赛道最多 2 次，第 2 次须在首次完成后满 30 天 → **实际只有 1 次 Full** |
| 评测 Key 发放 | 申请后**次日 19:00 前**发放 → 必须尽早申请 |

**核心结论：只有 1 次 Full 机会，务必 Smoke + 本地验证全部通过后再投。**

---

## 2. 已确认的参赛定位（用户已拍板）

- **赛道**：文本（6000+ 实例、32 数据源、公开基准最全、最易迭代）
- **组别**：开源方法榜 / 学术榜（可参与 ¥15 万奖金池）
- **部署**：阿里云（轻量服务器 / 学生机 / 新用户特价档，到 Phase 3 再选具体档位）
- **模型约束（学术榜硬性规则）**：
  - Embedding **必须**用 `text-embedding-v4`（阿里云 DashScope，OpenAI 兼容接口）
  - LLM 组件**若使用必须**用 `gpt-4o-mini`（v1 刻意不用，规避依赖）
  - Reranker **不限**（可用免费的 `bge-reranker-v2-m3`）

---

## 3. 比赛规则要点（必须遵守）

1. **必须自行托管 Add/Search API**，不接受"仅提交仓库由平台代部署"（第二期新规）。
2. **Search 不得生成最终答案**，只返回检索到的记忆证据；答案由平台固定模型（gpt-4o-mini, temperature 0）生成。
3. **不得**硬编码公开题目、**不得**跨样本共享状态。
4. **user_id 是唯一检索隔离边界**：Search 绝不能返回其他 user_id 的数据。
5. **Add 必须同步**：内容存储并完成索引后才返回 200，不能"已接收稍后处理"。
6. **request_id 幂等**：同一 request_id 重复调用不得产生重复记忆。
7. 需提供公开 GitHub 仓库 + 固定 commit + 方法说明 + API 运行日志（供版本审计）。
8. 嵌入模型必须 `text-embedding-v4`；LLM 组件必须 `gpt-4o-mini`；Reranker 不限。

---

## 4. 接口契约（Add/Search）

> 依据：官方公开打分管线 + 第三方 AML 适配器交叉验证。部署前会再用官方 api-guide 复核一次。

### 健康检查
- `GET /health`（或 `/`、`/v1/health`）→ 免鉴权返回 2xx，如 `{"ok": true}`

### 写入记忆
- `POST /add`（或 `/v1/add`）
- 请求体 JSON：
  ```json
  {
    "request_id": "string",
    "messages": [{"role": "user|assistant|...", "content": "string", "created_at"?/ "timestamp"?: "..."}],
    "user_id": "string",
    "session_id": "string"
  }
  ```
- 响应（**同步持久化完成后**才返回）：
  ```json
  {"success": true, "request_id": "...", "user_id": "...", "session_id": "..."}
  ```
  - 必须**原样回显** `request_id` / `user_id` / `session_id`。
  - 同一 `request_id` 重复调用：跳过写入，直接返回 success（幂等）。

### 检索证据
- `POST /search`（或 `/v1/search`）
- 请求体 JSON：
  ```json
  {"query": "string", "user_id": "string", "top_k": 100}
  ```
- 响应：
  ```json
  {"data": [{"id": "...", "content": "...", "created_at": "ISO-8601"}]}
  ```
  - 按**相关度降序**排列；最多返回 `top_k` 条（正式上限 100）。
  - 无相关证据可返回 `{"data": []}`（abstain，宁可少不硬凑）。
  - **只返回该 user_id 的记忆**。

### 鉴权
- 支持 `X-Api-Key: <key>` / `Authorization: Bearer <key>` / `Authorization: Token <key>`。
- Key 由环境变量 `AML_API_KEY` 配置（与评测 Key 对应）。

### 时间戳
- 统一 ISO-8601 的 `created_at`；支持 Unix 毫秒时间戳输入并规范化。

---

## 5. 原方案的两处修正（重要）

1. **「MemForge Classic」脚手架不存在**（疑为模型幻觉，GitHub 查无此物）。
   - 真实相关仓库：官方 [AML-memory/agent-memory-leaderboard](https://github.com/AML-memory/agent-memory-leaderboard)（只有评测合约+公开打分管线，非脚手架）；第三方 [LeslieWylie/repository-memory](https://github.com/LeslieWylie/repository-memory)（AML 适配器，可作接口参考，但走第一期"平台代部署"旧路线）。
   - **决定：自己写一个轻量服务**（几百行），更可控、更利于开源披露。
2. **"嵌入换成 bge-m3" 会违规**。学术榜 Embedding 必须 `text-embedding-v4`，bge-m3 会被判违规。
   - **决定：嵌入用 `text-embedding-v4`**；Reranker 才可用 bge（免费、不限）。

---

## 6. 技术架构（v1，稳字优先）

- **Web 框架**：FastAPI + Uvicorn（异步，高并发处理平台请求）
- **存储**：SQLite（行存原始记忆块；启动时重建索引）
- **稀疏检索**：纯 Python BM25（自实现，避免 FTS5 原生依赖，数据为英文）
- **稠密检索**：`text-embedding-v4`（DashScope OpenAI 兼容接口；Add 时 embed 文档向量，Search 时 embed 查询向量）
- **融合**：RRF（Reciprocal Rank Fusion）合并稠密 + 稀疏排序
- **重排（可选）**：`bge-reranker-v2-m3`（默认关闭，可配置开启）
- **记忆治理**：消息切块 → 原始块存储 → 时间戳排序 → 时间感知排序（更近优先的平局打破）→ `request_id` 幂等

### 对齐官方 8 个能力维度的策略
| 维度 | 策略 |
|---|---|
| A 显式事实召回 | BM25 关键词 + 原文块（保留具体名称/时间/地点） |
| B 关系与多跳 | Search 返回多个互补证据块（top_k 放大，不止 top1） |
| C 时间与事件序列 | created_at 排序 + 时间敏感查询加「更近优先」信号 |
| D 记忆治理 | 排序平局时更近者优先；冲突由平台 Answer 模型按最新取用 |
| E 个性化 | 用户偏好事实层（句子级） |
| G 规则/流程 | 原文块 + 格式约束保留 |
| H 安全/隐私 | 严格 user_id 隔离、无证据返回空数组（abstain） |

---

## 7. 项目目录结构

```
memcomp/
├── README.md                 # 本文件（执行依据）
├── DEPLOY.md                 # 部署操作手册（Phase 3 照此执行）
├── METHOD.md                 # 方法说明（Phase 5 提交材料，已起草）
├── GITHUB.md                 # GitHub 仓库搭建指南（部署 + 提交用）
├── requirements.txt          # 运行依赖
├── requirements-dev.txt      # 运行依赖 + pytest
├── Dockerfile                # 容器化部署
├── .env.example              # 环境变量模板（复制为 .env）
├── conftest.py               # pytest 路径配置
├── run.py                    # 启动入口：python run.py
├── deploy.sh                 # 服务器一键部署脚本（Phase 3 用）
├── app/
│   ├── __init__.py
│   ├── config.py             # 读取环境变量配置
│   ├── vector_utils.py       # 向量打包/余弦相似度（numpy 或纯 Python）
│   ├── bm25.py               # 纯 Python BM25 索引
│   ├── store.py              # SQLite 存储 + 幂等 + user_id 隔离
│   ├── embedder.py           # text-embedding-v4 客户端（含离线 hash 回退）
│   ├── engine.py             # 切块 + 混合检索 + RRF 融合 + 相关性阈值
│   └── main.py               # FastAPI：/health /add /search + 鉴权
├── scripts/
│   ├── eval_recall.py        # 本地召回率评测 harness（Phase 2）
│   └── test_embedding.py     # 验证 DashScope text-embedding-v4 Key
└── tests/
    └── test_contract.py      # 契约测试（鉴权/幂等/隔离/top_k/时间戳/abstain）
```

> 说明：Reranker（bge-reranker）目前**预留了 `ENABLE_RERANK` 开关但未实现**，v1 先用「BM25 + 稠密 + RRF」即可，Phase 2 视效果决定是否加入。

---

## 8. 执行步骤（照此执行）

### Phase 0 — 拍板（已完成）
- [x] 赛道：文本 + 开源方法榜
- [x] 部署：阿里云（Phase 3 再选档位）
- [x] 账号：无阿里云账号，需注册（注册+实名+开通 Model Studio，约 10–30 分钟；学生可做学生认证）

### Phase 1 — 写服务 + 契约测试（✅ 已完成）
- [x] 搭好依赖（`requirements.txt` / `requirements-dev.txt`）
- [x] 实现 `store.py`（SQLite + 幂等 + 隔离）
- [x] 实现 `bm25.py`（纯 Python BM25）
- [x] 实现 `embedder.py`（DashScope + 离线 hash 回退）
- [x] 实现 `engine.py`（切块 + 混合检索 + RRF + 阈值门控）
- [x] 实现 `main.py`（/health /add /search + 鉴权 + 时间戳）
- [x] 跑通 `tests/test_contract.py`（**15/15 通过**）
- [x] 写 `Dockerfile` / `.env.example` / `run.py`
- [x] 真实 HTTP 冒烟通过（uvicorn → /health → /add → /search）

### Phase 2 — 本地测检索质量并迭代
- [ ] 下载公开子集（LoCoMo / PersonaMem 公开数据；已定位：LoCoMo=snap-research/locomo、PersonaMem-v2=HF milanow/PersonaMem-v2、LongMemEval=xiaowu0162/LongMemEval）
- [ ] 用官方公开打分管线的 Answer 提示词做本地模拟，测召回质量
- [ ] 调 chunk 策略、RRF 权重、top_k、阈值
- [ ] 实测 text-embedding-v4 的用量与成本

### Phase 3 — 部署上线（详见 `DEPLOY.md`）
- [ ] 用户注册阿里云 + 开通 DashScope（拿 `DASHSCOPE_API_KEY`，用 `scripts/test_embedding.py` 验证）
- [ ] 选定最便宜的轻量服务器档位并购买
- [ ] 上传代码 / 构建镜像 / 启动服务（systemd 常驻）
- [ ] 配置 `AML_API_KEY`、公网 IP、防火墙放行 8080
- [ ] 自测公网 `curl /health /add /search`
- [ ] 在官网提交评测申请（拿评测 Key，次日 19:00 前发）

### Phase 4 — Smoke → Full（1 次机会）
- [ ] 用评测 Key 跑 Smoke，按报错修正
- [ ] Smoke 全绿后，启动 Full
- [ ] 监控进度、保留运行日志

### Phase 5 — 提交材料（10-31 前）
- [ ] 公开 GitHub 仓库 + 固定 commit
- [ ] 方法说明（已起草于 `METHOD.md`，架构、配置、复现方式）
- [ ] 提交 API 运行日志 + 版本信息
- [ ] 等待复核 → 公榜

### 本地运行与测试（在你自己的电脑上执行）

```bash
# 1) 建虚拟环境并装依赖
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt

# 2) 跑契约测试（无需网络，用离线 hash 嵌入，15 个用例）
python -m pytest tests -v

# 3) 本地启动服务（未配 AML_API_KEY / DASHSCOPE_API_KEY 时 = 离线、不鉴权）
python run.py
# 另开终端验证：
#   curl http://127.0.0.1:8080/health
#   curl -X POST http://127.0.0.1:8080/add -H "Content-Type: application/json" -d "{\"request_id\":\"r1\",\"messages\":[{\"role\":\"user\",\"content\":\"I live in Beijing\"}],\"user_id\":\"u1\",\"session_id\":\"s1\"}"
#   curl -X POST http://127.0.0.1:8080/search -H "Content-Type: application/json" -d "{\"query\":\"Where do I live\",\"user_id\":\"u1\",\"top_k\":5}"

# 4) 接入真实嵌入：复制 .env.example 为 .env，填 DASHSCOPE_API_KEY（text-embedding-v4），重启即可
```

---

## 9. 部署与成本

- **唯一硬性外部依赖**：阿里云 DashScope `text-embedding-v4`（按 token 计费；新用户通常有免费额度，Phase 2 实测后给出精确成本）。
- **服务器**：阿里云/腾讯云「轻量应用服务器」学生机/新用户特价档，常见 ¥9~10/月或首年 ¥99 级；2C2G + 40G SSD 足够（v1 不用 reranker 时 2G 内存够，要跑 bge-reranker 选 2C4G）。
- **协同优势**：嵌入与部署同用阿里云账号，调用延迟低、账目统一。
- 免费兜底（不推荐正式 Full）：Render 免费档 / HuggingFace Space（磁盘不持久、冷启动风险）。

---

## 10. 风险与应对

| 风险 | 应对 |
|---|---|
| 时间紧 + 只有 1 次 Full | Smoke 与本地测试是安全网，前置全过再投 |
| 嵌入成本/时长随数据量变化 | Phase 2 实测用量与成本 |
| gpt-4o-mini 组件受 OpenAI 访问限制 | v1 不使用 LLM 组件，规避 |
| 阿里云注册/部署需本人操作 | 涉及账号与支付，由用户本人完成，AI 逐步指导 |

---

## 11. 提交材料 checklist

- [ ] 公开 GitHub 仓库 URL + 固定 commit hash
- [ ] 方法说明文档（架构图 + 配置 + 复现步骤）
- [ ] Add/Search API 地址 + 鉴权说明 + 版本号
- [ ] API 运行日志（供版本审计）
- [ ] 声明嵌入模型 = `text-embedding-v4`、LLM 组件（如用）= `gpt-4o-mini`

---

## 12. 下一步（待办）

1. ✅ Phase 1 已完成：服务代码 + 契约测试（15/15）+ 真实 HTTP 冒烟均通过。
2. **Phase 2（进行中）**：下载公开子集（LoCoMo/PersonaMem），用官方 Answer 提示词做本地召回质量测试并迭代。
3. **用户并行**：注册阿里云账号 + 实名 + 开通 Model Studio（拿 `DASHSCOPE_API_KEY`）。
4. Phase 3 部署时再选服务器档位并购买。
