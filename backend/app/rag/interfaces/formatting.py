from app.rag.core.types import DocPage, KbInfo, SearchResult


def format_hits(result: SearchResult, kbs: list[str]) -> str:
    if not result.hits:
        return (
            f"No relevant content found in: {', '.join(kbs)}. "
            "Try different keywords or another knowledge base."
        )
    blocks = []
    for n, h in enumerate(result.hits, start=1):
        meta = f"title: {h.title}"
        if h.heading_path:
            meta += f" | section: {h.heading_path}"
        blocks.append(
            f"[{n}] kb: {h.kb} | doc_id: {h.doc_id} | path: {h.path}\n"
            f"    {meta}\n"
            f"    chars: {h.start}-{h.end} of {h.doc_chars} | reranked: {str(result.reranked).lower()}\n"
            f"{h.content}"
        )
    return "\n\n".join(blocks)


def format_page(page: DocPage) -> str:
    end = page.offset + len(page.text)
    out = (
        f"doc: {page.path} | title: {page.title} | chars {page.offset}-{end} "
        f"of {page.total_chars} | has_more: {str(page.has_more).lower()}\n\n{page.text}"
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
        line = f"- {kb.name}: {kb.description} ({kb.doc_count} documents, {synced})"
        if kb.last_error:
            line += f" [last sync failed: {kb.last_error[:120]}]"
        lines.append(line)
    return "\n".join(lines)


def format_error(err: Exception) -> str:
    return f"error: {err}"
