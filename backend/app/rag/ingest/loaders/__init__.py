from pathlib import PurePosixPath

from app.rag.core.types import LoadedDoc
from app.rag.ingest.loaders.markdown import load_markdown
from app.rag.ingest.loaders.pdf import load_pdf

SUPPORTED_EXTENSIONS = (".md", ".pdf")


def load_with_meta(path: str, raw: bytes) -> tuple[LoadedDoc, str]:
    ext = PurePosixPath(path).suffix.lower()
    if ext == ".md":
        return load_markdown(path, raw)
    if ext == ".pdf":
        return load_pdf(path, raw)
    raise ValueError(f"unsupported file type: {ext or path}")


def load(path: str, raw: bytes) -> LoadedDoc:
    return load_with_meta(path, raw)[0]
