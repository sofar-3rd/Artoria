import pytest

from app.db import SessionLocal, engine
from app.rag.bootstrap import build_rag
from app.rag.ingest.sources import DirSource
from app.rag.interfaces import cli
from tests.rag.fakes import HashEmbedder


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


@pytest.fixture
def source_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli, "build_rag",
        lambda: build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len,
                          source_factory=lambda kb: DirSource(tmp_path)),
    )
    return tmp_path


def run(argv):
    # cli.main uses asyncio.run, which cannot be nested in the test's own loop: run it in a thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(cli.main, argv).result()


def test_create_list_and_sync(source_dir, capsys):
    (source_dir / "a.md").write_text("# A\n\nalpha body text is here\n", encoding="utf-8")
    (source_dir / "b.md").write_text("# B\n\nbeta body text is here\n", encoding="utf-8")
    assert run(["create", "cli-kb", "--repo", f"dir:{source_dir}", "--description", "cli docs"]) == 0
    assert "created knowledge base 'cli-kb'" in capsys.readouterr().out
    assert run(["sync", "cli-kb"]) == 0
    assert "added=2 changed=0 removed=0 unchanged=0 failed=0" in capsys.readouterr().out
    assert run(["list"]) == 0
    out = capsys.readouterr().out
    assert "cli-kb: cli docs (2 documents" in out
    assert run(["sync", "cli-kb"]) == 0
    assert "added=0 changed=0 removed=0 unchanged=2 failed=0" in capsys.readouterr().out


def test_sync_exits_1_when_a_file_fails(source_dir, capsys):
    (source_dir / "good.md").write_text("# G\n\ngood body text is here\n", encoding="utf-8")
    (source_dir / "empty.md").write_text("   \n", encoding="utf-8")
    assert run(["create", "cli-bad", "--repo", f"dir:{source_dir}"]) == 0
    capsys.readouterr()
    assert run(["sync", "cli-bad"]) == 1
    captured = capsys.readouterr()
    assert "failed=1" in captured.out and "empty.md" in captured.err


def test_unknown_kb_exits_2_with_a_message(source_dir, capsys):
    assert run(["sync", "no-such-kb"]) == 2
    assert "unknown knowledge base" in capsys.readouterr().err


def test_a_bad_name_exits_2_and_creates_nothing(source_dir, capsys):
    assert run(["create", "bad name", "--repo", f"dir:{source_dir}"]) == 2
    assert "name must be" in capsys.readouterr().err
    assert run(["list"]) == 0
    assert "bad name" not in capsys.readouterr().out


@pytest.mark.parametrize("repo", ["-u", "--upload-pack=touch /tmp/x"])
def test_an_option_like_repo_is_refused(source_dir, capsys, repo):
    # `--repo=VALUE` is the only way to hand argparse a value that starts with "-".
    assert run(["create", "opt-kb", f"--repo={repo}"]) == 2
    assert "must be a git url or a directory" in capsys.readouterr().err


def test_a_blank_repo_is_refused(source_dir, capsys):
    assert run(["create", "blank-kb", "--repo=   "]) == 2
    assert "must be a git url or a directory" in capsys.readouterr().err


def test_duplicate_name_is_a_clean_error(source_dir, capsys):
    assert run(["create", "dup-kb", "--repo", f"dir:{source_dir}"]) == 0
    capsys.readouterr()
    assert run(["create", "dup-kb", "--repo", f"dir:{source_dir}"]) == 2
    assert "already exists" in capsys.readouterr().err


def test_a_command_is_required(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_without_embedder_the_cli_explains_what_to_do(monkeypatch, capsys):
    monkeypatch.undo()  # use the real build_rag, which has no embedder yet
    assert cli.main(["list"]) == 2
    assert "RAG_ENABLED" in capsys.readouterr().err
