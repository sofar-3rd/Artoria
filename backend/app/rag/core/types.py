from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Chunk:
    idx: int
    heading_path: str
    content: str  # shown to the model (fences repaired)
    index_text: str  # embedded and tokenized: "title > heading_path\ncontent"
    start: int  # char range in the original markdown
    end: int


@dataclass(frozen=True)
class ChunkedDoc:
    title: str
    chunks: list[Chunk]


@dataclass(frozen=True)
class LoadedDoc:
    title: str
    markdown: str


@dataclass(frozen=True)
class Snapshot:
    revision: str
    files: dict[str, str]  # path -> sha256 of raw bytes
    reader: Callable[[str], bytes] = field(repr=False)
    # Files the source refused to list (for example larger than the size limit): path -> reason.
    skipped: dict[str, str] = field(default_factory=dict)

    def read(self, path: str) -> bytes:
        return self.reader(path)


@dataclass(frozen=True)
class Hit:
    kb: str
    doc_id: str
    path: str
    title: str
    heading_path: str
    start: int
    end: int
    doc_chars: int
    content: str
    score: float
    reranked: bool = False


@dataclass(frozen=True)
class SearchResult:
    hits: list[Hit]
    reranked: bool


@dataclass(frozen=True)
class KbInfo:
    name: str
    description: str
    doc_count: int
    synced_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class DocInfo:
    doc_id: str
    path: str
    title: str
    chars: int


@dataclass(frozen=True)
class DocPage:
    doc_id: str
    path: str
    title: str
    text: str
    offset: int
    total_chars: int
    has_more: bool


@dataclass(frozen=True)
class SyncReport:
    revision: str
    added: int
    changed: int
    removed: int
    unchanged: int
    failed: list[tuple[str, str]] = field(default_factory=list)
    # Files that were not indexed on purpose (size limit). They are warnings: they never block mark_synced.
    skipped: list[tuple[str, str]] = field(default_factory=list)
