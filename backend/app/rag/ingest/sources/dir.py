import asyncio
import hashlib
import os
from pathlib import Path

from app.rag.core.errors import SourceUnavailable
from app.rag.core.types import Snapshot
from app.rag.ingest.loaders import SUPPORTED_EXTENSIONS


def resolve_subdir(root: Path, subdir: str) -> Path:
    """Return `root/subdir` for a relative subdir; refuse anything that could leave `root`.

    A leading "/" is treated as "relative to the root" (matching how GitSource always treated it),
    so an absolute filesystem path can never re-root the source.
    """
    clean = subdir.strip().strip("/")
    if not clean:
        return root
    target = root / clean
    if ".." in Path(clean).parts or root.resolve() not in (target.resolve(), *target.resolve().parents):
        raise ValueError("subdir must stay inside the knowledge base root and must not contain '..'")
    return target


def scan(root: Path) -> dict[str, str]:
    """Hash every supported file under `root`. Symlinks are never followed and unreadable
    directories raise, so a permission problem cannot silently shrink the snapshot."""
    if not root.is_dir():
        raise SourceUnavailable(f"source directory not found: {root}")

    def fail(err: OSError) -> None:
        raise SourceUnavailable(f"cannot read directory {err.filename}: {err.strerror}")

    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=fail):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d))
        )
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name.startswith(".") or path.is_symlink():
                continue
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
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
