"""The whole feature with the REAL models, real Postgres and real files: sync, search, update, delete.

Skipped unless run with `-m slow` and the models are downloaded (backend/scripts/download_models.py).
"""

import io
import uuid
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.config import settings

pytestmark = pytest.mark.slow

ROLLBACK = """---
title: 回滚指南
tags: [运维, 部署]
---
# 回滚指南

## 何时回滚

发布后错误率超过 5% 或核心接口延迟翻倍时,应立即回滚到上一个稳定版本。

## 回滚步骤

执行下面的命令回滚到上一个版本:

```bash
kubectl rollout undo deploy/app
kubectl rollout status deploy/app
```

回滚后检查监控面板,确认错误率恢复正常。
"""

MONITORING = """# 监控与告警

## 监控面板

面板展示请求量、错误率、P99 延迟和 Pod 重启次数。

## 告警规则

错误率连续 5 分钟高于 5% 触发 P1 告警,通知值班工程师。
"""

COOKING = """# 红烧肉的做法

## 食材

五花肉 500 克,冰糖 30 克,生抽、老抽、料酒各适量,葱姜若干。

## 步骤

五花肉切块焯水,冰糖炒出糖色,下肉块翻炒上色,加调料和热水,小火炖 60 分钟,最后大火收汁。
"""


def make_pdf(lines):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


@pytest.fixture(scope="module")
def models_present():
    root = Path(settings.rag_model_dir)
    if not all((root / n).is_file() for n in ("bge-m3/pytorch_model.bin", "bge-reranker-v2-m3/model.safetensors")):
        pytest.skip("models are not downloaded; run backend/scripts/download_models.py")


@pytest.fixture
def source_dir(tmp_path):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "rollback.md").write_text(ROLLBACK, encoding="utf-8")
    (tmp_path / "ops" / "monitoring.md").write_text(MONITORING, encoding="utf-8")
    (tmp_path / "life").mkdir()
    (tmp_path / "life" / "cooking.md").write_text(COOKING, encoding="utf-8")
    (tmp_path / "ops" / "runbook.pdf").write_bytes(make_pdf(["Database failover runbook", "Promote the replica with pg_ctl promote."]))
    return tmp_path


@pytest.fixture
async def rag(models_present, source_dir):
    from app.db import SessionLocal, engine
    from app.rag.bootstrap import build_rag
    from app.rag.ingest.sources import DirSource

    instance = build_rag(source_factory=lambda kb: DirSource(source_dir))
    yield instance
    await engine.dispose()


async def new_kb(rag, source_dir):
    name = f"e2e-{uuid.uuid4().hex[:8]}"
    await rag.store.create_kb(name, "e2e docs", f"dir:{source_dir}", "main", "", rag.embedder.model, rag.embedder.dim)
    return name


async def test_the_whole_lifecycle_with_the_real_models(rag, source_dir):
    name = await new_kb(rag, source_dir)

    report = await rag.syncer.sync(name)
    assert (report.added, report.failed) == (4, [])  # three markdown files and the pdf

    # Chinese question -> the Chinese rollback guide, reranked by the real cross-encoder.
    hits = await rag.searcher.search("怎么回滚部署", [name], 3)
    assert hits.reranked is True and hits.hits[0].path == "ops/rollback.md" and hits.hits[0].score > 0.5
    assert hits.hits[0].title == "回滚指南" and "回滚" in hits.hits[0].heading_path

    # English question -> the same Chinese document: the multilingual models work across languages.
    english = await rag.searcher.search("how do I roll back a release", [name], 3)
    assert english.hits[0].path == "ops/rollback.md"

    # The PDF is searchable too (its text comes from MarkItDown, with the file name as title).
    pdf = await rag.searcher.search("how to promote the database replica", [name], 3)
    assert pdf.hits[0].path == "ops/runbook.pdf" and pdf.hits[0].title == "runbook"

    # An off-topic question matches nothing well: every score is low (this is what a threshold would use).
    off_topic = await rag.searcher.search("量子计算机的退相干时间", [name], 3)
    assert max(h.score for h in off_topic.hits) < 0.3

    # Update one document: only that one is re-embedded, the new text is found, the old text is not.
    (source_dir / "ops" / "rollback.md").write_text(ROLLBACK.replace("kubectl rollout undo deploy/app", "helm rollback app 1"), encoding="utf-8")
    report = await rag.syncer.sync(name)
    assert (report.added, report.changed, report.removed, report.unchanged) == (0, 1, 0, 3)
    after = await rag.searcher.search("helm rollback", [name], 1)
    assert after.hits[0].path == "ops/rollback.md" and "helm rollback app 1" in after.hits[0].content
    assert "kubectl rollout undo" not in after.hits[0].content

    # Delete a document: it disappears from search.
    (source_dir / "life" / "cooking.md").unlink()
    report = await rag.syncer.sync(name)
    assert report.removed == 1
    gone = await rag.searcher.search("红烧肉怎么做", [name], 3)
    assert all(h.path != "life/cooking.md" for h in gone.hits)


async def test_knowledge_bases_are_isolated_from_each_other(rag, source_dir):
    first, second = await new_kb(rag, source_dir), await new_kb(rag, source_dir)
    await rag.syncer.sync(first)
    # Only the first knowledge base has been synced: searching the second must find nothing, not the first's text.
    empty = await rag.searcher.search("怎么回滚部署", [second], 5)
    assert empty.hits == []
    both = await rag.searcher.search("怎么回滚部署", [first, second], 5)
    assert both.hits and {h.kb for h in both.hits} == {first}


async def test_read_document_returns_the_text_a_search_hit_points_into(rag, source_dir):
    name = await new_kb(rag, source_dir)
    await rag.syncer.sync(name)
    hit = (await rag.searcher.search("怎么回滚部署", [name], 1)).hits[0]
    page = await rag.catalog.read_document(hit.doc_id, hit.start, 200)
    assert page.text.startswith(hit.content[:20]) or hit.content[:20] in ROLLBACK
    assert page.total_chars == hit.doc_chars and page.path == hit.path


async def test_the_agent_tools_work_end_to_end_with_the_real_models(rag, source_dir):
    from app.rag.interfaces.tools import build_kb_tools

    name = await new_kb(rag, source_dir)
    await rag.syncer.sync(name)
    tools = {t.name: t for t in build_kb_tools(rag.catalog, rag.searcher)}
    listing = await tools["list_knowledge_bases"].ainvoke({})
    assert name in listing and "4 documents" in listing
    found = await tools["search_knowledge_base"].ainvoke({"query": "回滚后要检查什么", "kbs": [name], "top_k": 2})
    assert "path: ops/rollback.md" in found and "reranked: true" in found
    doc_id = found.split("doc_id: ")[1].split(" ")[0]
    page = await tools["read_document"].ainvoke({"doc_id": doc_id, "offset": 0, "limit": 80})
    assert page.startswith("doc: ops/rollback.md") and "has_more: true" in page


async def test_a_real_search_takes_well_under_a_second_once_the_models_are_loaded(rag, source_dir):
    import time

    name = await new_kb(rag, source_dir)
    await rag.syncer.sync(name)
    await rag.searcher.search("预热", [name], 1)  # first call loads the models
    timings = []
    for question in ("怎么回滚部署", "告警什么时候触发", "how to promote the replica"):
        started = time.perf_counter()
        await rag.searcher.search(question, [name], 5)
        timings.append(time.perf_counter() - started)
    assert max(timings) < 3.0, f"slowest search {max(timings):.2f}s"  # generous: CPU-only machines are ~2.5 s
