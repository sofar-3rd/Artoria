import re

from app.rag.core.types import DocPage, KbInfo, SearchResult

# Retrieved text is untrusted. Two things could make the model believe there is a result that does not
# exist (and cite a forged path): a line of document text that looks like one of our own markers, and a
# single-line field (title, path, ...) that contains a line break. Both are neutralised where the text
# enters the model-facing output. This raises the bar; it is not a trust boundary.
_LINE_BREAKS = re.compile(r"\r\n|[\r\x0b\x0c\x85\u2028\u2029]")
_INVISIBLE = "\ufeff\u200b\u200c\u200d\u2060"
_FORGEABLE = re.compile(
    r"(?mi)^([ \t" + _INVISIBLE + r"]*)"
    r"([\[\uff3b]\s*[\d\uff10-\uff19]+\s*[\]\uff3d]\s*kb\s*:|doc:[^\n]*\|\s*has_more\s*:|\[truncated: call read_document)"
)
_WHITESPACE = re.compile(r"\s+")


def _quote(text: str) -> str:
    text = _LINE_BREAKS.sub("\n", text)
    return _FORGEABLE.sub(lambda m: f"{m.group(1)}\\{m.group(2)}", text)


def _one_line(value: object) -> str:
    """A field that must stay on one line: any whitespace run, line breaks included, becomes one space."""
    return _WHITESPACE.sub(" ", str(value)).strip()


def format_hits(result: SearchResult, kbs: list[str]) -> str:
    if not result.hits:
        return (
            f"No relevant content found in: {', '.join(kbs)}. "
            "Try different keywords or another knowledge base."
        )
    blocks = []
    for n, h in enumerate(result.hits, start=1):
        meta = f"title: {_one_line(h.title)}"
        if h.heading_path:
            meta += f" | section: {_one_line(h.heading_path)}"
        blocks.append(
            f"[{n}] kb: {_one_line(h.kb)} | doc_id: {_one_line(h.doc_id)} | path: {_one_line(h.path)}\n"
            f"    {meta}\n"
            f"    chars: {h.start}-{h.end} of {h.doc_chars} | reranked: {str(result.reranked).lower()}\n"
            f"{_quote(h.content)}"
        )
    return "\n\n".join(blocks)


def format_page(page: DocPage) -> str:
    if not page.text and page.total_chars > 0 and page.offset >= page.total_chars:
        return (
            f"error: offset {page.offset} is past the end of '{_one_line(page.path)}' "
            f"(the document has {page.total_chars} characters). Use an offset below {page.total_chars}."
        )
    end = page.offset + len(page.text)
    out = (
        f"doc: {_one_line(page.path)} | title: {_one_line(page.title)} | chars {page.offset}-{end} "
        f"of {page.total_chars} | has_more: {str(page.has_more).lower()}\n\n{_quote(page.text)}"
    )
    if page.has_more:
        out += f"\n\n[truncated: call read_document again with offset={end} to continue]"
    return out


def format_kbs(kbs: list[KbInfo]) -> str:
    if not kbs:
        return "No knowledge bases are available."
    lines = []
    for kb in kbs:
        synced = kb.synced_at.strftime("%Y-%m-%d %H:%M UTC") if kb.synced_at else "never synced"
        line = f"- {_one_line(kb.name)}: {_one_line(kb.description)} ({kb.doc_count} documents, {synced})"
        if kb.last_error:
            line += f" [last sync failed: {_one_line(kb.last_error)[:120]}]"
        lines.append(line)
    return "\n".join(lines)


def format_error(err: Exception) -> str:
    return f"error: {err}"
