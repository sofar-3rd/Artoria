"""Input hygiene shared by the model adapters.

Two limits, both from measurements on the target machine (bge-m3 accepts 8192 tokens and attention cost
grows quadratically): a 2,000-character text takes 0.3 s, 4,000 characters 0.8 s, 8,000 characters 4.8 s.
Everything runs on ONE inference thread, so one oversized input delays every other request.
"""

# A search question is never this long; anything beyond it adds latency, not relevance.
MAX_QUERY_CHARS = 2000
# Document text is already bounded to 512 tokens by the chunker (the longest index_text of the real documents
# is ~2,100 characters); this is only a safety net for text that bypasses the chunker.
MAX_DOCUMENT_CHARS = 8000


def clean(text: str, limit: int = MAX_DOCUMENT_CHARS) -> str:
    """Make `text` safe for the tokenizer: no lone surrogates (a bare TypeError otherwise), bounded length."""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")[:limit]
