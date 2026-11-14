"""Import and evaluate a frozen MCP tool corpus, never execute any target tool.

uv run --group eval python -m scripts.eval_mcp_tools run --output PATH
uv run --group eval python -m scripts.eval_mcp_tools score --output PATH
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

os.environ["RAGAS_DO_NOT_TRACK"] = "true"

from app.config import settings
from app.rag.bootstrap import build_rag
from scripts.mcp_eval.budget import TOOL_CHUNK_MAX_TOKENS, validate_tool_token_budget
from scripts.mcp_eval.data import dataset_hash, evaluation_url, import_tools, load_dataset, open_database, read_runtime_jsonl
from scripts.mcp_eval.experiment import run_experiment, summarize, write_report, write_summary
from scripts.mcp_eval.provenance import database_metadata, ensure_metadata, model_fingerprint, runtime_metadata


async def execute(args) -> None:
    if args.command == "score":
        rows = await summarize(read_runtime_jsonl(args.output / "rankings.jsonl"))
        write_summary(args.output / "summary.csv", rows)
        metadata = json.loads((args.output / "metadata.json").read_text())
        selection = json.loads((args.output / "selection.json").read_text())
        print(write_report(args.output, metadata, selection))
        return
    tools, questions = load_dataset(args.dataset)
    if len(tools) != 200 or {t.origin: sum(x.origin == t.origin for x in tools) for t in tools} != {"local": 100, "public": 100}:
        raise ValueError("the frozen benchmark requires 100 local + 100 public tools")
    if not all(any(t.tool_id in q["relevant_tool_ids"] for q in questions) for t in tools):
        raise ValueError("every tool needs at least one labeled question")
    if {q["split"] for q in questions} != {"dev", "test"}:
        raise ValueError("both development and test questions required")
    evaluation_url(args.database_url)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(Path(settings.rag_model_dir) / "bge-reranker-v2-m3"), local_files_only=True)
    lengths = validate_tool_token_budget(tools, tokenizer)
    args.output.mkdir(parents=True, exist_ok=True)
    models = model_fingerprint(settings.rag_model_dir)
    engine, sessionmaker = await open_database(args.database_url)
    try:
        metadata = runtime_metadata(dataset_hash(args.dataset), models,
                                    await database_metadata(engine, args.database_url), len(tools), len(questions))
        metadata["tool_chunk_max_tokens"] = TOOL_CHUNK_MAX_TOKENS
        ensure_metadata(args.output, metadata)
        rag = build_rag(sessionmaker=sessionmaker)
        print(await import_tools(rag, tools, fingerprint=models["bge-m3"]), flush=True)
        if args.command == "import":
            return
        # Count actual query/passage token pairs, not character lengths, without changing the corpus.
        query_lengths = [len(tokenizer.encode(q["query"], add_special_tokens=False)) for q in questions]
        special = tokenizer.num_special_tokens_to_add(pair=True)
        truncation = {"max_tool_tokens": max(lengths), "pairs_over_512": sum(
            q + t + special > 512 for q in query_lengths for t in lengths
        ), "possible_pairs": len(tools) * len(questions)}
        (args.output / "truncation.json").write_text(json.dumps(truncation, indent=2) + "\n")
        choice = await run_experiment(rag, questions, tools, args.output)
        print(write_report(args.output, metadata, choice), flush=True)
    finally:
        await engine.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline MCP tool retrieval evaluation")
    parser.add_argument("command", choices=("import", "run", "score"))
    parser.add_argument("--dataset", type=Path, default=Path("eval/mcp_tools"))
    parser.add_argument("--output", type=Path, required=True)
    default_url = evaluation_url(settings.database_url.rsplit("/", 1)[0] + "/sagent_rag_eval")
    parser.add_argument("--database-url", default=default_url.render_as_string(hide_password=False))
    args = parser.parse_args(argv)
    asyncio.run(execute(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
