"""向量打包/解包与余弦相似度计算（numpy 可用则用，否则纯 Python 兜底）。"""
from __future__ import annotations

import struct

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:  # pragma: no cover
    np = None
    HAS_NUMPY = False


def pack_vec(vec) -> bytes:
    """把一维向量打包成 float32 字节，用于存 SQLite BLOB。"""
    if HAS_NUMPY:
        return np.asarray(vec, dtype=np.float32).tobytes()
    return struct.pack(f"{len(vec)}f", *[float(x) for x in vec])


def unpack_vec(data: bytes) -> list:
    """从 BLOB 还原成一维 Python list。"""
    if not data:
        return []
    if HAS_NUMPY:
        return np.frombuffer(data, dtype=np.float32).tolist()
    n = len(data) // 4
    return [float(x) for x in struct.unpack(f"{n}f", data)]


def cosine(matrix, query) -> list:
    """matrix: list[list[float]]；query: list[float]。返回每个文档与 query 的余弦分数。"""
    if not matrix:
        return []
    if HAS_NUMPY:
        m = np.asarray(matrix, dtype=np.float32)
        q = np.asarray(query, dtype=np.float32)
        qn = float(np.linalg.norm(q))
        if qn == 0.0:
            return [0.0] * len(m)
        mn = np.linalg.norm(m, axis=1)
        denom = mn * qn
        denom[denom == 0.0] = 1.0
        return (m @ q / denom).tolist()

    import math
    qn = math.sqrt(sum(x * x for x in query)) or 1.0
    out = []
    for row in matrix:
        dot = sum(a * b for a, b in zip(row, query))
        rn = math.sqrt(sum(x * x for x in row)) or 1.0
        out.append(dot / (rn * qn))
    return out
