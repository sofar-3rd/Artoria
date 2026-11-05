import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.rag.core.errors import EmptyDocument
from app.rag.ingest.loaders import load, load_with_meta


def make_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def test_markdown_title_from_front_matter():
    doc, tags = load_with_meta("a.md", b"---\ntitle: My Doc\ntags: [x, y]\n---\n# Other\n\nbody")
    assert doc.title == "My Doc" and tags == "x y"
    assert doc.markdown.startswith("# Other")


def test_markdown_title_from_first_h1():
    assert load("a.md", "# Hello\n\nbody".encode()).title == "Hello"


def test_markdown_title_ignores_h1_inside_fence():
    raw = "```bash\n# not a title\n```\n\n# Real\n".encode()
    assert load("a.md", raw).title == "Real"


def test_markdown_title_falls_back_to_stem():
    assert load("guides/deploy.md", b"just text").title == "deploy"


def test_empty_markdown_raises():
    with pytest.raises(EmptyDocument):
        load("a.md", b"   \n")


def test_pdf_extracts_text_and_uses_stem_as_title():
    doc = load("docs/guide.pdf", make_pdf(["Deployment Guide", "Run kubectl rollout undo."]))
    assert "Deployment Guide" in doc.markdown and "kubectl" in doc.markdown
    assert doc.title == "guide"


def test_pdf_without_text_raises():
    with pytest.raises(EmptyDocument):
        load("scan.pdf", make_pdf([]))


def test_unsupported_extension():
    with pytest.raises(ValueError):
        load("a.docx", b"x")
