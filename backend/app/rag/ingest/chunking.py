import bisect
import re
from collections.abc import Callable
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.core.types import Chunk, ChunkedDoc

# Slack for splitter rounding (it can accept a piece a few tokens above chunk_size). The reranker's 512
# limit also has to hold the query, so this bound is soft by nature; it is not worth chasing token-exactness.
_SPLIT_SLACK = 8
SEPARATORS = [r"\n#{1,6} ", r"\n\n", r"\n", r"(?<=[。！？!?;；])", r"(?<=[，、：,:])", r" ", ""]
_HEADING = re.compile(r"(#{1,6})[ \t]+(.*\S)")


@dataclass(frozen=True)
class ChunkConfig:
    target_tokens: int = 400
    max_tokens: int = 512
    overlap_tokens: int = 50
    min_chunk_chars: int = 60


def scan_headings(text: str) -> list[tuple[int, int, str]]:
    out, pos, in_fence = [], 0, False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            m = _HEADING.match(line)
            if m:
                out.append((pos, len(m.group(1)), m.group(2)))
        pos += len(line)
    return out


def scan_fences(text: str) -> list[tuple[int, int]]:
    out, pos, start = [], 0, None
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            if start is None:
                start = pos
            else:
                out.append((start, pos + len(line.rstrip("\n"))))
                start = None
        pos += len(line)
    return out


def _heading_path(headings, starts, pos: int) -> str:
    i = bisect.bisect_right(starts, pos) - 1
    stack: list[tuple[int, str]] = []
    for _, level, title in headings[: i + 1]:
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
    return " > ".join(t for _, t in stack)


def _sections(text: str, headings) -> list[tuple[int, int]]:
    bounds = sorted({0, len(text), *(p for p, lvl, _ in headings if lvl <= 3)})
    raw = list(zip(bounds, bounds[1:]))
    out: list[tuple[int, int]] = []
    carry = None
    for a, b in raw:
        if carry is not None:
            a, carry = carry, None
        body = re.sub(r"(?m)^#{1,6}[ \t]+.*$", "", text[a:b]).strip()
        if not body and b != len(text):
            carry = a
            continue
        out.append((a, b))
    return out


_HEADING_LINE = re.compile(r"(?m)^#{1,6}[ \t]+.*$\n?")


def _body_start(text: str, start: int, end: int) -> int:
    """Offset of the first non-heading, non-blank char in [start, end); `start` if none."""
    pos = start
    while pos < end:
        line_end = text.find("\n", pos, end)
        line_end = end if line_end == -1 else line_end + 1
        line = text[pos:line_end]
        if line.strip() and not _HEADING.match(line):
            return pos
        pos = line_end
    return start


def _repair(text: str, start: int, end: int, fences) -> str:
    """Make a chunk a valid markdown snippet: reopen a fence it starts inside, close one it leaves open."""
    seg = text[start:end]
    for fa, fb in fences:
        if fa < start < fb:  # chunk starts inside a fenced block
            nl = text.find("\n", fa)
            info = text[fa:len(text) if nl == -1 else nl].lstrip().removeprefix("```").strip()
            seg = f"```{info}\n{seg}"
            break
    if seg.count("```") % 2:
        seg += "\n```"
    return seg


def _split_spans(sec: str, splitter, overlap_tokens: int, count_tokens) -> list[tuple[int, int]]:
    """Split one section into (start, end) spans that are verbatim slices of `sec`.

    The splitter runs with chunk_overlap=0, so its pieces are consecutive and each one is found
    exactly at or after the end of the previous piece. LangChain's own overlap is counted in tokens
    while offsets are chars, and `add_start_index` returns -1 in that case; searching from an
    estimated offset also mis-locates pieces when content repeats (table rows, log lines).
    """
    spans: list[list[int]] = []
    cursor = 0
    for piece in splitter.split_text(sec):
        i = sec.find(piece, cursor)
        assert i != -1, "splitter piece is not a verbatim slice of the section"
        spans.append([i, i + len(piece)])
        cursor = i + len(piece)
    if overlap_tokens > 0:
        for k in range(1, len(spans)):
            spans[k][0] = _overlap_start(sec, spans[k - 1][0], spans[k][0], overlap_tokens, count_tokens)
    return [(a, b) for a, b in spans]


def _overlap_start(sec: str, prev_start: int, start: int, overlap_tokens: int, count_tokens) -> int:
    """Move `start` back over whole lines of the previous span while they fit the overlap budget."""
    j = start
    while True:
        nl = sec.rfind("\n", prev_start, j - 1)
        cand = nl + 1 if nl != -1 else -1
        if cand <= prev_start or count_tokens(sec[cand:start]) > overlap_tokens:
            return j
        j = cand


def chunk_markdown(
    text: str,
    title: str,
    tags: str,
    cfg: ChunkConfig,
    count_tokens: Callable[[str], int],
) -> ChunkedDoc:
    headings = scan_headings(text)
    starts = [h[0] for h in headings]
    fences = scan_fences(text)
    # Room for the fences `_repair` may add to a chunk that was cut inside a code block.
    repair_reserve = count_tokens("```markdown\n\n```")
    splitters: dict[int, RecursiveCharacterTextSplitter] = {}

    def splitter_for(size: int) -> RecursiveCharacterTextSplitter:
        if size not in splitters:
            splitters[size] = RecursiveCharacterTextSplitter(
                separators=SEPARATORS,
                is_separator_regex=True,
                keep_separator="start",
                chunk_size=size,
                chunk_overlap=0,  # overlap is added by `_overlap_start` on line boundaries
                length_function=count_tokens,
            )
        return splitters[size]

    def index_text(path: str, content: str) -> str:
        head = " > ".join(p for p in (title, path) if p)
        return "\n".join(p for p in (head, tags, content) if p)

    def prefix_tokens(path: str) -> int:
        return count_tokens(index_text(path, "") + "\n")

    spans: list[tuple[int, int]] = []
    for a, b in _sections(text, headings):
        sec = text[a:b]
        path = _heading_path(headings, starts, _body_start(text, a, b))
        if count_tokens(index_text(path, sec)) <= cfg.max_tokens:
            spans.append((a, b))
            continue
        # The splitter bounds only the content, so shrink it by the prefix that index_text will add,
        # the fences `_repair` may add, and the overlap `_split_spans` prepends from the previous span.
        # Headings deeper than H3 stay inside the section, so use the longest heading path found in it.
        prefix = max(
            prefix_tokens(_heading_path(headings, starts, p))
            for p in [_body_start(text, a, b), *(h[0] for h in headings if a < h[0] < b)]
        )
        size = max(1, min(cfg.target_tokens, cfg.max_tokens - prefix - repair_reserve - cfg.overlap_tokens - _SPLIT_SLACK))
        spans.extend((a + x, a + y) for x, y in _split_spans(sec, splitter_for(size), cfg.overlap_tokens, count_tokens))

    def fits(s: int, e: int) -> bool:
        path = _heading_path(headings, starts, _body_start(text, s, e))
        # A merged span is only repaired when it is cut inside a fence; account for that.
        reserve = repair_reserve if text[s:e].count("```") % 2 or any(fa < s < fb for fa, fb in fences) else 0
        return count_tokens(index_text(path, text[s:e])) + reserve <= cfg.max_tokens

    merged: list[list[int]] = []
    for s, e in spans:
        small = e - s < cfg.min_chunk_chars or (merged and merged[-1][1] - merged[-1][0] < cfg.min_chunk_chars)
        # A small chunk is better than a truncated one: only merge when the result still fits.
        if merged and small and fits(merged[-1][0], max(merged[-1][1], e)):
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    chunks = []
    for i, (s, e) in enumerate(merged):
        path = _heading_path(headings, starts, _body_start(text, s, e))
        content = _repair(text, s, e, fences)
        chunks.append(Chunk(i, path, content, index_text(path, content), s, e))
    return ChunkedDoc(title=title, chunks=chunks)
