"""纯 Python BM25（Okapi）稀疏检索，无外部依赖。评测数据为英文，按词元切分即可。"""
from __future__ import annotations

import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_tf: list[dict[str, int]] = []  # 每个文档的词频表
        self.doc_len: list[int] = []
        self.df: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.n = 0
        self.avgdl = 0.0
        self._finalized = False

    def add(self, tokens: list[str]) -> None:
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        self.doc_tf.append(tf)
        self.doc_len.append(len(tokens))
        self.n += 1
        for t in tf:
            self.df[t] = self.df.get(t, 0) + 1
        self._finalized = False

    def finalize(self) -> None:
        if self._finalized:
            return
        self.avgdl = sum(self.doc_len) / max(1, self.n)
        for t, df in self.df.items():
            self.idf[t] = math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))
        self._finalized = True

    def scores(self, query_tokens: list[str]) -> list[float]:
        """返回每个文档的 BM25 分数（与 add 顺序一致）。"""
        self.finalize()
        scores = [0.0] * self.n
        k1, b = self.k1, self.b
        for t in set(query_tokens):
            idf = self.idf.get(t, 0.0)
            if idf == 0.0:
                continue
            for i, tf in enumerate(self.doc_tf):
                f = tf.get(t, 0)
                if not f:
                    continue
                dl = self.doc_len[i]
                denom = f + k1 * (1.0 - b + b * dl / max(1.0, self.avgdl))
                scores[i] += idf * (f * (k1 + 1.0)) / denom
        return scores

    def top_indices(self, query_tokens: list[str], k: int) -> list[int]:
        """返回分数 > 0 的文档下标，按分数降序，最多 k 个。"""
        sc = self.scores(query_tokens)
        order = sorted(range(len(sc)), key=lambda i: sc[i], reverse=True)
        return [i for i in order if sc[i] > 0.0][:k]
