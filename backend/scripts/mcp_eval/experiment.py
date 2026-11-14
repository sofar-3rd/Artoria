import asyncio
import csv
import hashlib
import json
import math
import statistics
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from app.config import settings
from app.rag.core.types import Hit
from app.rag.retrieval.search import _validate_scores
from scripts.mcp_eval.data import read_runtime_jsonl, validate_text_lengths
from scripts.mcp_eval.metrics import score_ranking
from scripts.mcp_eval.provenance import dependency_versions, implementation_fingerprint

TOP_K = (1, 3, 5, 10)
METHODS = ("bm25", "hybrid", "rerank")


async def retrieve(rag, kb_id, query: str, recall: int, pool: int, method: str) -> dict:
    if method not in METHODS or min(recall, pool) < 1:
        raise ValueError("unknown method or non-positive candidate count")
    validate_text_lengths([], [{"id": "retrieval", "query": query}])
    start = time.perf_counter()
    cache = getattr(rag, "_eval_candidates", None)
    if cache is not None:
        candidates = await cache.get(rag, kb_id, query, recall, "bm25" if method == "bm25" else "hybrid")
    elif method == "bm25":
        candidates = await rag.store.bm25_candidates([kb_id], query, recall)
    else:
        vector = await rag.embedder.embed_query(query)
        # Keep the full route union for candidate coverage, then measure the fused pool separately.
        candidates = await rag.store.hybrid_candidates([kb_id], query, vector, recall, 2 * recall, 60)
    hits = candidates[:pool]
    reranked, error = False, None
    if method == "rerank" and hits:
        try:
            scores = await asyncio.wait_for(
                rag.searcher._reranker.rerank(query, [h.content for h in hits]), settings.rag_rerank_timeout_s
            )
            _validate_scores(scores, len(hits))
            hits = [hits[i] for i in sorted(range(len(hits)), key=lambda i: -scores[i])]
            reranked = True
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    return {
        "candidate_ids": [h.path for h in candidates], "pool_ids": [h.path for h in candidates[:pool]],
        "ranked_ids": [h.path for h in hits], "scores": [h.score for h in hits] if not reranked else [float(scores[i]) for i in sorted(range(len(scores)), key=lambda i: -scores[i])],
        "reranked": reranked, "error": error, "elapsed_s": time.perf_counter() - start,
    }


class CachedEmbedder:
    def __init__(self, base):
        self.base = base
        self.queries = {}

    async def embed_query(self, query):
        if query not in self.queries:
            self.queries[query] = await self.base.embed_query(query)
        return self.queries[query]


class CachedReranker:
    """Pair scoring is independent of pool size; reuse scores without re-running identical pairs."""

    def __init__(self, base, path: Path, fingerprint=None):
        self.base, self.path = base, path
        self.fingerprint = fingerprint or hashlib.sha256(json.dumps({
            "model": f"{type(base).__module__}.{type(base).__qualname__}",
            "implementation": implementation_fingerprint(), "dependencies": dependency_versions(),
            "device": settings.rag_device,
        }, sort_keys=True).encode()).hexdigest()
        self.scores = {}
        for row in read_runtime_jsonl(path):
            if row.get("fingerprint") != self.fingerprint:
                raise ValueError("pair score cache fingerprint differs from current checkpoint")
            _validate_scores([row["score"]], 1)
            self.scores[row["query"], row["content"]] = float(row["score"])

    async def rerank(self, query, docs):
        missing = list(dict.fromkeys(doc for doc in docs if (query, doc) not in self.scores))
        if missing:
            values = await self.base.rerank(query, missing)
            _validate_scores(values, len(missing))
            with self.path.open("a", encoding="utf-8") as handle:
                for doc, score in zip(missing, values, strict=True):
                    handle.write(json.dumps({"query": query, "content": doc, "score": float(score),
                                             "fingerprint": self.fingerprint}, ensure_ascii=False, allow_nan=False) + "\n")
                    handle.flush()
                    self.scores[query, doc] = float(score)
        return [self.scores[query, doc] for doc in docs]


class CachedCandidates:
    def __init__(self, path: Path, fingerprint: str):
        self.path, self.fingerprint = path, fingerprint
        self.candidates = {}
        for row in read_runtime_jsonl(path):
            if row.get("fingerprint") != fingerprint:
                raise ValueError("candidate cache fingerprint differs from current checkpoint")
            self.candidates[row["query"], row["recall"], row["route"]] = [Hit(**hit) for hit in row["hits"]]

    async def get(self, rag, kb_id, query, recall, route):
        key = (query, recall, route)
        if key not in self.candidates:
            if route == "bm25":
                hits = await rag.store.bm25_candidates([kb_id], query, recall)
            else:
                vector = await rag.embedder.embed_query(query)
                hits = await rag.store.hybrid_candidates([kb_id], query, vector, recall, 2 * recall, 60)
            row = dict(query=query, recall=recall, route=route, hits=[asdict(hit) for hit in hits],
                       fingerprint=self.fingerprint)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
            self.candidates[key] = hits
        return self.candidates[key]


def latest_rankings(rankings: list[dict]) -> list[dict]:
    return list({(row["phase"], row["question_id"], row["method"], row["recall"], row["pool"]): row
                 for row in rankings}.values())


async def summarize(rankings: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in latest_rankings(rankings):
        for k in TOP_K:
            scores = await score_ranking(row["ranked_ids"], row["references"], k)
            refs = set(row["references"])
            scores["candidate_recall"] = len(refs & set(row["candidate_ids"])) / len(refs)
            scores["pool_recall"] = len(refs & set(row["pool_ids"])) / len(refs)
            scores["empty"] = float(not row["ranked_ids"])
            scores["rerank_failures"] = float(row["method"] == "rerank" and row["error"] is not None)
            for origin in ("all", row["origin"]):
                key = (row["phase"], row["split"], origin, row["method"], row["recall"], row["pool"], k)
                groups[key].append(scores)
    result = []
    for key, values in sorted(groups.items()):
        phase, split, origin, method, recall, pool, k = key
        item = dict(phase=phase, split=split, origin=origin, method=method, recall=recall, pool=pool, k=k, queries=len(values))
        for metric in ("precision", "recall", "hit", "mrr", "returned", "candidate_recall", "pool_recall"):
            label = "recall_at_k" if metric == "recall" else metric
            item[label] = statistics.fmean(v[metric] for v in values)
        item["empty_results"] = sum(int(v["empty"]) for v in values)
        item["ragas_precision_nan"] = sum(math.isnan(v["ragas_precision"]) for v in values)
        item["rerank_failures"] = sum(int(v["rerank_failures"]) for v in values)
        result.append(item)
    return result


def select_configuration(rows: list[dict]) -> dict:
    eligible = [r for r in rows if r["split"] == "dev" and r["origin"] == "all"
                and r["method"] == "rerank" and r["k"] == 5 and not r.get("rerank_failures", 0)]
    if not eligible:
        raise ValueError("no successful development configurations to select")
    return max(eligible, key=lambda r: (r["recall_at_k"], r["mrr"], -r["recall"], -r["pool"]))


async def run_experiment(rag, questions: list[dict], tools, output: Path) -> dict:
    validate_text_lengths(tools, questions)
    kb = await rag.store.get_kb("mcp-tools")
    ranking_path = output / "rankings.jsonl"
    existing = read_runtime_jsonl(ranking_path)
    done = {(r["phase"], r["question_id"], r["method"], r["recall"], r["pool"]): r for r in existing}
    retrievals = {(r["query"], r["method"], r["recall"], r["pool"]): r for r in existing}
    origins = {t.tool_id: t.origin for t in tools}
    metadata_path = output / "metadata.json"
    if metadata_path.exists():
        checkpoint = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        checkpoint = {"tools": [(t.tool_id, t.text) for t in tools], "questions": questions,
                      "embedding": [getattr(rag.embedder, "model", type(rag.embedder).__qualname__),
                                    getattr(rag.embedder, "dim", None)],
                      "reranker": f"{type(rag.searcher._reranker).__module__}.{type(rag.searcher._reranker).__qualname__}",
                      "implementation": implementation_fingerprint(), "dependencies": dependency_versions(),
                      "device": settings.rag_device, "timeout": settings.rag_rerank_timeout_s}
    fingerprint = hashlib.sha256(json.dumps(checkpoint, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if any(row.get("fingerprint") != fingerprint for row in existing):
        raise ValueError("rankings fingerprint differs from current checkpoint")
    rag.embedder = CachedEmbedder(rag.embedder)
    rag.searcher._reranker = CachedReranker(rag.searcher._reranker, output / "pair_scores.jsonl", fingerprint)
    rag._eval_candidates = CachedCandidates(output / "candidates.jsonl", fingerprint)

    async def stage(phase, split, configurations):
        qs = [q for q in questions if q["split"] == split]
        with ranking_path.open("a", encoding="utf-8") as handle:
            for index, q in enumerate(qs):
                for method, recall, pool in configurations:
                    key = (phase, q["id"], method, recall, pool)
                    if key in done and not done[key].get("error"):
                        continue
                    cached = retrievals.get((q["query"], method, recall, pool))
                    outcome = cached if cached is not None and not cached.get("error") else await retrieve(rag, kb.id, q["query"], recall, pool, method)
                    origin = {origins[t] for t in q["relevant_tool_ids"]}
                    row = {**outcome, "phase": phase, "question_id": q["id"], "query": q["query"],
                           "references": q["relevant_tool_ids"], "split": split,
                           "origin": next(iter(origin)) if len(origin) == 1 else "mixed",
                           "method": method, "recall": recall, "pool": pool, "fingerprint": fingerprint}
                    handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                    handle.flush()
                    existing.append(row)
                    done[key] = row
                    retrievals[q["query"], method, recall, pool] = row
                if (index + 1) % 10 == 0:
                    print(f"{phase}/{split}: {index + 1}/{len(qs)} questions", flush=True)

    await stage("baseline", "dev", [(m, 40, 20) for m in METHODS])
    await stage("recall_sweep", "dev", [(m, n, 20) for n in (20, 40, 80) for m in METHODS])
    rows = await summarize([r for r in existing if r["phase"] == "recall_sweep"])
    selected_recall = select_configuration(rows)["recall"]
    await stage("pool_sweep", "dev", [(m, selected_recall, n) for n in (10, 20, 40) for m in ("hybrid", "rerank")])
    rows = await summarize([r for r in existing if r["phase"] == "pool_sweep" and r["recall"] == selected_recall])
    selected = select_configuration(rows)
    # The holdout is evaluated only after choices have been locked on the development split.
    await stage("baseline", "test", [(m, 40, 20) for m in METHODS])
    await stage("selected", "test", [(m, selected_recall, selected["pool"]) for m in METHODS])
    summary = await summarize(existing)
    write_summary(output / "summary.csv", summary)
    choice = {"recall": selected_recall, "pool": selected["pool"], "default_top_k": 5,
              "selection": "dev Recall@5, then MRR@5, then fewer candidates", "pair_scores": len(rag.searcher._reranker.scores)}
    (output / "selection.json").write_text(json.dumps(choice, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return choice


def write_summary(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("no rankings to summarize")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(output: Path, metadata: dict, selection: dict) -> Path:
    with (output / "summary.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    def table(title, selected_rows, columns):
        lines.extend(["", f"## {title}", "",
                      "|" + "|".join(label for _, label in columns) + "|",
                      "|" + "|".join("---" for _ in columns) + "|"])
        metrics = {"precision", "recall_at_k", "hit", "mrr", "candidate_recall", "pool_recall"}
        for row in selected_rows:
            values = [f"{float(row[key]):.4f}" if key in metrics else cell(row.get(key, ""))
                      for key, _ in columns]
            lines.append("|" + "|".join(values) + "|")
        if not selected_rows:
            lines.append("暂无该阶段结果。")

    lines = ["# MCP 工具检索评测", "", "## 实验设置", "",
             f"- 语料哈希: `{metadata['dataset_sha256']}`", "- 200 个工具, 每个工具一个 chunk; 文本仅含工具名称、功能描述、使用时机。",
             "- BM25: k1=1.2, b=0.75; RRF: k=60; 向量模型 BGE-M3; 重排模型 BGE-reranker-v2-m3。",
             "- 候选参数仅在开发集选择, 测试集不参与调参。所有配置报告 Top K=1/3/5/10。",
             f"- 选定每路召回 {selection['recall']}, 融合池/重排候选 {selection['pool']}; 默认返回 Top 5。",
             f"- 运行设备: `{metadata.get('device', '未记录')}`; 重排超时: {metadata.get('rerank_timeout_s', '未记录')} 秒。"]
    lines += ["", "## 运行证据", "", "### 依赖版本", "", "|依赖|版本|", "|---|---|"]
    for name, version in sorted(metadata.get("dependencies", {}).items()):
        lines.append(f"|{cell(name)}|{cell(version if version is not None else '未安装')}|")
    lines += ["", "### 模型文件", "", "|模型|文件数|总字节数|MiB|", "|---|---|---|---|"]
    for model, files in sorted(metadata.get("models", {}).items()):
        size = sum(file["size"] for file in files.values())
        lines.append(f"|{cell(model)}|{len(files)}|{size}|{size / 1024 ** 2:.2f}|")
    lines.append("模型文件逐文件 SHA256 和尺寸记录在 metadata.json; 此表只汇总本地文件证据, 不代表推理吞吐或质量。")
    truncation_path = output / "truncation.json"
    lines += ["", "### Token 截断检查", ""]
    if truncation_path.exists():
        truncation = json.loads(truncation_path.read_text(encoding="utf-8"))
        lines += [f"- 工具正文最大 token 数: {truncation['max_tool_tokens']}。",
                  f"- query/正文加特殊 token 后超过 {metadata.get('rerank_max_tokens', 512)} 的组合: "
                  f"{truncation['pairs_over_512']} / {truncation['possible_pairs']}。",
                  "- 来源: truncation.json, 使用实际重排 tokenizer 检查所有可能组合; 不等于实际评分 pair 数。"]
    else:
        lines.append("未找到 truncation.json, 无法核对 tokenizer 截断证据。")

    metric_columns = [("precision", "Precision"), ("recall_at_k", "Recall"), ("hit", "Hit"),
                      ("mrr", "MRR"), ("candidate_recall", "候选召回"), ("pool_recall", "融合池召回"),
                      ("ragas_precision_nan", "原始Precision NaN/null"), ("rerank_failures", "重排失败")]
    dev_columns = [("method", "方案"), ("recall", "每路召回"), ("pool", "池大小"), ("queries", "题数")] + metric_columns
    for phase, title in (("baseline", "开发集基线"), ("recall_sweep", "开发集召回扫描"), ("pool_sweep", "开发集候选池扫描")):
        selected_rows = [row for row in rows if row["phase"] == phase and row["split"] == "dev"
                         and row["origin"] == "all" and int(row["k"]) == 5]
        table(title + " (Top5, all)", selected_rows, dev_columns)
        if phase == "pool_sweep":
            lines.append(f"参数选择只使用当前每路召回 {selection['recall']} 的候选池结果; 表中其他召回值为恢复日志中的历史配置。")
    table("测试集结果", [row for row in rows if row["split"] == "test"],
          [("phase", "阶段"), ("origin", "分组"), ("method", "方案"), ("recall", "每路召回"),
           ("pool", "池大小"), ("k", "K"), ("queries", "题数")] + metric_columns)
    nulls = sum(int(row["ragas_precision_nan"]) for row in rows if row["origin"] == "all")
    lines += ["", "## 原始 Precision 空值", "",
              f"- 原始 Ragas Precision NaN/null 总计: {nulls}, 按最新唯一阶段/配置/问题/K 计数, 仅汇总 all 分组避免来源分组重复计数。",
              "- rankings.jsonl 保存排名, 不保存逐题 Ragas 分数; 上述计数来自 summary.csv 的 ragas_precision_nan, 不是日志中的 JSON null 数量。",
              "- 空召回原始分数为 NaN (JSON 展示时应为 null), 汇总 Precision 按 0 计入; 同题在不同配置或 K 下分别计数。"]
    lines += ["", "## 限制与解释", "",
              "- 这是工具发现检索评测, 不验证模型调用、目标工具是否在线或答案生成质量。公开工具只采集定义, 本机缓存不是实时可用性证明。",
              "- 语料描述和问题均经离线整理, 标签不是外部独立金标准。需要结合误召回逐题核对, 不应据此声称生产准确率。",
              "- 同名/同功能工具可能多标; local/public 分组按该题相关工具来源划分, 跨来源题标记 mixed。",
              "- Ragas ID precision 分母为实际返回数量。空召回原始 Precision 为 NaN, 汇总按0计入并单独计数。",
              "- 重排失败按回退排名保留, 单独计数; 含失败配置不参与参数选择。",
              "- 单一融合池的覆盖率限制重排上限。分阶段调参不保证全组合全局最优。",
              "- 跨配置复用查询向量及逐对重排分数, elapsed_s 包含缓存影响, 不用于延迟性能对比。",
              "- 数据和模型指纹一致时可以恢复实验; rankings.jsonl 可在不访问数据库/模型的情况下重新计分。",
              "", "## 选定配置失败样例", ""]
    records = read_runtime_jsonl(output / "rankings.jsonl")
    latest = latest_rankings(records)
    selected = [r for r in latest if r["split"] == "test" and r["phase"] == "selected"
                and r["method"] == "rerank" and r["recall"] == selection["recall"] and r["pool"] == selection["pool"]]
    failures = [r for r in selected if r.get("error")]
    lines.append(f"当前选定配置重排失败: {len(failures)} / {len(selected)} 题。")
    for row in failures[:12]:
        lines += [f"- {row['question_id']}: {row['query']}", f"  错误: {row['error']}",
                  f"  标注: {', '.join(row['references'])}; 回退前5: {', '.join(row['ranked_ids'][:5])}",
                  f"  候选数: {len(row['candidate_ids'])}; 池大小: {len(row['pool_ids'])}; reranked: {row.get('reranked')}"]
    historical_failures = sum(bool(r.get("error")) for r in records)
    lines.append(f"原始追加日志保留 {historical_failures} 条历史失败记录 (跨所有阶段/配置, 包含已重试记录); 汇总使用最新唯一结果。")
    lines += ["", "## 误召回样例", ""]
    zero_hit = [r for r in selected if not set(r["references"]) & set(r["ranked_ids"][:5])]
    partial_coverage = [r for r in selected if set(r["references"]) & set(r["ranked_ids"][:5])
                        and not set(r["references"]) <= set(r["ranked_ids"][:5])]
    lines += [f"- Top5 至少命中一个标注工具: {len(selected) - len(zero_hit)} / {len(selected)} 题。",
              f"- Top5 零命中 (zero_hit): {len(zero_hit)} / {len(selected)} 题。",
              f"- Top5 部分覆盖 (partial_coverage): {len(partial_coverage)} / {len(selected)} 题。",
              f"- Top5 完整覆盖全部标注工具: {len(selected) - len(zero_hit) - len(partial_coverage)} / {len(selected)} 题。",
              "至少命中一个标注工具不等于完整覆盖; 部分覆盖仍有标注工具漏召回, 需要核对标签及跨来源等价工具。"]
    for title, examples in (("零命中样例", zero_hit), ("部分覆盖样例", partial_coverage)):
        lines += ["", f"### {title}", ""]
        for row in examples[:12]:
            top5 = row["ranked_ids"][:5]
            missing = [tool_id for tool_id in row["references"] if tool_id not in top5]
            lines += [f"- {row['question_id']}: {row['query']}", f"  标注 ID: {', '.join(row['references'])}",
                      f"  缺失 ID: {', '.join(missing)}; Top5 排名 ID: {', '.join(top5)}"]
        if not examples:
            lines.append("无此类样例。")
    path = output / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
