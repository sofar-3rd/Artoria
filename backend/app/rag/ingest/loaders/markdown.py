import re
from pathlib import PurePosixPath

from app.rag.core.errors import EmptyDocument
from app.rag.core.types import LoadedDoc
from app.rag.ingest.frontmatter import extract_tags, split_front_matter

_H1 = re.compile(r"^#\s+(.*\S)\s*$")


def first_h1(body: str) -> str | None:
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            m = _H1.match(line)
            if m:
                return m.group(1)
    return None


def load_markdown(path: str, raw: bytes) -> tuple[LoadedDoc, str]:
    text = raw.decode("utf-8", errors="replace")
    meta, body = split_front_matter(text)
    if not body.strip():
        raise EmptyDocument(path)
    title = str(meta.get("title") or "") or first_h1(body) or PurePosixPath(path).stem
    return LoadedDoc(title=title, markdown=body), extract_tags(meta)
