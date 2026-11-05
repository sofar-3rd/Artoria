import subprocess
from pathlib import Path

import pytest

from app.rag.ingest.sources import DirSource, GitSource, make_source


def write(root: Path, rel: str, content: bytes):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


async def test_dir_source_lists_supported_files_only(tmp_path):
    write(tmp_path, "a.md", b"# A")
    write(tmp_path, "sub/b.pdf", b"%PDF")
    write(tmp_path, "c.txt", b"nope")
    write(tmp_path, ".hidden/d.md", b"# D")
    snap = await DirSource(tmp_path).snapshot()
    assert sorted(snap.files) == ["a.md", "sub/b.pdf"]
    assert snap.read("a.md") == b"# A"


async def test_dir_source_revision_changes_with_content(tmp_path):
    write(tmp_path, "a.md", b"1")
    r1 = (await DirSource(tmp_path).snapshot()).revision
    write(tmp_path, "a.md", b"2")
    r2 = (await DirSource(tmp_path).snapshot()).revision
    assert r1 != r2


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


async def test_git_source_clones_and_follows_new_commits(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    write(origin, "docs/a.md", b"# A")
    write(origin, "other/x.md", b"# X")
    git(origin, "add", "."); git(origin, "commit", "-q", "-m", "c1")

    src = GitSource(str(origin), "main", "docs", tmp_path / "cache")
    s1 = await src.snapshot()
    assert list(s1.files) == ["a.md"] and s1.read("a.md") == b"# A"

    write(origin, "docs/a.md", b"# A2")
    git(origin, "add", "."); git(origin, "commit", "-q", "-m", "c2")
    s2 = await src.snapshot()
    assert s2.revision != s1.revision and s2.read("a.md") == b"# A2"


def test_make_source_picks_dir_for_local_directory(tmp_path):
    assert isinstance(make_source(str(tmp_path), "main", "", tmp_path / "c"), DirSource)
    assert isinstance(make_source("https://example.com/r.git", "main", "", tmp_path / "c"), GitSource)
