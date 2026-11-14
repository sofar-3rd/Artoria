"""Validate the frozen offline data and audit files without network or MCP calls."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parent


def load(filename):
    return [json.loads(line) for line in (ROOT / filename).read_text().splitlines() if line]


def check():
    tools, sources, questions = (load(f'{name}.jsonl') for name in ('tools', 'sources', 'questions'))
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    assert len(tools) == len(sources) == 200
    assert len(questions) == 400
    ids = {t['tool_id'] for t in tools}
    assert len(ids) == 200
    assert {s['tool_id'] for s in sources} == ids
    assert Counter(t['origin'] for t in tools) == {'local': 100, 'public': 100}
    assert Counter(t['tool_id'].split('/')[0] for t in tools) == {
        'iWiki': 37, 'tapd_mcp_http': 4, 'tce-env-mcp': 12, 'codegraph': 8,
        'context7': 2, 'chrome-devtools': 29, 'wecom-doc': 8, 'github': 75, 'playwright': 25}
    for tool, source in zip(tools, sources):
        assert set(tool) == {'tool_id', 'name', 'origin', 'function', 'when_to_use'}
        assert tool['tool_id'] == source['tool_id']
        assert tool['name'] == source['name'] == tool['tool_id'].split('/', 1)[1]
        assert tool['origin'] == source['origin']
        assert re.search(r'[\u4e00-\u9fff]', tool['function'])
        assert re.search(r'[\u4e00-\u9fff]', tool['when_to_use'])
        assert 'inputSchema' not in tool['function'] + tool['when_to_use']
        assert not any(label in tool['function'] + tool['when_to_use'] for label in
                       ('iWiki/', 'tapd_mcp_http', 'tce-env-mcp', 'chrome-devtools', 'wecom-doc', 'codegraph_', 'browser_'))
        assert set(source) == ({'tool_id', 'origin', 'name', 'description', 'inputSchema', 'source_sha256',
                                'source_path', 'cached_at', 'license'} if source['origin'] == 'local' else
                               {'tool_id', 'origin', 'name', 'description', 'inputSchema', 'source_sha256',
                                'source_url', 'revision', 'license'})
        assert source['inputSchema']['type'] == 'object'
        assert set(source['inputSchema'].get('required', [])).issubset(source['inputSchema'].get('properties', {}))
        if source['origin'] == 'local':
            definition = {k: source[k] for k in ('name', 'description', 'inputSchema')}
            data = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        else:
            server = source['tool_id'].split('/')[0]
            data = (ROOT / 'sources' / server / 'README.md').read_bytes()
            assert source['revision'] in source['source_url']
        assert hashlib.sha256(data).hexdigest() == source['source_sha256']
    assert len({q['id'] for q in questions}) == 400
    assert len({q['query'] for q in questions}) == 400, 'Duplicate demand text'
    by_intent = defaultdict(list)
    coverage = Counter()
    origin_by_id = {t['tool_id']: t['origin'] for t in tools}
    for question in questions:
        assert set(question) == {'id', 'intent_id', 'query', 'relevant_tool_ids', 'split', 'category'}
        assert question['split'] in {'dev', 'test'}
        assert question['category'] in {'direct', 'paraphrase', 'boundary'}
        assert question['relevant_tool_ids'] and set(question['relevant_tool_ids']).issubset(ids)
        assert len(set(question['relevant_tool_ids'])) == len(question['relevant_tool_ids'])
        assert question['query'] not in {t['function'] for t in tools}
        assert re.search(r'[\u4e00-\u9fff]', question['query'])
        by_intent[question['intent_id']].append(question)
        coverage.update(question['relevant_tool_ids'])
    assert set(coverage) == ids
    assert min(coverage.values()) >= 2
    for group in by_intent.values():
        assert len({q['split'] for q in group}) == 1, 'Intent leaked across splits'
    for question in questions:
        if question['category'] == 'paraphrase':
            assert len(by_intent[question['intent_id']]) >= 2, ('Unpaired paraphrase', question['id'])
    intent_ids = sorted(by_intent)
    random.Random(42).shuffle(intent_ids)
    test_intents = set(intent_ids[:round(len(intent_ids) * 0.2)])
    assert all((q['intent_id'] in test_intents) == (q['split'] == 'test') for q in questions)
    for split in ('dev', 'test'):
        assert {origin_by_id[t] for q in questions if q['split'] == split for t in q['relevant_tool_ids']} == {'local', 'public'}
    for relative, expected in manifest['hashes_sha256'].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    for acquisition in json.loads((ROOT / 'sources' / 'acquisition.json').read_text()):
        server = acquisition['server']
        assert acquisition['revision'] == manifest['public_selections'][server]['revision']
        snapshot = ROOT / 'sources' / server / 'README.md'
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == acquisition['stored_sanitized_readme_sha256']
        excerpt = ROOT / acquisition['raw_tool_excerpt']
        assert hashlib.sha256(excerpt.read_bytes()).hexdigest() == acquisition['raw_tool_excerpt_sha256']
        assert excerpt.read_text() in snapshot.read_text(), 'Raw tool section changed during sanitation'
    aliases_text = (ROOT / 'sources' / 'github' / 'tool-renaming.md').read_text()
    aliases = set(re.findall(r'^\| `([^`]+)` \| `[^`]+` \|$', aliases_text, re.M))
    assert not aliases.intersection(t['name'] for t in tools if t['tool_id'].startswith('github/'))
    private_text = '\n'.join((ROOT / name).read_text() for name in
                             ('sources.jsonl', 'tools.jsonl', 'questions.jsonl', 'local.tsv', 'public.tsv', 'build_corpus.py'))
    assert not re.search(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', private_text), 'Unsanitized IP literal'
    assert not re.search(r'\b(?:gh[pousr]_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|AKID[A-Za-z0-9]{12,})\b', private_text)
    for path in (ROOT / 'sources').rglob('*'):
        if path.is_file():
            text = path.read_text()
            assert not re.search(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', text), ('Raw IP', path.name)
            assert not re.search(r'https?://[^/\s:@]+:[^/\s@]+@', text), ('URL credential sample', path.name)
            assert not re.search(r'Bearer\s+(?!\[REDACTED_SECRET\])[A-Za-z0-9_.${}-]+', text), ('Bearer sample', path.name)
    for payload in sources:
        serialized = json.dumps(payload, ensure_ascii=False)
        assert not re.search(r'--(?:new-password|password)\s+(?!\[REDACTED_SECRET\])[^\s]+', serialized)
    print(json.dumps({'status': 'passed', 'tools': 200, 'sources': 200, 'questions': 400,
                      'intents': len(by_intent), 'splits': dict(Counter(q['split'] for q in questions)),
                      'categories': dict(Counter(q['category'] for q in questions)),
                      'multi_label_questions': sum(len(q['relevant_tool_ids']) > 1 for q in questions),
                      'covered_tools_by_split': {s: len({t for q in questions if q['split'] == s for t in q['relevant_tool_ids']})
                                                 for s in ('dev', 'test')},
                      'audit_files_hashed': len(manifest['hashes_sha256'])}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    check()
