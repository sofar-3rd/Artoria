import re

import yaml

_FM = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def split_front_matter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, text[m.end():]


def extract_tags(meta: dict) -> str:
    words: list[str] = []
    for key in ("tags", "aliases"):
        value = meta.get(key)
        if isinstance(value, str):
            words.append(value)
        elif isinstance(value, list):
            words.extend(str(v) for v in value)
    return " ".join(words)
