import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.rag.core.errors import SourceUnavailable
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


async def test_dir_source_missing_directory_raises(tmp_path):
    with pytest.raises(SourceUnavailable):
        await DirSource(tmp_path / "does-not-exist").snapshot()


async def test_dir_source_existing_empty_directory_is_a_valid_empty_snapshot(tmp_path):
    assert (await DirSource(tmp_path).snapshot()).files == {}


async def test_make_source_with_missing_subdir_raises(tmp_path):
    with pytest.raises(SourceUnavailable):
        await make_source(f"dir:{tmp_path}", "main", "nope", tmp_path / "c").snapshot()


@pytest.mark.parametrize("location", ["", "   ", "dir:", "dir:  "])
def test_make_source_rejects_empty_location(location, tmp_path):
    with pytest.raises(ValueError, match="repo_url must not be empty"):
        make_source(location, "main", "", tmp_path / "c")


@pytest.mark.parametrize("subdir", ["../outside", "a/../../outside", "..", "sub/../.."])
def test_subdir_with_dotdot_is_rejected(subdir, tmp_path):
    (tmp_path / "kb").mkdir()
    with pytest.raises(ValueError, match="subdir"):
        make_source(f"dir:{tmp_path / 'kb'}", "main", subdir, tmp_path / "c")
    with pytest.raises(ValueError, match="subdir"):
        GitSource("https://example.com/r.git", "main", subdir, tmp_path / "c")


async def test_absolute_subdir_is_relative_to_the_root_not_the_filesystem(tmp_path):
    kb, outside = tmp_path / "kb", tmp_path / "outside"
    (kb / "docs").mkdir(parents=True); outside.mkdir()
    (kb / "docs/a.md").write_bytes(b"# A"); (outside / "secret.md").write_bytes(b"# S")
    # "/docs" means <root>/docs
    snap = await make_source(f"dir:{kb}", "main", "/docs", tmp_path / "c").snapshot()
    assert list(snap.files) == ["a.md"]
    # an absolute path to somewhere else resolves under the root and therefore does not exist
    with pytest.raises(SourceUnavailable):
        await make_source(f"dir:{kb}", "main", str(outside), tmp_path / "c").snapshot()


async def test_symlinks_are_not_followed(tmp_path):
    kb, outside = tmp_path / "kb", tmp_path / "outside"
    kb.mkdir(); outside.mkdir()
    (kb / "a.md").write_bytes(b"# A"); (outside / "leak.md").write_bytes(b"# leak")
    (kb / "file-link.md").symlink_to(outside / "leak.md")
    (kb / "dir-link").symlink_to(outside, target_is_directory=True)
    snap = await DirSource(kb).snapshot()
    assert list(snap.files) == ["a.md"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX FIFOs")
def test_fifo_named_like_a_document_is_skipped_not_opened(tmp_path):
    # open() on a FIFO blocks forever and cannot be interrupted inside a worker thread, so run the scan
    # in a child process with a hard timeout instead of risking a hung test run.
    (tmp_path / "a.md").write_bytes(b"# A")
    os.mkfifo(tmp_path / "pipe.md")
    code = (
        "import sys; from pathlib import Path; from app.rag.ingest.sources.dir import scan; "
        "print(sorted(scan(Path(sys.argv[1]))))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, timeout=20,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['a.md']"


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read everything")
async def test_unreadable_subdirectory_fails_loudly(tmp_path):
    (tmp_path / "a.md").write_bytes(b"# A")
    locked = tmp_path / "locked"; locked.mkdir(); (locked / "b.md").write_bytes(b"# B")
    locked.chmod(0o000)
    try:
        with pytest.raises(SourceUnavailable):
            await DirSource(tmp_path).snapshot()
    finally:
        locked.chmod(0o755)


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


async def test_git_source_missing_subdir_raises(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    write(origin, "docs/a.md", b"# A")
    git(origin, "add", "."); git(origin, "commit", "-q", "-m", "c1")
    with pytest.raises(SourceUnavailable):
        await GitSource(str(origin), "main", "dcos", tmp_path / "cache").snapshot()


def test_make_source_picks_dir_for_local_directory(tmp_path):
    assert isinstance(make_source(str(tmp_path), "main", "", tmp_path / "c"), DirSource)
    assert isinstance(make_source("https://example.com/r.git", "main", "", tmp_path / "c"), GitSource)
