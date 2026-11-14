import re

import jieba
from jieba.analyse import TFIDF

_WORDS = re.compile(r"[\w]+", re.UNICODE)
_STOP_WORDS = frozenset(TFIDF.STOP_WORDS) | {"的", "了", "是"}


def search_text(raw: str) -> str:
    """Use one tokenizer for documents and queries; preserve frequency for BM25."""
    return " ".join(
        word for segment in jieba.cut(raw.lower())
        for word in _WORDS.findall(segment) if word not in _STOP_WORDS
    )
