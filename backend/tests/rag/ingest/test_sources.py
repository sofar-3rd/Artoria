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
        "print(sorted(scan(Path(sys.argv[1]))[0]))"
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


@pytest.mark.parametrize("url", ["--upload-pack=touch /tmp/pwned", "-u x", "", "   ", " --upload-pack=x", "\t-u"])
def test_git_source_refuses_option_like_or_empty_urls(url, tmp_path):
    with pytest.raises(ValueError, match="invalid repo url"):
        GitSource(url, "main", "", tmp_path / "c")


@pytest.mark.parametrize("branch", ["--config=core.sshCommand=touch /tmp/pwned", "-b", "", " --x"])
def test_git_source_refuses_option_like_branches(branch, tmp_path):
    with pytest.raises(ValueError, match="invalid branch"):
        GitSource("https://example.com/r.git", branch, "", tmp_path / "c")


async def test_git_helper_transports_are_blocked(tmp_path):
    marker = tmp_path / "pwned"
    src = GitSource(f"ext::sh -c touch% {marker}", "main", "", tmp_path / "cache")
    with pytest.raises(SourceUnavailable, match="not allowed"):
        await src.snapshot()
    assert not marker.exists()


async def test_git_failure_carries_gits_own_message(tmp_path):
    with pytest.raises(SourceUnavailable) as exc:
        await GitSource(str(tmp_path / "no-such-repo"), "main", "", tmp_path / "cache").snapshot()
    assert "git clone failed" in str(exc.value) and "does not exist" in str(exc.value)


async def test_the_url_is_passed_to_git_after_a_double_dash(tmp_path, monkeypatch):
    """Defence in depth: even a value that looked harmless must reach git as an operand, never an option."""
    from app.rag.ingest.sources import git as git_module

    seen = []

    def fake_git(cwd, *args):
        seen.append(args)
        raise SourceUnavailable("stop here")

    monkeypatch.setattr(git_module, "_git", fake_git)
    with pytest.raises(SourceUnavailable):
        await GitSource("https://example.com/r.git", "main", "", tmp_path / "c").snapshot()
    clone = seen[0]
    assert clone[0] == "clone" and clone[clone.index("--") + 1] == "https://example.com/r.git"


async def test_git_runs_with_a_protocol_allow_list_and_no_prompts(tmp_path, monkeypatch):
    from app.rag.ingest.sources import git as git_module

    captured = {}

    def fake_run(cmd, **kw):
        captured["env"] = kw["env"]
        raise SourceUnavailable("stop here")

    monkeypatch.setattr(git_module.subprocess, "run", fake_run)
    with pytest.raises(SourceUnavailable):
        git_module._git(None, "ls-remote", "--", "https://example.com/r.git")
    assert captured["env"]["GIT_ALLOW_PROTOCOL"] == "https:ssh:git:file"
    assert "ext" not in captured["env"]["GIT_ALLOW_PROTOCOL"].split(":")
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_two_owners_of_the_same_repository_get_separate_checkouts(tmp_path):
    a = GitSource("https://example.com/r.git", "main", "a", tmp_path, owner="kb-1")
    b = GitSource("https://example.com/r.git", "main", "b", tmp_path, owner="kb-2")
    again = GitSource("https://example.com/r.git", "main", "a", tmp_path, owner="kb-1")
    assert a.workdir != b.workdir and a.workdir == again.workdir


async def test_a_second_owner_does_not_move_the_first_owners_checkout(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    write(origin, "a/x.md", b"# A v1"); write(origin, "b/y.md", b"# B v1")
    git(origin, "add", "."); git(origin, "commit", "-q", "-m", "c1")
    a = GitSource(str(origin), "main", "a", tmp_path / "cache", owner="kb-1")
    b = GitSource(str(origin), "main", "b", tmp_path / "cache", owner="kb-2")
    snap_a = await a.snapshot()
    write(origin, "a/x.md", b"# A v2 newer"); git(origin, "commit", "-qam", "c2")
    await b.snapshot()  # another knowledge base syncs the same repository at the newer commit
    assert snap_a.read("x.md") == b"# A v1"  # the first one still reads the commit it listed


async def test_a_half_written_checkout_directory_is_replaced_not_fatal(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    write(origin, "a.md", b"# A")
    git(origin, "add", "."); git(origin, "commit", "-q", "-m", "c1")
    src = GitSource(str(origin), "main", "", tmp_path / "cache", owner="kb-1")
    src.workdir.mkdir(parents=True)
    (src.workdir / "leftover.txt").write_text("interrupted clone")  # a directory without .git
    assert list((await src.snapshot()).files) == ["a.md"]
    assert not list(src.workdir.parent.glob("*.tmp-*"))  # no temporary clone left behind


async def test_a_file_over_the_size_limit_is_skipped_with_a_reason_not_listed(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rag_max_document_bytes", 1024 * 1024)
    (tmp_path / "small.md").write_bytes(b"# small")
    with open(tmp_path / "huge.pdf", "wb") as f:
        f.truncate(3 * 1024 * 1024)  # sparse: cheap to create, over the 1 MB limit
    snap = await DirSource(tmp_path).snapshot()
    assert list(snap.files) == ["small.md"]
    assert list(snap.skipped) == ["huge.pdf"] and "3 MB" in snap.skipped["huge.pdf"] and "limit is 1 MB" in snap.skipped["huge.pdf"]


@pytest.mark.parametrize("size,text", [(0, "0 bytes"), (999, "999 bytes"), (2048, "2 KB"), (2560, "2.5 KB"), (1 << 20, "1 MB"), (3 * (1 << 20), "3 MB"), (1536 * 1024, "1.5 MB"), (5 * (1 << 30), "5 GB")])
def test_sizes_are_shown_in_a_unit_that_means_something(size, text):
    from app.rag.ingest.sources.dir import _human

    assert _human(size) == text


async def test_the_revision_changes_when_a_file_crosses_the_size_limit(tmp_path, monkeypatch):
    """Otherwise a sync would return early on 'same revision' and never notice the file became skippable (or fine)."""
    from app.config import settings

    monkeypatch.setattr(settings, "rag_max_document_bytes", 1000)
    (tmp_path / "ok.md").write_bytes(b"# ok")
    (tmp_path / "grow.md").write_bytes(b"x" * 500)
    before = (await DirSource(tmp_path).snapshot()).revision
    (tmp_path / "grow.md").write_bytes(b"x" * 1500)  # now over the limit: leaves `files`, enters `skipped`
    over = (await DirSource(tmp_path).snapshot()).revision
    (tmp_path / "grow.md").unlink()
    gone = (await DirSource(tmp_path).snapshot()).revision
    assert len({before, over, gone}) == 3


async def test_a_file_exactly_at_the_limit_is_still_indexed(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rag_max_document_bytes", 100)
    (tmp_path / "edge.md").write_bytes(b"x" * 100)
    (tmp_path / "over.md").write_bytes(b"x" * 101)
    snap = await DirSource(tmp_path).snapshot()
    assert list(snap.files) == ["edge.md"] and list(snap.skipped) == ["over.md"]


def test_hashing_a_large_file_does_not_load_it_into_memory(tmp_path, monkeypatch):
    """Block hashing keeps memory constant: read_bytes() of a 200 MB file grew the process by 200 MB."""
    import hashlib
    import tracemalloc

    from app.rag.ingest.sources.dir import _sha256_file

    big = tmp_path / "big.md"
    with open(big, "wb") as f:
        for _ in range(64):
            f.write(b"a" * (1024 * 1024))  # 64 MB of real bytes
    tracemalloc.start()
    digest = _sha256_file(big)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 8 * 1024 * 1024, f"peak {peak / 1e6:.0f} MB while hashing a 64 MB file"
    assert digest == hashlib.sha256(big.read_bytes()).hexdigest()  # same result as the one-shot hash


async def test_the_default_limit_is_20_mb():
    from app.config import settings

    assert settings.rag_max_document_bytes == 20 * 1024 * 1024


async def test_a_failure_moving_the_clone_into_place_is_a_source_problem(tmp_path, monkeypatch):
    from app.rag.ingest.sources import git as git_module

    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    write(origin, "a.md", b"# A")
    git(origin, "add", "."); git(origin, "commit", "-q", "-m", "c1")

    def refuse(src, dst):
        raise OSError(66, "Directory not empty")

    monkeypatch.setattr(git_module.os, "replace", refuse)
    src = GitSource(str(origin), "main", "", tmp_path / "cache", owner="kb-1")
    with pytest.raises(SourceUnavailable, match="could not move the fresh clone into place"):
        await src.snapshot()
    assert not list(src.workdir.parent.glob("*.tmp-*"))  # the temporary clone was cleaned up


async def test_a_file_that_grows_after_listing_is_not_read_in_full(tmp_path, monkeypatch):
    """The limit is enforced when READING too: listing says 8 bytes, the file is then replaced by a huge one."""
    import resource

    from app.config import settings

    monkeypatch.setattr(settings, "rag_max_document_bytes", 2000)
    (tmp_path / "grow.md").write_bytes(b"# small\n")
    snap = await DirSource(tmp_path).snapshot()
    assert list(snap.files) == ["grow.md"]
    with open(tmp_path / "grow.md", "wb") as f:
        f.truncate(400 * 1024 * 1024)  # sparse: free to create, 400 MB if read_bytes() were used
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    with pytest.raises(SourceUnavailable, match="larger than the 2 KB limit now"):
        snap.read("grow.md")
    grown_mb = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) / (1024 * 1024)  # bytes on macOS
    assert grown_mb < 50, f"the process grew by {grown_mb:.0f} MB while refusing the file"


def test_read_limited_reads_a_file_exactly_at_the_limit(tmp_path):
    from app.rag.ingest.sources.dir import read_limited

    (tmp_path / "edge.md").write_bytes(b"x" * 100)
    assert read_limited(tmp_path / "edge.md", 100) == b"x" * 100
    (tmp_path / "over.md").write_bytes(b"x" * 101)
    with pytest.raises(SourceUnavailable):
        read_limited(tmp_path / "over.md", 100)


async def test_the_git_reader_enforces_the_limit_too(tmp_path, monkeypatch):
    from app.config import settings

    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    write(origin, "a.md", b"# small")
    git(origin, "add", "."); git(origin, "commit", "-q", "-m", "c1")
    monkeypatch.setattr(settings, "rag_max_document_bytes", 2000)
    src = GitSource(str(origin), "main", "", tmp_path / "cache", owner="kb-1")
    snap = await src.snapshot()
    (src.workdir / "a.md").write_bytes(b"y" * 5000)  # the checkout changes after listing
    with pytest.raises(SourceUnavailable, match="larger than"):
        snap.read("a.md")


@pytest.mark.parametrize(
    "text,secret",
    [
        ("fatal: unable to access 'https://user:SECRET@host/r.git/': failed", "SECRET"),
        ("ssh://git:SECRET@host:22/o/r", "SECRET"),
        ("git://u:SECRET@h/r", "SECRET"),
        ("https://x-access-token:SECRET@host/o/r.git", "SECRET"),
        ("error cloning https://TOKENONLY@host/o/r.git", "TOKENONLY"),
    ],
)
def test_credentials_in_a_url_are_removed_from_any_message(text, secret):
    from app.rag.core.redact import redact_url

    out = redact_url(text)
    assert secret not in out
    assert "://" in out  # still useful: the host is there


def test_redaction_leaves_urls_without_credentials_and_paths_with_at_signs_alone():
    from app.rag.core.redact import redact_url

    for text in ("https://host/o/r.git", "https://host/a@b/r.git", "no url here", "path/to/file@1.md"):
        assert redact_url(text) == text


def test_source_errors_are_redacted_wherever_they_are_constructed():
    """The constructor redacts, so a new raise site cannot leak a credential by forgetting to."""
    with pytest.raises(SourceUnavailable) as exc:
        setattr(SourceUnavailable, "_probe", None) or (_ for _ in ()).throw(
            SourceUnavailable("cannot read 'https://u:TOPSECRET@host/r.git'")
        )
    assert "TOPSECRET" not in str(exc.value) and "host/r.git" in str(exc.value)
