"""One worker thread for model inference.

Embedding and reranking are CPU/GPU bound. Running them on the event loop would freeze every SSE chat
stream, and running several torch calls at once only makes them fight for the same cores, so all
inference goes through a single worker thread.
"""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-inference")


async def run_cpu(fn: Callable[..., T], *args: Any) -> T:
    """Run `fn(*args)` on the inference thread and await the result; exceptions propagate."""
    return await asyncio.get_running_loop().run_in_executor(_executor, fn, *args)
