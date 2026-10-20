"""集中读取环境变量配置。"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # python-dotenv 未安装也不影响
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# 评测 Key（平台调用我方接口时携带的鉴权密钥）。为空 = 本地开发不鉴权。
AML_API_KEY = _env("AML_API_KEY")

# 阿里云 DashScope（text-embedding-v4）配置
DASHSCOPE_API_KEY = _env("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL = _env("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBED_MODEL = _env("EMBED_MODEL", "text-embedding-v4")
# 0 = 使用模型默认维度；正整数 = 显式指定维度（text-embedding-v4 支持 dimensions 参数）
EMBED_DIM = int(_env("EMBED_DIM", "1024") or 0)
EMBED_BATCH = int(_env("EMBED_BATCH", "10") or 10)
EMBED_TIMEOUT = float(_env("EMBED_TIMEOUT", "30") or 30)
# 稠密检索的相关性门槛：余弦相似度低于该值视为不相关（用于无证据时返回空，避免硬凑）
DENSE_THRESHOLD = float(_env("DENSE_THRESHOLD", "0.15") or 0.15)

# 存储
DB_PATH = _env("DB_PATH", "data/memories.db")

# 重排（可选，v1 默认关闭）
ENABLE_RERANK = _env("ENABLE_RERANK", "0").lower() in {"1", "true", "yes"}

# 服务
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8080") or 8080)
TOP_K_MAX = 100
# 内存中最多缓存的用户索引数（LRU 淘汰，超出后从 SQLite 重新加载，控制内存占用）
MAX_CACHED_USERS = int(_env("MAX_CACHED_USERS", "32") or 32)
