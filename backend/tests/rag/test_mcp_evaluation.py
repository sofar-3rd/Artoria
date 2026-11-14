import importlib.util
import json
import math
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, update

from app.db import SessionLocal, engine
from app.rag.bootstrap import build_rag
from app.rag.core.types import Hit
from app.rag.persistence.models import ChunkRow, Document, KnowledgeBase
from tests.rag.fakes import HashEmbedder

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("ragas") is None,
    reason="Optional evaluation dependencies missing; use uv run --group eval pytest",
)


def tool():
    from scripts.mcp_eval.data import Tool

    return Tool("private-server/fetch", "fetch", "local", "读取远程文件内容。", "查看文件而不下载到本地时。")


def hit(path, score=0.1):
    return Hit("tools", "doc", path, "", "", 0, 4, 4, "body", score)


def test_only_name_capability_and_usage_enter_search_text():
    text = tool().text
    assert text == "工具名称: fetch\n功能描述: 读取远程文件内容。\n使用时机: 查看文件而不下载到本地时。"
    assert "private-server" not in text


@pytest.mark.parametrize("tokens", [255, 256])
def test_tool_token_budget_accepts_complete_chunk_at_boundary(tokens):
    from scripts.mcp_eval.budget import validate_tool_token_budget

    item = replace(tool(), function="")
    item = replace(item, function="x" * (tokens - len(item.text)))

    class Tokenizer:
        def encode(self, text, *, add_special_tokens):
            assert text == item.text and add_special_tokens is False
            return list(range(len(text)))

    assert validate_tool_token_budget([item], Tokenizer()) == [tokens]


def test_tool_token_budget_rejects_257_without_truncating():
    from scripts.mcp_eval.budget import validate_tool_token_budget

    item = replace(tool(), function="")
    item = replace(item, function="x" * (257 - len(item.text)))

    class Tokenizer:
        def encode(self, text, *, add_special_tokens):
            assert text == item.text and add_special_tokens is False
            return list(range(len(text)))

    with pytest.raises(ValueError, match=r"private-server/fetch.*257.*256"):
        validate_tool_token_budget([item], Tokenizer())
    assert len(item.text) == 257


async def test_cli_rejects_over_budget_before_database_or_output_write(tmp_path, monkeypatch):
    from scripts import eval_mcp_tools
    from transformers import AutoTokenizer

    tools = [replace(tool(), tool_id=f"s/tool-{i}", origin="local" if i < 100 else "public") for i in range(200)]
    questions = [dict(id=f"q-{i}", query="read", relevant_tool_ids=[t.tool_id],
                      split="dev" if i < 100 else "test") for i, t in enumerate(tools)]
    monkeypatch.setattr(eval_mcp_tools, "load_dataset", lambda directory: (tools, questions))

    class Tokenizer:
        def encode(self, text, *, add_special_tokens):
            assert text == tools[0].text and add_special_tokens is False
            return list(range(257))

    def tokenizer(*args, **kwargs):
        assert kwargs.get("local_files_only") is True
        return Tokenizer()

    monkeypatch.setattr(AutoTokenizer, "from_pretrained", tokenizer)

    async def forbidden(*args):
        raise AssertionError("over-budget corpus must not open a database")

    monkeypatch.setattr(eval_mcp_tools, "open_database", forbidden)
    output = tmp_path / "output"
    args = SimpleNamespace(command="import", dataset=tmp_path, output=output,
                           database_url="postgresql://localhost/sagent_rag_eval")
    with pytest.raises(ValueError, match=r"s/tool-0.*257.*256"):
        await eval_mcp_tools.execute(args)
    assert not output.exists()


@pytest.mark.parametrize("url", [
    "postgresql://localhost/sagent", "postgresql://localhost/sagent_rag_test",
    "postgresql://localhost/sagent_rag_eval_backup", "sqlite:///sagent_rag_eval",
])
def test_refuses_non_evaluation_databases(url):
    from scripts.mcp_eval.data import evaluation_url

    with pytest.raises(ValueError):
        evaluation_url(url)


def test_accepts_only_exact_evaluation_database():
    from scripts.mcp_eval.data import evaluation_url

    assert evaluation_url("postgresql://localhost/sagent_rag_eval").database == "sagent_rag_eval"


async def test_ragas_metrics_match_hand_calculation_and_empty_retrieval():
    from scripts.mcp_eval.metrics import score_ranking

    row = await score_ranking(["wrong", "a", "b"], ["a", "b", "c"], 3)
    assert row["precision"] == pytest.approx(2 / 3)
    assert row["recall"] == pytest.approx(2 / 3)
    assert row["hit"] == 1
    assert row["mrr"] == 0.5
    empty = await score_ranking([], ["a"], 5)
    assert math.isnan(empty["ragas_precision"])
    assert empty["precision"] == empty["recall"] == empty["hit"] == empty["mrr"] == 0
    assert empty["returned"] == 0


async def test_precision_uses_actual_return_count_and_top_k():
    from scripts.mcp_eval.metrics import score_ranking

    assert (await score_ranking(["a"], ["a"], 10))["precision"] == 1
    assert (await score_ranking(["wrong", "a"], ["a"], 1))["recall"] == 0


def test_dataset_rejects_invalid_labels_and_group_leakage(tmp_path):
    from scripts.mcp_eval.data import load_dataset

    tools = [vars(tool())]
    questions = [dict(id="q1", intent_id="i1", query="查看远程文件", relevant_tool_ids=[tool().tool_id], split="dev", category="direct")]
    (tmp_path / "tools.jsonl").write_text("\n".join(json.dumps(x) for x in tools))
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps(questions[0]))
    assert len(load_dataset(tmp_path)[1]) == 1
    path.write_text(json.dumps({**questions[0], "relevant_tool_ids": ["missing"]}))
    with pytest.raises(ValueError, match="unknown"):
        load_dataset(tmp_path)
    path.write_text("\n".join(json.dumps(q) for q in [questions[0], {**questions[0], "id": "q2", "split": "test"}]))
    with pytest.raises(ValueError, match="intent"):
        load_dataset(tmp_path)


@pytest.fixture
async def disposed_engine():
    yield
    await engine.dispose()


async def test_import_is_one_chunk_per_tool_and_idempotent(disposed_engine):
    from scripts.mcp_eval.data import import_tools

    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, sessionmaker=SessionLocal)
    await import_tools(rag, [tool()])
    await import_tools(rag, [tool()])
    async with SessionLocal() as session:
        assert (await session.scalar(select(func.count()).select_from(Document))) == 1
        assert (await session.scalar(select(func.count()).select_from(ChunkRow))) == 1
        chunk = (await session.scalars(select(ChunkRow))).one()
        assert chunk.content == tool().text
        assert "private-server" not in chunk.search_text
    rows = await rag.store.bm25_candidates([(await rag.store.get_kb("mcp-tools")).id], "远程文件", 10)
    assert [r.path for r in rows] == [tool().tool_id]


async def test_bm25_branch_does_not_embed_or_rerank():
    from scripts.mcp_eval.experiment import retrieve

    class Store:
        async def bm25_candidates(self, ids, query, recall):
            assert ids == ["kb"] and query == "read" and recall == 40
            return [hit("a"), hit("b")]

    class Forbidden:
        async def embed_query(self, query):
            raise AssertionError("BM25 must not embed")

        async def rerank(self, query, docs):
            raise AssertionError("BM25 must not rerank")

    rag = SimpleNamespace(store=Store(), embedder=Forbidden(), searcher=SimpleNamespace(_reranker=Forbidden()))
    rows = await retrieve(rag, "kb", "read", 40, 1, "bm25")
    assert rows["candidate_ids"] == ["a", "b"]
    assert rows["ranked_ids"] == ["a"]


async def test_hybrid_pool_and_reranking_use_exact_chunk_text():
    from scripts.mcp_eval.experiment import retrieve

    class Store:
        async def hybrid_candidates(self, ids, query, vector, recall, limit, rrf_k):
            assert (recall, limit, rrf_k) == (20, 40, 60)
            return [replace(hit("a"), content="first"), replace(hit("b"), content="second"), hit("c")]

    class Embedder:
        async def embed_query(self, query):
            return [1.0]

    class Reranker:
        async def rerank(self, query, docs):
            assert docs == ["first", "second"]
            return [0.1, 0.9]

    rag = SimpleNamespace(store=Store(), embedder=Embedder(), searcher=SimpleNamespace(_reranker=Reranker()))
    rows = await retrieve(rag, "kb", "read", 20, 2, "rerank")
    assert rows["candidate_ids"] == ["a", "b", "c"]
    assert rows["pool_ids"] == ["a", "b"]
    assert rows["ranked_ids"] == ["b", "a"]
    assert rows["reranked"] is True and rows["error"] is None


async def test_failed_reranker_records_fallback():
    from scripts.mcp_eval.experiment import retrieve

    class Store:
        async def hybrid_candidates(self, *args):
            return [hit("a"), hit("b")]

    class Embedder:
        async def embed_query(self, query):
            return [1.0]

    class Reranker:
        async def rerank(self, query, docs):
            return [float("nan"), 0.9]

    rag = SimpleNamespace(store=Store(), embedder=Embedder(), searcher=SimpleNamespace(_reranker=Reranker()))
    rows = await retrieve(rag, "kb", "read", 20, 2, "rerank")
    assert rows["ranked_ids"] == ["a", "b"]
    assert rows["reranked"] is False and rows["error"]


def test_selection_excludes_test_set_and_breaks_ties_on_candidate_count():
    from scripts.mcp_eval.experiment import select_configuration

    rows = [
        dict(split="dev", origin="all", method="rerank", recall=20, pool=20, k=5, recall_at_k=0.8, mrr=0.6),
        dict(split="dev", origin="all", method="rerank", recall=40, pool=20, k=5, recall_at_k=0.8, mrr=0.6),
        dict(split="test", origin="all", method="rerank", recall=80, pool=20, k=5, recall_at_k=1.0, mrr=1.0),
    ]
    assert select_configuration(rows)["recall"] == 20


async def test_three_phases_holdout_and_resume_produce_identical_scores(tmp_path):
    from scripts.mcp_eval.data import Tool, read_jsonl
    from scripts.mcp_eval.experiment import run_experiment, summarize

    class Store:
        async def get_kb(self, name):
            return SimpleNamespace(id="kb")

        async def bm25_candidates(self, ids, query, limit):
            return [hit("s/a"), hit("s/b")]

        async def hybrid_candidates(self, ids, query, vector, recall, limit, rrf_k):
            return [replace(hit("s/a"), content="a"), replace(hit("s/b"), content="b")]

    class Embedder:
        async def embed_query(self, query):
            return [1.0]

    class Reranker:
        async def rerank(self, query, docs):
            return [1.0 if doc == "b" else 0.0 for doc in docs]

    def rag():
        return SimpleNamespace(store=Store(), embedder=Embedder(), searcher=SimpleNamespace(_reranker=Reranker()))

    tools = [Tool("s/a", "a", "local", "a", "a"), Tool("s/b", "b", "public", "b", "b")]
    questions = [dict(id="dev", query="dev", split="dev", relevant_tool_ids=["s/b"]),
                 dict(id="test", query="test", split="test", relevant_tool_ids=["s/a"])]
    selection = await run_experiment(rag(), questions, tools, tmp_path)
    assert (selection["recall"], selection["pool"]) == (20, 10)
    records = read_jsonl(tmp_path / "rankings.jsonl")
    assert {r["phase"] for r in records} == {"baseline", "recall_sweep", "pool_sweep", "selected"}
    assert not any(r["split"] == "test" and r["phase"] in {"recall_sweep", "pool_sweep"} for r in records)
    summary = await summarize(records)
    assert any(r["split"] == "test" and r["method"] == "rerank" and r["k"] == 1
               and r["recall_at_k"] == 0 for r in summary)
    assert await run_experiment(rag(), questions, tools, tmp_path) == selection
    assert read_jsonl(tmp_path / "rankings.jsonl") == records


async def test_import_refuses_changed_embedding_fingerprint(disposed_engine):
    from scripts.mcp_eval.data import import_tools

    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, sessionmaker=SessionLocal)
    await import_tools(rag, [tool()], fingerprint={"weights": "first", "tokenizer": "one"})
    before = (await rag.store.get_kb("mcp-tools")).last_commit
    with pytest.raises(ValueError, match="fingerprint"):
        await import_tools(rag, [tool()], fingerprint={"weights": "second", "tokenizer": "one"})
    with pytest.raises(ValueError, match="fingerprint"):
        await import_tools(rag, [tool()], fingerprint={"weights": "first", "tokenizer": "two"})
    assert (await rag.store.get_kb("mcp-tools")).last_commit == before


async def test_import_refuses_nonempty_legacy_state(disposed_engine):
    from scripts.mcp_eval.data import import_tools

    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, sessionmaker=SessionLocal)
    await import_tools(rag, [tool()])
    async with SessionLocal() as session:
        await session.execute(update(KnowledgeBase).values(last_commit=None))
        await session.commit()
    with pytest.raises(ValueError, match="fingerprint"):
        await import_tools(rag, [tool()])


async def test_import_refuses_changed_tokenization_adapter(disposed_engine, monkeypatch):
    from scripts.mcp_eval import data

    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, sessionmaker=SessionLocal)
    await data.import_tools(rag, [tool()])
    monkeypatch.setattr(data, "import_behavior_fingerprint", lambda: {"fts": "changed"})
    with pytest.raises(ValueError, match="fingerprint"):
        await data.import_tools(rag, [tool()])


@pytest.mark.parametrize("corruption", ["foreign_kb", "chunk_content", "search_text", "foreign_chunk"])
async def test_import_rejects_foreign_or_modified_data(disposed_engine, corruption):
    from scripts.mcp_eval.data import import_tools

    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, sessionmaker=SessionLocal)
    await import_tools(rag, [tool()])
    async with SessionLocal() as session:
        if corruption == "foreign_kb":
            session.add(KnowledgeBase(name="foreign", description="", repo_url="", embed_model="fake", embed_dim=1024))
        elif corruption == "foreign_chunk":
            chunk = (await session.scalars(select(ChunkRow))).one()
            session.add(ChunkRow(doc_id=chunk.doc_id, kb_id=chunk.kb_id, idx=1, heading_path="",
                                 start_char=0, end_char=1, content="foreign", search_text="foreign", embedding=[0.0] * 1024))
        else:
            await session.execute(update(ChunkRow).values(**{corruption if corruption == "search_text" else "content": "modified"}))
        await session.commit()
    with pytest.raises(ValueError, match="foreign|frozen|exactly one"):
        await import_tools(rag, [tool()])


def test_model_fingerprint_hashes_large_weights_and_nested_tokenizer(tmp_path):
    from scripts.eval_mcp_tools import model_fingerprint

    for model in ("bge-m3", "bge-reranker-v2-m3"):
        (tmp_path / model / "nested").mkdir(parents=True)
        (tmp_path / model / "nested/tokenizer.json").write_text("first")
        (tmp_path / model / "weights.bin").write_bytes(b"a" * 25_000_001)
    first = model_fingerprint(str(tmp_path))
    weights = tmp_path / "bge-m3/weights.bin"
    stat = weights.stat()
    with weights.open("r+b") as handle:
        handle.write(b"b")
    import os
    os.utime(weights, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    second = model_fingerprint(str(tmp_path))
    assert first != second
    (tmp_path / "bge-m3/nested/tokenizer.json").write_text("second")
    assert second != model_fingerprint(str(tmp_path))


@pytest.mark.parametrize("filename", ["rankings.jsonl", "pair_scores.jsonl", "candidates.jsonl"])
def test_runtime_jsonl_recovers_only_incomplete_final_line(tmp_path, filename):
    from scripts.mcp_eval.data import read_runtime_jsonl

    path = tmp_path / filename
    valid = b'{"ok": 1}\n'
    path.write_bytes(valid + b'{"query": "\xe4\xb8')
    assert read_runtime_jsonl(path) == [{"ok": 1}]
    assert path.read_bytes() == valid
    for broken in (valid + b'{broken}\n', b'{broken}\n' + valid, b'{broken}\n{"partial":',
                   valid + b'{broken}', valid + b'{broken'):
        path.write_bytes(broken)
        with pytest.raises(ValueError):
            read_runtime_jsonl(path)
        assert path.read_bytes() == broken
    path.write_bytes(b'{"ok": 1}')
    assert read_runtime_jsonl(path) == [{"ok": 1}]
    assert path.read_bytes() == valid


def test_corpus_jsonl_never_recovers_partial_record(tmp_path):
    from scripts.mcp_eval.data import read_jsonl

    path = tmp_path / "tools.jsonl"
    broken = b'{"ok": 1}\n{"partial":'
    path.write_bytes(broken)
    with pytest.raises(ValueError):
        read_jsonl(path)
    assert path.read_bytes() == broken


def test_metadata_resume_preserves_file_and_rejects_changed_state(tmp_path):
    from scripts.eval_mcp_tools import ensure_metadata

    path = tmp_path / "metadata.json"
    metadata = {"database": {"version": "17", "endpoint_sha256": "first"}}
    ensure_metadata(tmp_path, metadata)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    ensure_metadata(tmp_path, metadata)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    with pytest.raises(ValueError):
        ensure_metadata(tmp_path, {"database": {"version": "18", "endpoint_sha256": "first"}})
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


async def test_metadata_reads_actual_database_and_scrubs_credentials(disposed_engine):
    from scripts.eval_mcp_tools import database_metadata, runtime_metadata

    db = await database_metadata(engine, "postgresql://user:secret@localhost:5433/sagent_rag_eval?password=hidden")
    assert db["postgres_version"]
    assert set(db["extensions"]) == {"vector", "pg_textsearch"}
    metadata = runtime_metadata("dataset", {}, db, 200, 400)
    assert {"fts", "store", "embedding", "rerank", "inference_text", "retrieval"} <= metadata["implementation_sha256"].keys()
    assert {"jieba", "torch", "transformers", "sentence-transformers", "psycopg", "sqlalchemy"} <= metadata["dependencies"].keys()
    assert metadata["rerank_timeout_s"] > 0
    encoded = json.dumps(metadata)
    assert all(secret not in encoded for secret in ("secret", "hidden", "user:", "password"))
    other = await database_metadata(engine, "postgresql://other:credential@localhost:5434/sagent_rag_eval")
    assert other["endpoint_sha256"] != db["endpoint_sha256"]


async def test_summary_uses_latest_unique_outcome():
    from scripts.mcp_eval.experiment import summarize

    failed = dict(phase="baseline", question_id="q", method="rerank", recall=40, pool=20,
                  split="dev", origin="local", references=["a"], candidate_ids=["a"], pool_ids=["a"],
                  ranked_ids=["wrong"], error="timeout")
    success = {**failed, "ranked_ids": ["a"], "error": None}
    rows = await summarize([failed, success, success])
    assert all(row["queries"] == 1 and row["recall_at_k"] == 1 and row["rerank_failures"] == 0 for row in rows)


def experiment_fixture():
    from scripts.mcp_eval.data import Tool

    class Store:
        def __init__(self):
            self.calls = []

        async def get_kb(self, name):
            return SimpleNamespace(id="kb")

        async def bm25_candidates(self, ids, query, recall):
            self.calls.append((query, recall, "bm25"))
            return [hit("s/a"), hit("s/b")]

        async def hybrid_candidates(self, ids, query, vector, recall, limit, rrf_k):
            self.calls.append((query, recall, "hybrid"))
            # An unstable store exposes separate retrievals for hybrid and rerank.
            rows = [replace(hit("s/a"), content="a"), replace(hit("s/b"), content="b")]
            return rows if len(self.calls) % 2 else rows[::-1]

    class Embedder:
        model, dim = "fake", 1

        async def embed_query(self, query):
            return [1.0]

    class Reranker:
        async def rerank(self, query, docs):
            return [1.0 if doc == "b" else 0.0 for doc in docs]

    rag = SimpleNamespace(store=Store(), embedder=Embedder(), searcher=SimpleNamespace(_reranker=Reranker()))
    tools = [Tool("s/a", "a", "local", "a", "a"), Tool("s/b", "b", "public", "b", "b")]
    questions = [dict(id="dev", query="dev", split="dev", relevant_tool_ids=["s/b"]),
                 dict(id="test", query="test", split="test", relevant_tool_ids=["s/a"])]
    return rag, tools, questions


async def test_experiment_shares_candidates_across_methods_pools_and_resume(tmp_path):
    from scripts.mcp_eval.data import read_jsonl
    from scripts.mcp_eval.experiment import run_experiment

    rag, tools, questions = experiment_fixture()
    await run_experiment(rag, questions, tools, tmp_path)
    assert len(rag.store.calls) == len(set(rag.store.calls))
    rows = read_jsonl(tmp_path / "rankings.jsonl")
    for row in rows:
        if row["method"] == "rerank":
            hybrid = next(r for r in rows if (r["phase"], r["question_id"], r["recall"], r["pool"], r["method"])
                          == (row["phase"], row["question_id"], row["recall"], row["pool"], "hybrid"))
            assert row["candidate_ids"] == hybrid["candidate_ids"]
            assert row["pool_ids"] == row["candidate_ids"][:row["pool"]]
    (tmp_path / "rankings.jsonl").write_text("")
    resumed, _, _ = experiment_fixture()
    await run_experiment(resumed, questions, tools, tmp_path)
    assert resumed.store.calls == []
    new_rows = read_jsonl(tmp_path / "rankings.jsonl")
    assert [r["candidate_ids"] for r in new_rows] == [r["candidate_ids"] for r in rows]


async def test_resume_retries_failed_records_and_preserves_provenance(tmp_path):
    from scripts.mcp_eval.data import read_jsonl
    from scripts.mcp_eval.experiment import run_experiment, summarize

    rag, tools, questions = experiment_fixture()
    await run_experiment(rag, questions, tools, tmp_path)
    path = tmp_path / "rankings.jsonl"
    rows = read_jsonl(path)
    failed = {**next(r for r in rows if r["method"] == "rerank"), "error": "TimeoutError: original", "reranked": False}
    with path.open("a") as handle:
        handle.write(json.dumps(failed) + "\n")
    prior = path.read_bytes()
    resumed, _, _ = experiment_fixture()
    await run_experiment(resumed, questions, tools, tmp_path)
    assert path.read_bytes().startswith(prior)
    outcomes = [r for r in read_jsonl(path) if (r["phase"], r["question_id"], r["method"], r["recall"], r["pool"])
                == (failed["phase"], failed["question_id"], failed["method"], failed["recall"], failed["pool"])]
    assert len(outcomes) == 3 and outcomes[-1]["error"] is None
    assert outcomes[-2]["error"] == "TimeoutError: original"
    assert all(r["rerank_failures"] == 0 for r in await summarize(read_jsonl(path)))


async def test_pair_cache_rejects_changed_checkpoint(tmp_path):
    from scripts.mcp_eval.experiment import CachedReranker

    class Reranker:
        async def rerank(self, query, docs):
            return [0.25] * len(docs)

    path = tmp_path / "pair_scores.jsonl"
    first = CachedReranker(Reranker(), path, fingerprint="first")
    assert await first.rerank("q", ["exact chunk"]) == [0.25]
    with pytest.raises(ValueError, match="fingerprint"):
        CachedReranker(Reranker(), path, fingerprint="second")


@pytest.mark.parametrize("kind", ["tool", "query"])
def test_dataset_rejects_adapter_truncation(tmp_path, kind):
    from app.rag.inference.text import MAX_DOCUMENT_CHARS, MAX_QUERY_CHARS
    from scripts.mcp_eval.data import load_dataset

    item = tool()
    question = dict(id="q", intent_id="i", query="read", split="dev", relevant_tool_ids=[item.tool_id])
    if kind == "tool":
        item = replace(item, function="x" * MAX_DOCUMENT_CHARS)
    else:
        question["query"] = "x" * (MAX_QUERY_CHARS + 1)
    (tmp_path / "tools.jsonl").write_text(json.dumps(vars(item)))
    (tmp_path / "questions.jsonl").write_text(json.dumps(question))
    with pytest.raises(ValueError, match="limit|length|truncat"):
        load_dataset(tmp_path)


def test_dataset_accepts_exact_adapter_length_limits(tmp_path):
    from app.rag.inference.text import MAX_DOCUMENT_CHARS, MAX_QUERY_CHARS
    from scripts.mcp_eval.data import load_dataset

    empty = replace(tool(), function="")
    item = replace(empty, function="x" * (MAX_DOCUMENT_CHARS - len(empty.text)))
    question = dict(id="q", intent_id="i", query="x" * MAX_QUERY_CHARS, split="dev", relevant_tool_ids=[item.tool_id])
    (tmp_path / "tools.jsonl").write_text(json.dumps(vars(item)))
    (tmp_path / "questions.jsonl").write_text(json.dumps(question))
    loaded, questions = load_dataset(tmp_path)
    assert len(loaded[0].text) == MAX_DOCUMENT_CHARS
    assert len(questions[0]["query"]) == MAX_QUERY_CHARS


async def test_interrupted_import_resumes_only_missing_frozen_tools(disposed_engine):
    from scripts.mcp_eval.data import import_tools

    class InterruptingEmbedder(HashEmbedder):
        def __init__(self):
            super().__init__()
            self.batches = 0

        async def embed_documents(self, texts):
            self.batches += 1
            if self.batches == 2:
                raise RuntimeError("interrupted import")
            return await super().embed_documents(texts)

    items = [replace(tool(), tool_id=f"s/tool-{index}", name=f"tool-{index}") for index in range(17)]
    rag = build_rag(embedder=InterruptingEmbedder(), reranker=None, count_tokens=len, sessionmaker=SessionLocal)
    with pytest.raises(RuntimeError, match="interrupted"):
        await import_tools(rag, items)
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(Document)) == 16
    result = await import_tools(rag, items)
    assert result["changed"] == 1
    assert (await import_tools(rag, items))["changed"] == 0


async def test_resume_recovers_torn_rankings_and_both_caches(tmp_path):
    from scripts.mcp_eval.experiment import run_experiment

    rag, tools, questions = experiment_fixture()
    choice = await run_experiment(rag, questions, tools, tmp_path)
    originals = {}
    for name in ("rankings.jsonl", "pair_scores.jsonl", "candidates.jsonl"):
        path = tmp_path / name
        originals[name] = path.read_bytes()
        with path.open("ab") as handle:
            handle.write(b'{"partial":')
    resumed, _, _ = experiment_fixture()
    assert await run_experiment(resumed, questions, tools, tmp_path) == choice
    assert resumed.store.calls == []
    for name, data in originals.items():
        assert (tmp_path / name).read_bytes() == data


async def test_actual_rerank_failure_is_retryable_after_restart(tmp_path):
    from scripts.mcp_eval.data import read_jsonl
    from scripts.mcp_eval.experiment import run_experiment

    class Reranker:
        def __init__(self, fail):
            self.fail = fail

        async def rerank(self, query, docs):
            if self.fail:
                raise TimeoutError("original failure")
            return [1.0 if doc == "b" else 0.0 for doc in docs]

    rag, tools, questions = experiment_fixture()
    rag.searcher._reranker = Reranker(True)
    with pytest.raises(ValueError, match="successful development"):
        await run_experiment(rag, questions, tools, tmp_path)
    path = tmp_path / "rankings.jsonl"
    failed = read_jsonl(path)
    assert any(r["error"] == "TimeoutError: original failure" for r in failed)
    before = path.read_bytes()
    resumed, _, _ = experiment_fixture()
    resumed.searcher._reranker = Reranker(False)
    await run_experiment(resumed, questions, tools, tmp_path)
    assert path.read_bytes().startswith(before)
    recovered = read_jsonl(path)
    for row in failed:
        if row["error"]:
            same = [r for r in recovered if (r["phase"], r["question_id"], r["method"], r["recall"], r["pool"])
                    == (row["phase"], row["question_id"], row["method"], row["recall"], row["pool"])]
            assert len(same) == 2 and same[-1]["error"] is None


def test_candidate_cache_rejects_changed_metadata(tmp_path):
    from scripts.mcp_eval.experiment import CachedCandidates

    path = tmp_path / "candidates.jsonl"
    path.write_text(json.dumps(dict(query="q", recall=20, route="hybrid", hits=[vars(hit("s/a"))], fingerprint="old")) + "\n")
    with pytest.raises(ValueError, match="fingerprint"):
        CachedCandidates(path, "new")


def test_metadata_atomic_creation_never_overwrites_racing_writer(tmp_path, monkeypatch):
    from scripts.mcp_eval import provenance

    path = tmp_path / "metadata.json"
    metadata = {"checkpoint": "ours"}
    original_link = provenance.os.link

    def competing_writer(source, destination):
        path.write_text(json.dumps({"checkpoint": "other"}))
        original_link(source, destination)

    monkeypatch.setattr(provenance.os, "link", competing_writer)
    with pytest.raises(ValueError):
        provenance.ensure_metadata(tmp_path, metadata)
    assert json.loads(path.read_text()) == {"checkpoint": "other"}
    assert not list(tmp_path.glob(".metadata-*"))


def test_fingerprint_ignores_report_wording_but_tracks_retrieval(tmp_path, monkeypatch):
    from scripts.mcp_eval import provenance

    (tmp_path / "scripts/mcp_eval").mkdir(parents=True)
    path = tmp_path / "scripts/mcp_eval/experiment.py"
    path.write_text('async def retrieve():\n    return 1\ndef write_report():\n    return "first"\n')
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    monkeypatch.setattr(provenance, "IMPLEMENTATIONS", {})
    first = provenance.implementation_fingerprint()
    path.write_text('async def retrieve():\n    return 1\ndef write_report():\n    return "second"\n')
    assert provenance.implementation_fingerprint() == first
    path.write_text('async def retrieve():\n    return 2\ndef write_report():\n    return "second"\n')
    assert provenance.implementation_fingerprint() != first


async def test_recovery_selects_pool_only_for_current_recall(tmp_path):
    from scripts.mcp_eval.data import read_jsonl
    from scripts.mcp_eval.experiment import run_experiment

    rag, tools, questions = experiment_fixture()
    await run_experiment(rag, questions, tools, tmp_path)
    path = tmp_path / "rankings.jsonl"
    records = read_jsonl(path)
    for row in records:
        if row["split"] == "dev" and row["method"] == "rerank":
            if row["phase"] == "recall_sweep":
                row["ranked_ids"] = ["s/a", "s/b"] if row["recall"] == 20 else ["s/a"]
            elif row["phase"] == "pool_sweep":
                row["ranked_ids"] = ["s/a", "s/b"] if row["pool"] == 20 else ["s/a"]
    recovered = next(row for row in records if row["phase"] == "recall_sweep"
                     and row["method"] == "rerank" and row["recall"] == 20)
    failure = {**recovered, "error": "TimeoutError: before recovery", "reranked": False}
    old_pool = {**next(row for row in records if row["phase"] == "pool_sweep" and row["method"] == "rerank"),
                "recall": 40, "pool": 10, "ranked_ids": ["s/b"], "error": None}
    # Prior recall=40 pool results survive after a retry makes recall=20 the current choice.
    records = [failure, *[row for row in records if row["phase"] != "selected"], old_pool]
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    prior = path.read_bytes()

    resumed, _, _ = experiment_fixture()
    choice = await run_experiment(resumed, questions, tools, tmp_path)
    assert (choice["recall"], choice["pool"]) == (20, 20)
    assert path.read_bytes().startswith(prior)
    selected = [row for row in read_jsonl(path) if row["phase"] == "selected"]
    assert selected and all((row["recall"], row["pool"]) == (20, 20) for row in selected)


@pytest.mark.parametrize("ranked,hit_count,zero_count,partial_count,complete_count", [
    (["s/a"], 1, 0, 1, 0),
    (["s/wrong"], 0, 1, 0, 0),
    (["s/a", "s/b"], 1, 0, 0, 1),
])
def test_report_distinguishes_partial_coverage_from_zero_hit(
    tmp_path, ranked, hit_count, zero_count, partial_count, complete_count
):
    from scripts.mcp_eval.experiment import write_report

    (tmp_path / "summary.csv").write_text("phase,split,origin,method,k,ragas_precision_nan\n")
    row = dict(phase="selected", split="test", question_id="q-multiple", query="two relevant tools",
               method="rerank", recall=20, pool=20, references=["s/a", "s/b"], ranked_ids=ranked,
               candidate_ids=["s/a", "s/b", "s/wrong"], pool_ids=["s/a", "s/b", "s/wrong"],
               error=None, reranked=True)
    (tmp_path / "rankings.jsonl").write_text(json.dumps(row) + "\n")
    report = write_report(tmp_path, {"dataset_sha256": "fixture"}, {"recall": 20, "pool": 20}).read_text()

    assert f"Top5 至少命中一个标注工具: {hit_count} / 1 题。" in report
    assert f"Top5 零命中 (zero_hit): {zero_count} / 1 题。" in report
    assert f"Top5 部分覆盖 (partial_coverage): {partial_count} / 1 题。" in report
    assert f"Top5 完整覆盖全部标注工具: {complete_count} / 1 题。" in report
    assert "未出现 Top5 漏召回" not in report
    if partial_count:
        partial = report.split("### 部分覆盖样例", 1)[1]
        assert "q-multiple: two relevant tools" in partial
        assert "缺失 ID: s/b; Top5 排名 ID: s/a" in partial
    elif zero_count:
        zero_hit = report.split("### 零命中样例", 1)[1].split("### 部分覆盖样例", 1)[0]
        assert "q-multiple: two relevant tools" in zero_hit
        assert "缺失 ID: s/a, s/b; Top5 排名 ID: s/wrong" in zero_hit
    else:
        assert "q-multiple: two relevant tools" not in report
