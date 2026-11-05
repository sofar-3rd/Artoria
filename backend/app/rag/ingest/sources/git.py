import asyncio
import hashlib
import subprocess
from pathlib import Path

from app.rag.core.types import Snapshot
from app.rag.ingest.sources.dir import scan


def _git(cwd: Path | None, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class GitSource:
    def __init__(self, url: str, branch: str, subdir: str, cache_dir: Path):
        self.url, self.branch, self.subdir = url, branch, subdir.strip("/")
        key = hashlib.sha256(f"{url}@{branch}".encode()).hexdigest()[:16]
        self.workdir = Path(cache_dir) / key

    def _sync(self) -> Snapshot:
        if not (self.workdir / ".git").exists():
            self.workdir.parent.mkdir(parents=True, exist_ok=True)
            _git(None, "clone", "--quiet", "--branch", self.branch, self.url, str(self.workdir))
        else:
            _git(self.workdir, "fetch", "--quiet", "origin", self.branch)
            _git(self.workdir, "reset", "--quiet", "--hard", f"origin/{self.branch}")
        revision = _git(self.workdir, "rev-parse", "HEAD")
        root = self.workdir / self.subdir if self.subdir else self.workdir
        files = scan(root)
        return Snapshot(revision, files, lambda rel: (root / rel).read_bytes())

    async def snapshot(self) -> Snapshot:
        return await asyncio.to_thread(self._sync)
