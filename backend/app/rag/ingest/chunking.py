import bisect
import re
from collections.abc import Callable
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.core.types import Chunk, ChunkedDoc

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
            info = text[fa:text.index("\n", fa)].lstrip().removeprefix("```").strip()
            seg = f"```{info}\n{seg}"
            break
    if seg.count("```") % 2:
        seg += "\n```"
    return seg


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
    splitter = RecursiveCharacterTextSplitter(
        separators=SEPARATORS,
        is_separator_regex=True,
        keep_separator="start",
        chunk_size=cfg.target_tokens,
        chunk_overlap=cfg.overlap_tokens,
        length_function=count_tokens,
    )

    def index_text(path: str, content: str) -> str:
        head = " > ".join(p for p in (title, path) if p)
        return "\n".join(p for p in (head, tags, content) if p)

    spans: list[tuple[int, int]] = []
    for a, b in _sections(text, headings):
        sec = text[a:b]
        path = _heading_path(headings, starts, _body_start(text, a, b))
        if count_tokens(index_text(path, sec)) <= cfg.max_tokens:
            spans.append((a, b))
            continue
        # Do not trust `add_start_index`: LangChain searches from `prev_start + prev_len - chunk_overlap`,
        # and `chunk_overlap` is in tokens while offsets are in chars, so find() can return -1.
        floor = 0
        for piece in splitter.split_text(sec):
            i = sec.find(piece, floor)
            if i == -1:
                i = sec.find(piece)
            assert i != -1, "splitter piece is not a verbatim slice of the section"
            spans.append((a + i, a + i + len(piece)))
            floor = i + 1

    merged: list[list[int]] = []
    for s, e in spans:
        if merged and (e - s < cfg.min_chunk_chars or merged[-1][1] - merged[-1][0] < cfg.min_chunk_chars):
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    chunks = []
    for i, (s, e) in enumerate(merged):
        path = _heading_path(headings, starts, _body_start(text, s, e))
        content = _repair(text, s, e, fences)
        chunks.append(Chunk(i, path, content, index_text(path, content), s, e))
    return ChunkedDoc(title=title, chunks=chunks)
