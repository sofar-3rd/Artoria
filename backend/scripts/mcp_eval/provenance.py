"""Fingerprints for the behavior and data that make persisted evaluation results reusable."""

import ast
import hashlib
import importlib.metadata
import json
import os
import tempfile
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import settings

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATIONS = {
    "fts": "app/rag/persistence/fts.py",
    "store": "app/rag/persistence/store.py",
    "models": "app/rag/persistence/models.py",
    "embedding": "app/rag/inference/embedding.py",
    "rerank": "app/rag/inference/rerank.py",
    "inference_text": "app/rag/inference/text.py",
    "compute": "app/rag/inference/compute.py",
    "retrieval": "app/rag/retrieval/search.py",
    "bootstrap": "app/rag/bootstrap.py",
    "types": "app/rag/core/types.py",
    "data": "scripts/mcp_eval/data.py",
    "tool_budget": "scripts/mcp_eval/budget.py",
    "metrics": "scripts/mcp_eval/metrics.py",
    "provenance": "scripts/mcp_eval/provenance.py",
}
DEPENDENCIES = ("ragas", "jieba", "torch", "transformers", "tokenizers", "sentence-transformers",
                "numpy", "pgvector", "psycopg", "sqlalchemy", "sentencepiece", "safetensors")


def implementation_fingerprint() -> dict:
    hashes = {name: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
              for name, path in IMPLEMENTATIONS.items()}
    # Report wording is not retrieval behavior. Hash the owning runtime definitions, not the CLI.
    source = (ROOT / "scripts/mcp_eval/experiment.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    behavior = [node for node in tree.body if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                or node.name != "write_report"]
    hashes["experiment"] = hashlib.sha256(ast.dump(ast.Module(body=behavior, type_ignores=[])).encode()).hexdigest()
    return hashes


def dependency_versions() -> dict:
    versions = {}
    for name in DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def import_behavior_fingerprint() -> dict:
    keys = ("fts", "embedding", "inference_text", "store", "models", "data", "bootstrap")
    hashes = implementation_fingerprint()
    versions = dependency_versions()
    return {"implementation": {key: hashes[key] for key in keys},
            "dependencies": {key: versions[key] for key in ("jieba", "torch", "transformers", "tokenizers",
                                                           "sentence-transformers", "numpy", "sentencepiece")},
            "device": settings.rag_device}


def model_fingerprint(directory: str) -> dict:
    root = Path(directory)
    records = {}
    for model in ("bge-m3", "bge-reranker-v2-m3"):
        records[model] = {}
        for file in sorted((root / model).rglob("*")):
            relative = file.relative_to(root / model)
            if file.is_file() and not any(part.startswith(".") for part in relative.parts):
                with file.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                records[model][relative.as_posix()] = {"size": file.stat().st_size, "sha256": digest}
        if not records[model]:
            raise ValueError(f"missing model files: {model}")
    return records


async def database_metadata(engine, value: str) -> dict:
    url = make_url(value)
    async with engine.connect() as conn:
        postgres_version = await conn.scalar(text("SHOW server_version"))
        actual = (await conn.execute(text(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
        ))).one()
        extensions = dict((await conn.execute(text(
            "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_textsearch')"
        ))).all())
        options = await conn.scalar(text("SELECT reloptions FROM pg_class WHERE oid='ix_chunks_bm25'::regclass"))
    if set(extensions) != {"vector", "pg_textsearch"}:
        raise ValueError("evaluation database extensions are missing")
    # Include configured routing (including libpq host overrides) and the server actually reached.
    endpoint = [url.host, url.port or 5432, url.database,
                {key: url.query[key] for key in ("host", "hostaddr", "port", "service") if key in url.query},
                list(actual)]
    return {"name": actual[0], "endpoint_sha256": hashlib.sha256(json.dumps(endpoint, sort_keys=True).encode()).hexdigest(),
            "postgres_version": postgres_version, "extensions": extensions, "bm25_index_options": sorted(options or [])}


def runtime_metadata(dataset_sha256, models, database, tools, questions) -> dict:
    from app.rag.inference.rerank import MAX_LENGTH

    return {"format_version": 2, "dataset_sha256": dataset_sha256, "models": models,
            "implementation_sha256": implementation_fingerprint(), "dependencies": dependency_versions(),
            "device": settings.rag_device, "rerank_timeout_s": settings.rag_rerank_timeout_s,
            "bm25": {"k1": 1.2, "b": 0.75}, "rrf_k": 60, "top_k": [1, 3, 5, 10],
            "tools": tools, "questions": questions, "database": database,
            "rerank_max_tokens": MAX_LENGTH, "precision_empty_policy": "raw NaN, aggregate 0", "telemetry": False}


def ensure_metadata(output: Path, metadata: dict) -> None:
    path = output / "metadata.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != metadata:
            raise ValueError("dataset/model/implementation/database/settings changed: choose a new output directory")
        return
    if any(output.glob("*.jsonl")):
        raise ValueError("runtime artifacts without matching metadata: choose a new output directory")
    fd, temporary = tempfile.mkstemp(prefix=".metadata-", dir=output)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if json.loads(path.read_text(encoding="utf-8")) != metadata:
                raise ValueError("concurrent evaluation created incompatible metadata") from None
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
