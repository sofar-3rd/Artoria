import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.rag.core.errors import UnknownKnowledgeBase
from app.rag.core.types import Chunk
from app.rag.inference.text import MAX_DOCUMENT_CHARS, MAX_QUERY_CHARS
from app.rag.persistence import fts
from app.rag.persistence.models import ChunkRow, Document, KnowledgeBase
from scripts.mcp_eval.provenance import import_behavior_fingerprint

EVAL_DATABASE = "sagent_rag_eval"
KB_NAME = "mcp-tools"


@dataclass(frozen=True)
class Tool:
    tool_id: str
    name: str
    origin: str
    function: str
    when_to_use: str

    @property
    def text(self) -> str:
        return f"工具名称: {self.name}\n功能描述: {self.function}\n使用时机: {self.when_to_use}"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_runtime_jsonl(path: Path) -> list[dict]:
    """Only an unterminated last record can be a torn append; earlier corruption is fatal."""
    if not path.exists():
        return []
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    rows, offset = [], 0
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            incomplete = False
            decoded = line.decode("utf-8", errors="ignore").rstrip()
            try:
                json.loads(decoded)
            except json.JSONDecodeError as error:
                tail = decoded[error.pos:]
                incomplete = (error.pos == len(decoded) or error.msg.startswith("Unterminated string")
                              or (error.msg == "Expecting value" and tail in ("n", "nu", "nul", "t", "tr", "tru", "f", "fa", "fal", "fals", "-"))
                              or (error.msg == "Expecting ',' delimiter" and tail in (".", "e", "e+", "e-", "E", "E+", "E-")))
            if (index != len(lines) - 1 or line.endswith(b"\n") or not incomplete
                    or (isinstance(exc, UnicodeDecodeError) and exc.reason != "unexpected end of data")):
                raise ValueError(f"corrupt runtime JSONL at {path.name}:{index + 1}") from exc
            with path.open("r+b") as handle:
                handle.truncate(offset)
            return rows
        if not isinstance(row, dict):
            raise ValueError(f"non-object runtime JSONL at {path.name}:{index + 1}")
        rows.append(row)
        offset += len(line)
    if data and not data.endswith(b"\n"):
        with path.open("ab") as handle:
            handle.write(b"\n")
    return rows


def validate_text_lengths(tools: list[Tool], questions: list[dict]) -> None:
    for tool in tools:
        if len(tool.text) > MAX_DOCUMENT_CHARS:
            raise ValueError(f"tool length exceeds adapter limit: {tool.tool_id}")
    for question in questions:
        if len(question["query"]) > MAX_QUERY_CHARS:
            raise ValueError(f"query length exceeds adapter limit: {question['id']}")


def load_dataset(directory: Path) -> tuple[list[Tool], list[dict]]:
    tools = [Tool(**row) for row in read_jsonl(directory / "tools.jsonl")]
    ids = {t.tool_id for t in tools}
    if not tools or len(ids) != len(tools):
        raise ValueError("tools must be non-empty and have unique IDs")
    for t in tools:
        if (not all(isinstance(v, str) and v.strip() for v in vars(t).values())
                or t.origin not in {"local", "public"} or "/" not in t.tool_id):
            raise ValueError(f"invalid tool: {t.tool_id}")
    questions = read_jsonl(directory / "questions.jsonl")
    question_ids, intents = set(), {}
    for q in questions:
        if (not q.get("id") or q["id"] in question_ids or not q.get("query", "").strip()
                or not q.get("intent_id") or q.get("split") not in {"dev", "test"}
                or not q.get("relevant_tool_ids")):
            raise ValueError(f"invalid question: {q.get('id')}")
        if not set(q["relevant_tool_ids"]) <= ids:
            raise ValueError(f"unknown tool label in {q['id']}")
        if q["intent_id"] in intents and intents[q["intent_id"]] != q["split"]:
            raise ValueError(f"intent leaks across splits: {q['intent_id']}")
        intents[q["intent_id"]] = q["split"]
        question_ids.add(q["id"])
    if not questions:
        raise ValueError("questions must not be empty")
    validate_text_lengths(tools, questions)
    return tools, questions


def dataset_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for name in ("tools.jsonl", "questions.jsonl"):
        digest.update(name.encode())
        digest.update((directory / name).read_bytes())
    return digest.hexdigest()


def evaluation_url(value: str):
    url = make_url(value)
    if url.get_backend_name() != "postgresql" or url.database != EVAL_DATABASE:
        raise ValueError(f"evaluation requires a PostgreSQL database named exactly {EVAL_DATABASE}")
    return url


async def open_database(value: str):
    url = evaluation_url(value)
    admin = url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (EVAL_DATABASE,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(EVAL_DATABASE)))
    engine = create_async_engine(url.set(drivername="postgresql+psycopg"))
    try:
        async with engine.begin() as conn:
            if await conn.scalar(text("SELECT current_database()")) != EVAL_DATABASE:
                raise ValueError("connected to a non-evaluation database")
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_textsearch"))
            # Only the three RAG tables are needed; no chat/checkpoint data is created or touched.
            from app.models import Base
            from app.rag.persistence.models import KnowledgeBase

            await conn.run_sync(lambda c: Base.metadata.create_all(
                c, tables=[KnowledgeBase.__table__, Document.__table__, ChunkRow.__table__]
            ))
            options = await conn.scalar(text("SELECT reloptions FROM pg_class WHERE oid='ix_chunks_bm25'::regclass"))
            options = dict(item.split("=", 1) for item in options)
            if (options.get("text_config") != "simple" or float(options.get("k1", "1.2")) != 1.2
                    or float(options.get("b", "0.75")) != 0.75):
                raise ValueError("evaluation BM25 index must use simple, k1=1.2, b=0.75")
        return engine, async_sessionmaker(engine, expire_on_commit=False)
    except BaseException:
        await engine.dispose()
        raise


async def validate_corpus(store, tools: list[Tool], kb_id=None, *, complete=False) -> None:
    frozen = {t.tool_id: t for t in tools}
    async with store._sm() as session:
        kbs = (await session.scalars(select(KnowledgeBase))).all()
        if any(k.name != KB_NAME or (kb_id is not None and k.id != kb_id) for k in kbs):
            raise ValueError("foreign knowledge base in evaluation database")
        if kb_id is None and kbs:
            kb_id = kbs[0].id
        documents = (await session.scalars(select(Document))).all()
        chunks = (await session.scalars(select(ChunkRow))).all()
    by_doc = {}
    for chunk in chunks:
        if chunk.kb_id != kb_id:
            raise ValueError("foreign chunk in evaluation database")
        by_doc.setdefault(chunk.doc_id, []).append(chunk)
    if set(by_doc) - {doc.id for doc in documents}:
        raise ValueError("foreign orphan chunk in evaluation database")
    for doc in documents:
        if doc.kb_id != kb_id or doc.path not in frozen:
            raise ValueError("foreign document in evaluation database")
        expected = frozen[doc.path].text
        if doc.content != expected or doc.content_sha != hashlib.sha256(expected.encode()).hexdigest():
            raise ValueError(f"document differs from frozen tool: {doc.path}")
        rows = by_doc.get(doc.id, [])
        if len(rows) != 1:
            raise ValueError("every tool must have exactly one chunk")
        chunk = rows[0]
        if (chunk.content != expected or chunk.search_text != fts.search_text(expected)
                or chunk.idx != 0 or chunk.start_char != 0 or chunk.end_char != len(expected)
                or chunk.heading_path):
            raise ValueError(f"chunk differs from frozen tool: {doc.path}")
    if complete and {doc.path for doc in documents} != set(frozen):
        raise ValueError("frozen evaluation corpus is incomplete")


async def import_tools(rag, tools: list[Tool], fingerprint=None) -> dict:
    validate_text_lengths(tools, [])
    embedding = fingerprint if fingerprint is not None else {"model": rag.embedder.model, "dim": rag.embedder.dim}
    state = {"embedding": embedding, "behavior": import_behavior_fingerprint(),
             "corpus": hashlib.sha256(json.dumps(
                 [(t.tool_id, t.text) for t in sorted(tools, key=lambda t: t.tool_id)],
                 ensure_ascii=False, separators=(",", ":")
             ).encode()).hexdigest()}
    revision = "mcp-eval-v2:" + json.dumps(state, sort_keys=True, separators=(",", ":"))
    await validate_corpus(rag.store, tools)
    try:
        kb = await rag.store.get_kb(KB_NAME)
    except UnknownKnowledgeBase:
        kb = await rag.store.create_kb(KB_NAME, "MCP tool evaluation", "offline:tools", "frozen", "",
                                       rag.embedder.model, rag.embedder.dim)
    if (kb.embed_model, kb.embed_dim) != (rag.embedder.model, rag.embedder.dim):
        raise ValueError("evaluation corpus embedding model differs; use a matching model")
    local = await rag.store.doc_shas(kb.id)
    if local and kb.last_commit != revision:
        raise ValueError("nonempty evaluation database has incompatible or missing import fingerprint")
    await validate_corpus(rag.store, tools, kb.id)
    # Persist the compatible state before the first document so a torn import can resume safely.
    if kb.last_commit != revision:
        await rag.store._update_kb(kb.id, last_commit=revision, synced_at=None)
    changed = [t for t in tools if local.get(t.tool_id) != hashlib.sha256(t.text.encode()).hexdigest()]
    for start in range(0, len(changed), 16):
        batch = changed[start:start + 16]
        vectors = await rag.embedder.embed_documents([t.text for t in batch])
        for t, vector in zip(batch, vectors, strict=True):
            sha = hashlib.sha256(t.text.encode()).hexdigest()
            chunk = Chunk(0, "", t.text, t.text, 0, len(t.text))
            await rag.store.replace_document(kb.id, t.tool_id, "", t.text, sha, [chunk], [vector])
        print(f"indexed {min(start + 16, len(changed))}/{len(changed)} tools", flush=True)
    await validate_corpus(rag.store, tools, kb.id, complete=True)
    await rag.store.mark_synced(kb.id, revision)
    return {"tools": len(tools), "changed": len(changed), "revision": revision}
