import hashlib
import math
import re


def _vec(text: str, dim: int) -> list[float]:
    v = [0.0] * dim
    for tok in re.findall(r"\w+|[\u4e00-\u9fff]", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class HashEmbedder:
    model = "hash-test"

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.calls = 0

    async def embed_documents(self, texts):
        self.calls += len(texts)
        return [_vec(t, self.dim) for t in texts]

    async def embed_query(self, text):
        return _vec(text, self.dim)


class TableEmbedder:
    model = "table-test"

    def __init__(self, mapping: dict[str, list[float]], dim: int):
        self.mapping, self.dim = mapping, dim

    async def embed_documents(self, texts):
        return [self.mapping[t] for t in texts]

    async def embed_query(self, text):
        return self.mapping[text]


class FailingReranker:
    async def rerank(self, query, docs):
        raise RuntimeError("rerank down")


class ReverseReranker:
    async def rerank(self, query, docs):
        n = len(docs)
        return [(i + 1) / n for i in range(n)]  # later docs score higher


class KeywordReranker:
    async def rerank(self, query, docs):
        q = set(query)
        return [len(q & set(d)) / max(len(q), 1) for d in docs]
