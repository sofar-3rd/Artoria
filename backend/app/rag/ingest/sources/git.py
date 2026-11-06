import asyncio
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from app.rag.core.errors import SourceUnavailable
from app.rag.core.types import Snapshot
from app.rag.ingest.sources.dir import read_limited, resolve_subdir, scan


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
    def __init__(self, url: str, branch: str, subdir: str, cache_dir: Path, owner: str = ""):
        # A value starting with "-" would be parsed by git as an option (for example --upload-pack=CMD).
        for label, value in (("repo url", url), ("branch", branch)):
            if not value.strip() or value.strip().startswith("-"):
                raise ValueError(f"invalid {label}: {value!r}")
        self.url, self.branch, self.subdir = url, branch, subdir
        # One checkout PER KNOWLEDGE BASE (`owner`), not per url@branch. Two knowledge bases on one repository
        # that shared a checkout could `reset --hard` it under each other while the first was still reading
        # the files of its snapshot (measured: text of a newer commit indexed under an older sha). Syncs of
        # ONE knowledge base are already serialised by the database lock, so a checkout has a single user.
        key = hashlib.sha256(f"{owner}|{url}@{branch}".encode()).hexdigest()[:16]
        self.workdir = Path(cache_dir) / key
        resolve_subdir(self.workdir, subdir)  # validate early: an unsafe subdir fails at construction

    def _sync(self) -> Snapshot:
        if not (self.workdir / ".git").exists():
            self._clone()
        else:
            _git(self.workdir, "fetch", "--quiet", "origin", self.branch)
            _git(self.workdir, "reset", "--quiet", "--hard", f"origin/{self.branch}")
        revision = _git(self.workdir, "rev-parse", "HEAD")
        root = resolve_subdir(self.workdir, self.subdir)
        files, skipped = scan(root)
        return Snapshot(revision, files, lambda rel: read_limited(root / rel), skipped)

    def _clone(self) -> None:
        """Clone into a temporary directory and move it into place, so a crash never leaves a half-written
        checkout that makes every later sync fail with "destination already exists"."""
        self.workdir.parent.mkdir(parents=True, exist_ok=True)
        if self.workdir.exists():  # leftover of an interrupted run: it has no .git, so it is not a checkout
            shutil.rmtree(self.workdir)
        tmp = self.workdir.with_name(f"{self.workdir.name}.tmp-{os.getpid()}")
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            _git(None, "clone", "--quiet", "--branch", self.branch, "--", self.url, str(tmp))
            try:
                os.replace(tmp, self.workdir)
            except OSError as exc:  # for example the directory appeared meanwhile: report it as a source problem
                raise SourceUnavailable(f"could not move the fresh clone into place: {exc.strerror}") from exc
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def snapshot(self) -> Snapshot:
        return await asyncio.to_thread(self._sync)
