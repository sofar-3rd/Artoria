import asyncio
import hashlib
from pathlib import Path

from app.rag.core.errors import SourceUnavailable
from app.rag.core.types import Snapshot
from app.rag.ingest.loaders import SUPPORTED_EXTENSIONS


def scan(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise SourceUnavailable(f"source directory not found: {root}")
    files: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or any(part.startswith(".") for part in rel.parts):
            continue
        if p.suffix.lower() in SUPPORTED_EXTENSIONS:
            files[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return files


class DirSource:
    def __init__(self, root: Path):
        self.root = Path(root)

    async def snapshot(self) -> Snapshot:
        files = await asyncio.to_thread(scan, self.root)
        digest = hashlib.sha256(repr(sorted(files.items())).encode()).hexdigest()
        return Snapshot(
            revision=f"dir:{digest[:16]}",
            files=files,
            reader=lambda rel: (self.root / rel).read_bytes(),
        )
