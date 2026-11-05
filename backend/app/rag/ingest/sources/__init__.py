from pathlib import Path

from app.rag.core.ports import DocSource
from app.rag.ingest.sources.dir import DirSource, resolve_subdir
from app.rag.ingest.sources.git import GitSource

__all__ = ["DirSource", "GitSource", "make_source"]


def make_source(location: str, branch: str, subdir: str, cache_dir: Path) -> DocSource:
    location = location.strip()
    path_part = location.removeprefix("dir:").strip()
    if not path_part:
        raise ValueError("repo_url must not be empty")
    local = Path(path_part)
    if location.startswith("dir:") or local.is_dir():
        return DirSource(resolve_subdir(local, subdir))
    return GitSource(location, branch, subdir, cache_dir)
