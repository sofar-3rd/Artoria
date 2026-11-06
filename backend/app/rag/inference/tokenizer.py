from collections.abc import Callable
from pathlib import Path


def make_token_counter(model_dir: str) -> Callable[[str], int]:
    """Count tokens exactly as the embedding model sees them (the bge-m3 tokenizer).

    The chunker sizes chunks in tokens, and the reranker silently truncates at 512 tokens, so the count has
    to come from the same tokenizer as the models rather than from a characters-per-token guess.
    The tokenizer is loaded on first use, so building the counter is free.
    """
    path = Path(model_dir)
    loaded: dict[str, object] = {}

    def count(text: str) -> int:
        tok = loaded.get("tok")
        if tok is None:
            from transformers import AutoTokenizer  # heavy import, kept out of module import time

            tok = loaded["tok"] = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
        return len(tok.encode(text, add_special_tokens=False, truncation=False, verbose=False))

    return count
