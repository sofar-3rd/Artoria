from pathlib import Path

from app.rag.inference.compute import run_cpu


class BgeM3Embedder:
    """Dense embeddings from BAAI/bge-m3 (1024 dimensions, normalised for cosine distance)."""

    model = "BAAI/bge-m3"
    dim = 1024

    def __init__(self, model_dir: str, device: str = "cpu", batch_size: int = 16):
        self._path = Path(model_dir)
        self._device = device
        self._batch_size = batch_size
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, loaded on first use

            self._model = SentenceTransformer(str(self._path), device=self._device)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._load().encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in row] for row in vectors]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await run_cpu(self._encode, texts)

    async def embed_query(self, text: str) -> list[float]:
        # bge-m3 needs no instruction prefix for queries.
        return (await self.embed_documents([text]))[0]

    async def warm_up(self) -> None:
        """Load the model now (on the inference thread) instead of on the first query."""
        await run_cpu(self._load)
