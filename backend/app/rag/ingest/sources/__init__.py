from pathlib import Path

from app.rag.core.ports import DocSource
from app.rag.ingest.sources.dir import DirSource
from app.rag.ingest.sources.git import GitSource

__all__ = ["DirSource", "GitSource", "make_source"]


def make_source(location: str, branch: str, subdir: str, cache_dir: Path) -> DocSource:
    local = Path(location.removeprefix("dir:"))
    if location.startswith("dir:") or local.is_dir():
        return DirSource(local / subdir if subdir else local)
    return GitSource(location, branch, subdir, cache_dir)
