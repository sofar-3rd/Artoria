import pytest

from app.rag.ingest.chunking import ChunkConfig, chunk_markdown, scan_fences, scan_headings

CFG = ChunkConfig(target_tokens=60, max_tokens=80, overlap_tokens=0, min_chunk_chars=20)
count = len  # tests use characters as tokens


def chunks(text, title="T", tags="", cfg=CFG):
    return chunk_markdown(text, title, tags, cfg, count).chunks


def test_scan_headings_ignores_fenced_hash():
    text = "# A\n\n```bash\n# comment\n```\n\n## B\n"
    assert [(lvl, t) for _, lvl, t in scan_headings(text)] == [(1, "A"), (2, "B")]


def test_scan_fences_pairs():
    text = "x\n```py\ncode\n```\ny\n"
    assert scan_fences(text) == [(2, 16)]


def test_short_sections_become_one_chunk_each_with_heading_path():
    text = "# Guide\n\nintro text here for the guide\n\n## Rollback\n\nrun the undo command now\n"
    cs = chunks(text)
    assert [c.heading_path for c in cs] == ["Guide", "Guide > Rollback"]
    assert cs[1].content.startswith("## Rollback")


def test_offsets_roundtrip_to_original_text():
    text = "# A\n\n" + "第一段内容,说明细节。" * 30 + "\n\n## B\n\n" + "second paragraph. " * 20
    for c in chunks(text):
        assert text[c.start:c.end] == c.content


def test_index_text_prefix_and_tags():
    text = "# Guide\n\nsome body text that is long enough\n"
    c = chunks(text, title="Doc", tags="ops k8s")[0]
    assert c.index_text.startswith("Doc > Guide\nops k8s\n")
    assert c.index_text.endswith(c.content)


def test_index_text_without_heading_or_tags():
    c = chunks("plain text without any heading at all, long enough")[0]
    assert c.index_text.startswith("T\n")


def test_long_section_is_split_within_limit():
    text = "# A\n\n" + "".join(f"句子{i}说明了一件事情。" for i in range(40))
    cs = chunks(text)
    assert len(cs) > 1
    assert all(count(c.index_text) <= CFG.max_tokens + 5 for c in cs)
    assert all(c.heading_path == "A" for c in cs)


def test_chinese_splits_on_sentence_punctuation():
    text = "# A\n\n" + "第一步检查配置是否正确。" * 20
    cs = chunks(text)
    assert all(c.content.rstrip().endswith("。") for c in cs[:-1])


def test_short_code_block_stays_whole():
    text = "# A\n\nrun:\n\n```bash\nkubectl rollout undo deploy/app\nkubectl get pods\n```\n\nafter"
    cs = chunks(text)
    assert len(cs) == 1 and cs[0].content.count("```") == 2


def test_long_code_block_split_by_lines_with_fences_repaired():
    code = "\n".join(f"kubectl apply -f manifest_{i}.yaml" for i in range(12))
    text = f"# A\n\n```bash\n{code}\n```\n"
    cs = chunks(text)
    assert len(cs) > 1
    for c in cs:
        assert c.content.count("```") % 2 == 0
    assert cs[1].content.startswith("```bash\n")


def test_tiny_fragments_are_merged():
    text = "# A\n\n" + "正文内容足够长的一段话用于测试。" * 4 + "\n\n## B\n\nx\n"
    cs = chunks(text)
    assert all(len(c.content) >= CFG.min_chunk_chars or len(cs) == 1 for c in cs)


def test_chunk_indexes_are_sequential():
    text = "# A\n\n" + "句子很长很长很长。" * 40
    assert [c.idx for c in chunks(text)] == list(range(len(chunks(text))))


def test_heading_only_section_merges_into_next():
    text = "# A\n\n## B\n\nbody of section b is long enough here\n"
    cs = chunks(text)
    assert len(cs) == 1 and cs[0].heading_path == "A > B"
