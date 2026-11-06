import asyncio
import hashlib
import os
import subprocess
from pathlib import Path

from app.rag.core.errors import SourceUnavailable
from app.rag.core.types import Snapshot
from app.rag.ingest.sources.dir import resolve_subdir, scan


# `ext::` and other helper transports run arbitrary commands; only the transports a document repository
# can legitimately use are allowed. `file` stays because local repositories are an operator feature
# (the HTTP API refuses local paths on its own, see app.rag.interfaces.validation).
_ALLOWED_PROTOCOLS = "https:ssh:git:file"


def _git(cwd: Path | None, *args: str) -> str:
    env = {**os.environ, "GIT_ALLOW_PROTOCOL": _ALLOWED_PROTOCOLS, "GIT_TERMINAL_PROMPT": "0"}
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    if done.returncode != 0:
        # Keep git's own message: "exit status 128" alone tells an operator nothing.
        raise SourceUnavailable(f"git {args[0]} failed: {_last_line(done.stderr) or done.returncode}")
    return done.stdout.strip()


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:300] if lines else ""


class GitSource:
    def __init__(self, url: str, branch: str, subdir: str, cache_dir: Path):
        # A value starting with "-" would be parsed by git as an option (for example --upload-pack=CMD).
        for label, value in (("repo url", url), ("branch", branch)):
            if not value.strip() or value.strip().startswith("-"):
                raise ValueError(f"invalid {label}: {value!r}")
        self.url, self.branch, self.subdir = url, branch, subdir
        key = hashlib.sha256(f"{url}@{branch}".encode()).hexdigest()[:16]
        self.workdir = Path(cache_dir) / key
        resolve_subdir(self.workdir, subdir)  # validate early: an unsafe subdir fails at construction

    def _sync(self) -> Snapshot:
        if not (self.workdir / ".git").exists():
            self.workdir.parent.mkdir(parents=True, exist_ok=True)
            _git(None, "clone", "--quiet", "--branch", self.branch, "--", self.url, str(self.workdir))
        else:
            _git(self.workdir, "fetch", "--quiet", "origin", self.branch)
            _git(self.workdir, "reset", "--quiet", "--hard", f"origin/{self.branch}")
        revision = _git(self.workdir, "rev-parse", "HEAD")
        root = resolve_subdir(self.workdir, self.subdir)
        files = scan(root)
        return Snapshot(revision, files, lambda rel: (root / rel).read_bytes())

    async def snapshot(self) -> Snapshot:
        return await asyncio.to_thread(self._sync)
