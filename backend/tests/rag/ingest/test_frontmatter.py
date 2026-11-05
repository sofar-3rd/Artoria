from app.rag.ingest.frontmatter import extract_tags, split_front_matter


def test_split_front_matter():
    meta, body = split_front_matter("---\ntitle: X\ntags: [a, b]\n---\n# H\n\ntext\n")
    assert meta == {"title": "X", "tags": ["a", "b"]}
    assert body == "# H\n\ntext\n"


def test_no_front_matter_is_untouched():
    text = "# H\n\ntext\n"
    assert split_front_matter(text) == ({}, text)


def test_invalid_yaml_is_untouched():
    text = "---\n: : bad\n---\nbody"
    meta, body = split_front_matter(text)
    assert meta == {} and body == text


def test_extract_tags_merges_tags_and_aliases():
    assert extract_tags({"tags": ["a", "b"], "aliases": "c"}) == "a b c"
    assert extract_tags({}) == ""
