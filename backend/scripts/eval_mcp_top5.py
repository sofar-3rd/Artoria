"""Fixed 20/20/5 evaluation of the expanded corpus, grouped by number of relevant tools."""

import argparse
import asyncio
import hashlib
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ["RAGAS_DO_NOT_TRACK"] = "true"

from app.config import settings
from app.models import Base
from app.rag.bootstrap import build_rag
from app.rag.persistence.models import ChunkRow, Document, KnowledgeBase
from scripts.mcp_eval.budget import TOOL_CHUNK_MAX_TOKENS, validate_tool_token_budget
from scripts.mcp_eval.data import dataset_hash, evaluation_url, import_tools, load_dataset, read_runtime_jsonl
from scripts.mcp_eval.experiment import CachedCandidates, CachedEmbedder, CachedReranker, METHODS, retrieve, write_summary
from scripts.mcp_eval.metrics import score_ranking
from scripts.mcp_eval.provenance import database_metadata, ensure_metadata, model_fingerprint, runtime_metadata

SCHEMA = "mcp_tools_256"


async def open_variant_database(value: str):
    url = evaluation_url(value)
    if url.query:
        raise ValueError("variant evaluation does not accept database URL options")
    engine = create_async_engine(url.set(drivername="postgresql+psycopg"),
                                 connect_args={"options": f"-c search_path={SCHEMA},public"},
                                 execution_options={"schema_translate_map": {None: SCHEMA}})
    try:
        async with engine.begin() as conn:
            if await conn.scalar(text("SELECT current_database()")) != "sagent_rag_eval":
                raise ValueError("not connected to the evaluation database")
            extensions = dict((await conn.execute(text(
                "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_textsearch')"
            ))).all())
            if set(extensions) != {"vector", "pg_textsearch"}:
                raise ValueError("evaluation database needs vector and pg_textsearch extensions")
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
            await conn.run_sync(lambda c: Base.metadata.create_all(
                c, tables=[KnowledgeBase.__table__, Document.__table__, ChunkRow.__table__]
            ))
            index_schema, raw_options = (await conn.execute(text(
                "SELECT n.nspname, c.reloptions FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.oid='ix_chunks_bm25'::regclass"
            ))).one()
            options = dict(item.split("=", 1) for item in raw_options)
            if (index_schema != SCHEMA or options.get("text_config") != "simple"
                    or float(options.get("k1", "1.2")) != 1.2 or float(options.get("b", "0.75")) != 0.75):
                raise ValueError("variant BM25 index must be isolated and use simple, k1=1.2, b=0.75")
        return engine, async_sessionmaker(engine, expire_on_commit=False)
    except BaseException:
        await engine.dispose()
        raise


async def grouped_scores(records: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in records:
        count = len(set(row["references"]))
        scores = await score_ranking(row["ranked_ids"], row["references"], 5)
        scores["rerank_failures"] = int(row.get("error") is not None)
        for label in (count, "all"):
            groups[row["method"], label].append(scores)
    result = []
    for (method, label), scores in sorted(groups.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        result.append({"method": method, "correct_tools": label, "questions": len(scores),
                       "recall_at_5": statistics.fmean(s["recall"] for s in scores),
                       "mrr_at_5": statistics.fmean(s["mrr"] for s in scores),
                       "hit_at_5": statistics.fmean(s["hit"] for s in scores),
                       "rerank_failures": sum(s["rerank_failures"] for s in scores)})
    return result


async def execute(args):
    tools, questions = load_dataset(args.dataset)
    if len(tools) != 200 or len(questions) != 400:
        raise ValueError("expected the frozen 200-tool, 400-question corpus")
    test = [q for q in questions if q["split"] == "test"]
    if not test:
        raise ValueError("test split is empty")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(Path(settings.rag_model_dir) / "bge-reranker-v2-m3"), local_files_only=True)
    lengths = validate_tool_token_budget(tools, tokenizer)
    max_query = max(len(tokenizer.encode(q["query"], add_special_tokens=False)) for q in test)
    max_pair = max(lengths) + max_query + tokenizer.num_special_tokens_to_add(pair=True)
    if max_pair > 512:
        raise ValueError("a query/chunk pair could exceed the reranker limit")
    args.output.mkdir(parents=True, exist_ok=True)
    models = model_fingerprint(settings.rag_model_dir)
    engine, sessionmaker = await open_variant_database(args.database_url)
    try:
        metadata = runtime_metadata(dataset_hash(args.dataset), models,
                                    await database_metadata(engine, args.database_url), len(tools), len(test))
        metadata.update(schema=SCHEMA, recall=20, pool=20, top_k=[5], split="test",
                        tool_chunk_max_tokens=TOOL_CHUNK_MAX_TOKENS, max_pair_tokens=max_pair,
                        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        ensure_metadata(args.output, metadata)
        fingerprint = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        rag = build_rag(sessionmaker=sessionmaker)
        imported = await import_tools(rag, tools, fingerprint=models["bge-m3"])
        print({"tools": imported["tools"], "changed": imported["changed"], "test_questions": len(test)}, flush=True)
        kb = await rag.store.get_kb("mcp-tools")
        rag.embedder = CachedEmbedder(rag.embedder)
        rag.searcher._reranker = CachedReranker(rag.searcher._reranker, args.output / "pair_scores.jsonl", fingerprint)
        rag._eval_candidates = CachedCandidates(args.output / "candidates.jsonl", fingerprint)
        path = args.output / "rankings.jsonl"
        latest = {}
        for row in read_runtime_jsonl(path):
            if row.get("fingerprint") != fingerprint:
                raise ValueError("ranking checkpoint differs")
            latest[row["question_id"], row["method"]] = row
        with path.open("a", encoding="utf-8") as handle:
            for i, q in enumerate(test):
                for method in METHODS:
                    key = q["id"], method
                    if key in latest and latest[key].get("error") is None:
                        continue
                    outcome = await retrieve(rag, kb.id, q["query"], 20, 20, method)
                    row = {**outcome, "question_id": q["id"], "query": q["query"], "split": "test",
                           "references": q["relevant_tool_ids"], "method": method, "recall": 20,
                           "pool": 20, "top_k": 5, "fingerprint": fingerprint}
                    handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                    handle.flush()
                    latest[key] = row
                if (i + 1) % 10 == 0:
                    print(f"test: {i + 1}/{len(test)}", flush=True)
        records = list(latest.values())
        if len(records) != len(test) * len(METHODS):
            raise ValueError("incomplete or foreign ranking records")
        summary = await grouped_scores(records)
        write_summary(args.output / "summary.csv", summary)
        lines = ["# 256-token 工具描述 Top5 评测", "", "每路召回 N=20，重排候选 M=20，最终 K=5；仅评测固定测试集，不调参。",
                 "每题先计算 Recall@5 和 MRR@5，再按标注正确工具数分组取平均；多标签为可替代工具，不是必须联合调用。", "",
                 "|方案|标注正确工具数|题数|Recall@5|MRR@5|Hit@5|重排失败|", "|---|---|---:|---:|---:|---:|---:|"]
        for r in summary:
            lines.append(f"|{r['method']}|{r['correct_tools']}|{r['questions']}|{r['recall_at_5']:.4%}|{r['mrr_at_5']:.4f}|{r['hit_at_5']:.4%}|{r['rerank_failures']}|")
        lines += ["", f"200个工具仍一工具一chunk，预算上限256tokens；实际最大{max(lengths)}tokens，最大测试输入对{max_pair}tokens，不截断。",
                  "新版位于独立schema mcp_tools_256，未覆盖public中的旧语料。排名、候选、分数和模型/实现/数据指纹随结果保存。",
                  "标签是离线整理而非独立金标准，3个正确工具的测试题很少，不据此作稳健泛化结论。"]
        (args.output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("eval/mcp_tools_256"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database-url", default=settings.database_url.rsplit("/", 1)[0] + "/sagent_rag_eval")
    asyncio.run(execute(parser.parse_args()))


if __name__ == "__main__":
    main()
