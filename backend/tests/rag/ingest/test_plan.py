from app.rag.ingest.plan import plan


def test_plan_classifies():
    p = plan(
        remote={"a.md": "1", "b.md": "2x", "c.md": "3"},
        local={"b.md": "2", "c.md": "3", "d.md": "4"},
    )
    assert (p.added, p.changed, p.removed, p.unchanged) == (["a.md"], ["b.md"], ["d.md"], ["c.md"])


def test_plan_empty():
    p = plan({}, {})
    assert p.added == p.changed == p.removed == p.unchanged == []
