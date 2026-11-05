import io
from pathlib import PurePosixPath

from app.rag.core.errors import EmptyDocument
from app.rag.core.types import LoadedDoc


def load_pdf(path: str, raw: bytes) -> tuple[LoadedDoc, str]:
    from markitdown import MarkItDown  # heavy import, keep lazy

    text = MarkItDown().convert_stream(io.BytesIO(raw), file_extension=".pdf").markdown
    if not text.strip():
        raise EmptyDocument(path)
    return LoadedDoc(title=PurePosixPath(path).stem, markdown=text), ""
