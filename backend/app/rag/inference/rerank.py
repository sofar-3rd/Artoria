from pathlib import Path

from app.rag.inference.compute import run_cpu

MAX_LENGTH = 512  # the model's limit for the query plus the passage; longer input is truncated silently


class BgeReranker:
    """Relevance scores in [0, 1] from the BAAI/bge-reranker-v2-m3 cross-encoder."""

    def __init__(self, model_dir: str, device: str = "cpu", batch_size: int = 16):
        self._path = Path(model_dir)
        self._device = device
        self._batch_size = batch_size
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from sentence_transformers import CrossEncoder  # heavy import, loaded on first use

            self._model = CrossEncoder(
                str(self._path),
                device=self._device,
                max_length=MAX_LENGTH,
                activation_fn=torch.nn.Sigmoid(),
            )
        return self._model

    def _score(self, query: str, docs: list[str]) -> list[float]:
        scores = self._load().predict(
            [(query, doc) for doc in docs],
            batch_size=self._batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [float(s) for s in scores]

    async def rerank(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        return await run_cpu(self._score, query, docs)

    async def warm_up(self) -> None:
        await run_cpu(self._load)
