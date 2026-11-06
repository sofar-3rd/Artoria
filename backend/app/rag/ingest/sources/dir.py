import asyncio
import hashlib
import os
from pathlib import Path

from app.config import settings
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


def _human(n: int) -> str:
    for unit, size in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= size:
            return f"{n / size:.1f} {unit}".replace(".0 ", " ")
    return f"{n} bytes"


def _sha256_file(path: Path) -> str:
    """Hash in blocks: memory stays constant however large the file is."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan(root: Path, max_bytes: int | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """Hash every supported file under `root`; return `(files, skipped)`.

    Symlinks are never followed and unreadable directories raise, so a permission problem cannot silently
    shrink the snapshot. A file larger than `max_bytes` is not listed as a document but reported in `skipped`
    with its reason, so the operator can see why it is missing.
    """
    limit = settings.rag_max_document_bytes if max_bytes is None else max_bytes
    if not root.is_dir():
        raise SourceUnavailable(f"source directory not found: {root}")

    def fail(err: OSError) -> None:
        raise SourceUnavailable(f"cannot read directory {err.filename}: {err.strerror}")

    files: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=fail):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d))
        )
        for name in sorted(filenames):
            path = Path(dirpath) / name
            # Only regular files: opening a FIFO or socket named *.md would block this thread forever.
            if name.startswith(".") or path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                rel = path.relative_to(root).as_posix()
                size = path.stat().st_size
                if size > limit:
                    skipped[rel] = f"file is {_human(size)}, the limit is {_human(limit)}"
                    continue
                files[rel] = _sha256_file(path)
    return files, skipped


class DirSource:
    def __init__(self, root: Path):
        self.root = Path(root)

    async def snapshot(self) -> Snapshot:
        files, skipped = await asyncio.to_thread(scan, self.root)
        # The revision must change whenever the OUTCOME of a sync could change: a file that crosses the size
        # limit (or comes back under it) alters `skipped` without altering `files`.
        digest = hashlib.sha256(repr((sorted(files.items()), sorted(skipped.items()))).encode()).hexdigest()
        return Snapshot(
            revision=f"dir:{digest[:16]}",
            files=files,
            reader=lambda rel: (self.root / rel).read_bytes(),
            skipped=skipped,
        )
