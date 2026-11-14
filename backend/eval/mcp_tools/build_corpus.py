"""Offline corpus serialization; never import or execute an MCP implementation."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import urllib.request

ROOT = Path(__file__).resolve().parent
CACHE = Path('/Users/glinn/.pi/agent/mcp-cache.json')
LOCAL_COUNTS = {'iWiki': 37, 'tapd_mcp_http': 4, 'tce-env-mcp': 12,
                'codegraph': 8, 'context7': 2, 'chrome-devtools': 29, 'wecom-doc': 8}
PUBLIC = {
    'github': ('github/github-mcp-server', '99d6d6503a7b2a133e2f8a595d6d0ba24b4086d3', 'MIT'),
    'playwright': ('microsoft/playwright-mcp', '404be8eb89abecff77a55152b6d843d140c78372', 'Apache-2.0'),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def sanitize(value):
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', '[REDACTED_IP]', value)
    value = re.sub(r'(?i)(--(?:new-password|password|passwd|token|secret|api[-_]key)\s+)(?:\x27[^\x27]*\x27|"[^"]*"|[^\s]+)',
                   r'\1[REDACTED_SECRET]', value)
    value = re.sub(r'(?i)((?:password|passwd|api[-_]key|access_token|secret)\s*=\s*)(?:\x27[^\x27]*\x27|"[^"]*")',
                   r'\1[REDACTED_SECRET]', value)
    value = re.sub(r'(?<![\w/])[A-Za-z][A-Za-z0-9]*[@!#$%][A-Za-z0-9!@#$%]*\d[A-Za-z0-9!@#$%]*(?![\w.])',
                   '[REDACTED_SECRET]', value)
    value = re.sub(r'(?i)((?:默认(?:新)?密码|重置密码为)\s*)[^\s，。;；)）]+', r'\1[REDACTED_SECRET]', value)
    value = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9_.${}-]+', r'\1[REDACTED_SECRET]', value)
    value = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|AKID[A-Za-z0-9]{12,})\b',
                   '[REDACTED_SECRET]', value)
    value = re.sub(r'(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[REDACTED_SECRET]@', value)
    return value


def acquire():
    for server, (repo, revision, _) in PUBLIC.items():
        folder = ROOT / 'sources' / server
        folder.mkdir(parents=True, exist_ok=True)
        for filename in ('README.md', 'LICENSE'):
            target = folder / filename
            if target.exists():
                continue
            url = f'https://raw.githubusercontent.com/{repo}/{revision}/{filename}'
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            target.write_bytes(data)
            print(f'Fetched {server}/{filename}: {len(data)} bytes, sha256={digest(data)}')


def audit_public():
    metadata_path = ROOT / 'sources' / 'acquisition.json'
    if metadata_path.exists():
        print('Public source snapshots already audited; no reacquisition.')
        return
    records = []
    for server, (repo, revision, license_name) in PUBLIC.items():
        path = ROOT / 'sources' / server / 'README.md'
        url = f'https://raw.githubusercontent.com/{repo}/{revision}/README.md'
        with urllib.request.urlopen(url, timeout=60) as response:
            original = response.read()
        text = original.decode()
        if server == 'github':
            start = text.index('<!-- START AUTOMATED TOOLS -->')
            end = text.index('<!-- END AUTOMATED TOOLS -->') + len('<!-- END AUTOMATED TOOLS -->')
        else:
            start = text.index('### Tools\n')
            end = text.index('<!--- End of tools generated section -->') + len('<!--- End of tools generated section -->')
        raw_tools = text[start:end]
        assert sanitize(raw_tools) == raw_tools, f'{server}: raw tool excerpt requires sanitation'
        excerpt = path.with_name('README.tools.raw.md')
        excerpt.write_bytes(raw_tools.encode())
        sanitized = sanitize(text).encode()
        path.write_bytes(sanitized)
        records.append({'server': server, 'repository': repo, 'revision': revision,
                        'source_url': f'https://raw.githubusercontent.com/{repo}/{revision}/README.md',
                        'upstream_full_readme_sha256': digest(original),
                        'stored_sanitized_readme_sha256': digest(sanitized),
                        'raw_tool_excerpt_sha256': digest(raw_tools.encode()),
                        'raw_tool_excerpt': str(excerpt.relative_to(ROOT)),
                        'excerpt_character_range': [start, end], 'encoding': 'UTF-8',
                        'license': license_name,
                        'method': 'Pinned HTTPS GET; preserve verbatim generated tool-documentation section and LICENSE; sanitize IP and credential sample syntax in full README snapshot.'})
    metadata_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
    print('Saved raw tool documentation excerpts and sanitized full README snapshots.')


def schema_type(kind, description):
    if ' | ' in kind:
        return {'type': kind.split(' | ')}
    if not kind:
        return {}
    if kind.endswith('[]'):
        return {'type': 'array', 'items': schema_type(kind[:-2], description)}
    if kind == 'array':
        return {'type': 'array'}
    if kind == 'object':
        return {'type': 'object'}
    if kind not in {'string', 'number', 'integer', 'boolean'}:
        raise ValueError(f'Unknown documented type: {kind}')
    return {'type': kind}


def public_definitions(server):
    text = (ROOT / 'sources' / server / 'README.md').read_text()
    if server == 'github':
        text = text.split('<!-- START AUTOMATED TOOLS -->', 1)[1].split('<!-- END AUTOMATED TOOLS -->', 1)[0]
        pattern = r'^- \*\*([a-z][a-z0-9_]*)\*\* - (.+)$'
        param_pattern = r'^  - `([^`]+)`: (.*?)\s+\(([^()\n,]+), (required|optional)\)(?=\n|$)'
    else:
        text = text.split('### Tools', 1)[-1]
        pattern = r'^- \*\*(browser_[a-z0-9_]+)\*\*$'
        param_pattern = r'^    - `([^`]+)` \(([^(),]*)(, optional)?\): (.+)$'
    matches = list(re.finditer(pattern, text, re.M))
    definitions = {}
    for index, match in enumerate(matches):
        block = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        name = match[1]
        description = match[2] if server == 'github' else re.search(r'^  - Description: (.+)$', block, re.M)[1]
        properties = {}
        required = []
        params = list(re.finditer(param_pattern, block, re.M | (re.S if server == 'github' else 0)))
        expected = re.findall(r'^\s+- `([^`]+)`[: ]', block, re.M)
        assert [p[1] for p in params] == expected, (name, expected, [p[1] for p in params])
        for param in params:
            if server == 'github':
                key, desc, kind, requirement = param.groups()
                is_required = requirement == 'required'
            else:
                key, kind, optional, desc = param.groups()
                if kind == 'optional':
                    kind, optional = '', True
                is_required = not optional
            properties[key] = {**schema_type(kind, desc), 'description': desc}
            if is_required:
                required.append(key)
        schema = {'type': 'object', 'properties': properties, 'required': required}
        definition = {'name': name, 'description': description, 'inputSchema': schema}
        if name in definitions:
            assert definitions[name] == definition, f'Conflicting canonical duplicate: {name}'
        definitions[name] = definition
    return definitions


def local_definitions():
    cache = json.loads(CACHE.read_text())
    definitions = {}
    timestamps = {}
    for server, count in LOCAL_COUNTS.items():
        entry = cache['servers'][server]
        assert len(entry['tools']) == count, (server, len(entry['tools']))
        timestamps[server] = entry['cachedAt']
        for tool in entry['tools']:
            selected = sanitize({key: tool[key] for key in ('name', 'description', 'inputSchema')})
            definitions[f'{server}/{tool["name"]}'] = selected
    assert len(definitions) == 100
    return definitions, timestamps


def jsonl(filename, records):
    data = ''.join(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n' for record in records)
    path = ROOT / filename
    if filename in {'tools.jsonl', 'questions.jsonl'} and path.exists():
        assert path.read_bytes() == data.encode(), f'Frozen corpus changed: {filename}; explicit review required'
        return
    path.write_text(data)


def build():
    local, timestamps = local_definitions()
    public = {server: public_definitions(server) for server in PUBLIC}
    rows = []
    for filename in ('local.tsv', 'public.tsv'):
        for line in (ROOT / filename).read_text().splitlines():
            if not line or line.startswith('#'):
                continue
            cells = line.split('\t')
            assert len(cells) == 7, (filename, cells)
            rows.append(cells)
    assert len(rows) == 200
    overrides = json.loads((ROOT / 'question_overrides.json').read_text())
    intent_groups = json.loads((ROOT / 'intent_groups.json').read_text())
    tools, sources, questions = [], [], []
    for tool_id, function, when, query1, query2, mode, intent in rows:
        server, name = tool_id.split('/', 1)
        origin = 'local' if server in LOCAL_COUNTS else 'public'
        tools.append({'tool_id': tool_id, 'name': name, 'origin': origin, 'function': function, 'when_to_use': when})
        if origin == 'local':
            definition = local[tool_id]
            provenance = {'source_path': str(CACHE), 'cached_at': timestamps[server],
                          'license': 'NOASSERTION', 'source_sha256': digest(canonical(definition))}
        else:
            definition = sanitize(public[server][name])
            repo, revision, license_name = PUBLIC[server]
            provenance = {'source_url': f'https://github.com/{repo}/blob/{revision}/README.md',
                          'revision': revision, 'license': license_name,
                          'source_sha256': digest((ROOT / 'sources' / server / 'README.md').read_bytes())}
        sources.append({'tool_id': tool_id, 'origin': origin, **provenance, **definition})
        for n, query in enumerate((query1, query2), 1):
            key = f'{tool_id}:{n}'
            override = overrides.get(key, {})
            category = 'direct' if n == 1 else mode
            # Pairs share an intent only when manually declared paraphrases.
            intent_id = intent if mode == 'paraphrase' else f'{intent}-{n}'
            intent_id = intent_groups.get(key, override.get('intent_id', intent_id))
            questions.append({'id': f'q{len(questions) + 1:04}',
                              'intent_id': intent_id,
                              'query': query, 'relevant_tool_ids': override.get('relevant_tool_ids', [tool_id]),
                              'split': '', 'category': category})
    intent_ids = sorted({q['intent_id'] for q in questions})
    random.Random(42).shuffle(intent_ids)
    test_ids = set(intent_ids[:round(len(intent_ids) * 0.2)])
    for question in questions:
        question['split'] = 'test' if question['intent_id'] in test_ids else 'dev'
    jsonl('tools.jsonl', tools)
    jsonl('sources.jsonl', sources)
    jsonl('questions.jsonl', questions)
    counts = {'tools': len(tools), 'sources': len(sources), 'questions': len(questions),
              'origins': {o: sum(t['origin'] == o for t in tools) for o in ('local', 'public')},
              'servers': {s: sum(t['tool_id'].startswith(s + '/') for t in tools) for s in [*LOCAL_COUNTS, *PUBLIC]},
              'splits': {s: sum(q['split'] == s for q in questions) for s in ('dev', 'test')},
              'categories': {c: sum(q['category'] == c for q in questions) for c in ('direct', 'paraphrase', 'boundary')},
              'intents': len(intent_ids), 'multi_label_questions': sum(len(q['relevant_tool_ids']) > 1 for q in questions)}
    audited = [*sorted((ROOT / 'sources').rglob('*')), ROOT / 'tools.jsonl', ROOT / 'sources.jsonl',
               ROOT / 'questions.jsonl', ROOT / 'local.tsv', ROOT / 'public.tsv',
               ROOT / 'question_overrides.json', ROOT / 'intent_groups.json',
               ROOT / 'build_corpus.py', ROOT / 'validate_corpus.py']
    hashes = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in audited if p.is_file()}
    manifest = {'format_version': 1, 'counts': counts, 'seed': 42,
                'split_method': 'Sort unique manually assigned intent_id values, Python random.Random(42).shuffle, first round(20%) intent groups to test; no per-question split.',
                'acquisition_method': 'Only explicit Pi cache definitions and HTTPS pinned official README/LICENSE; no credentials/config/session reads, installs, builds or MCP execution.',
                'public_selections': {s: {'repository': r, 'revision': v, 'license': l,
                                          'names': [t['name'] for t in tools if t['tool_id'].startswith(s + '/')]}
                                      for s, (r, v, l) in PUBLIC.items()},
                'local_source': {'path': str(CACHE), 'cached_at_unit': 'Unix milliseconds', 'cached_at': timestamps,
                                 'enabled_set_basis': 'User-specified global enabled selection; cache does not attest enablement. No config inspected.'},
                'source_sha256_semantics': {'local': 'SHA256 of sanitized name/description/inputSchema, UTF-8 JSON, keys sorted, compact separators.',
                                           'public': 'SHA256 of stored sanitized full pinned README snapshot; sources/acquisition.json also records upstream raw byte hashes and verbatim raw tool-section excerpt hashes. Schemas reconstructed from parameter docs, not runtime discovery.'},
                'curation_notes': {
                    'scope': '只增加固定离线检索语料及其审计材料，不涉及运行时、模型推理、工具执行、依赖安装、构建或提交。未使用子代理。',
                    'local_selection': '严格取用户指定七个服务的 100 个缓存定义。只选择 name、description、inputSchema 和 cachedAt；不落盘完整缓存、configHash、resources、prompts、instructions。全局启用状态依据用户提供的选择，缓存本身不能证明启用状态。',
                    'public_selection': '75 个 GitHub 工具与 25 个 Playwright 工具；从固定提交自动生成的 README 工具章节选择真实规范名称。GitHub 自动工具章节实际去重后 92 个名称；get_label 在两个工具分类重复出现但定义完全相同，只计一次。排除远程附加工具、兼容别名、意图版 Copilot 重叠工具；没有把 method/action 等参数取值拆成伪工具。Playwright 选择通用交互和网络状态，未选运行任意服务端代码、认证配置读取或浏览器安装等项。',
                    'schema_reconstruction': '公开 inputSchema 是文档重建，不是原始运行时 schema。逐条保留文档参数名称、类型、必填性及参数说明；多行参数说明完整保留，string | null 保留联合类型。array/object 的未公开嵌套结构不猜测；枚举、条件必填和默认值保留在原始参数说明里，不声称恢复未记录的运行时约束。中文检索字段不直接复制 schema。',
                    'manual_curation': 'local.tsv 和 public.tsv 的每一行分别手工编写能力、场景边界和两个真实需求；脚本仅解析文档参数、序列化及划分，不从名称模板或模型生成问题。query 是需求而非工具说明的复制；示例标识、日期、路径和域名是人工合成，问题中无真实凭据或主机地址。',
                    'semantic_intents': '意图表示动作、对象和改变可用工具的前提，不按工具名或参数值机械赋号。intent_groups.json 为全局手工语义复核：跨浏览器等价的拖放、悬停、读取元素文字、控制台列表、导航、截图、窗口尺寸、上传等并组；出现/消失、页面/元素截图、开新页/当前页导航、原文替换/首尾追加、租户/运营账户、对话/磁盘/远程传输等保留不同意图。category=boundary 不自动产生不同意图；paraphrase 同组。等价意图同 split，工具本身允许同时出现在两 split。这不是按工具冷启动评测。',
                    'split': '对排序后的全部唯一 intent_id 用 Python random.Random(42) 洗牌，前 round(20%) 组作为 test，其余 dev。按意图组而非问题条目分割；最终 321/79 个问题。两 split 均覆盖本地与公开来源。未用模型做意图聚类；语义边界仍可由人工审查。',
                    'relevance_policy': '多标签只纳入当前需求和前提下能直接完成动作的定义，不列未来步骤、先决步骤、工具内代理参数名或可通过任意脚本模拟一切的万能路径。优先用专门定义；当两个专门定义确有交集时多标签。对称浏览器重叠均标双来源。未知 URL、未登录、页面未加载等前提不可静默补充。',
                    'browser_boundaries': '缓存 click 等绝大部分网页操作确实要求 pageId；new_page 要求 url。chrome close_page 不能关闭最后页面，Playwright browser_close/browser_tabs 可表达当前页关闭。网页内元素拖放不同于外部 MIME/文件投递；元素快照不同于截图；单条控制台编号不同于日志列表；前进、等待任一文本、CPU 节流、堆快照及性能洞察不强行标 Playwright 通用操作。窗口 resize 不等同 emulate 的设备视口，已移除该误标。企微截图题仅给文档 URL 并未说明页面已打开，因此只标企微专用截图；没有把需先导航的普通截图混入。',
                    'document_boundaries': '知识文档按编号读完整正文、按条件查页面清单、语义检索片段、TXDOC 多关键词检索和企微链接完整正文读取分开。知识表字段、视图与数据行分开；企微单格与批量写入存在交集所以单格题多标签。知识标题变更允许正文不动的通用保存作为替代，附件扩展名保留题仅标专用重命名。',
                    'tce_boundaries': '四种传输定义分别对应对话内容到远程、远程内容到对话、远程主机互传、本地磁盘双向传输。前三类缓存声明十 MB 上限；本地隧道工具返回命令序列而非已执行传输，声明依赖和无大小限制。对话读取远程文本可以用 SSH 输出，因此读取题标 fetch_file/ssh_exec；其他方向不把 SSH 当万能传输替代。设备现有密码查找 query_server_password/password_cli 双标；租户 BSP 与运营 CAM 管理及清理白名单区分。',
                    'github_boundaries': 'issue 与 PR 会话评论、行级评审评论、待提交评审、评审线程状态、Discussions 回复和答案状态分开。代码扫描、Dependabot、凭据泄露、全球/组织/仓库公告分开。Git 标签对象与 release 说明不同；源码文字搜索与提交消息搜索不同。read/list/write 的 method 都是一个真实工具而非多个参数伪工具。',
                    'source_safety': '来源描述只做安全脱敏，不改写原始功能或工具中的指令式文案；这些文案是审计内容，不执行。递归清理示例 IPv4、命令行密码、赋值密码、Bearer 样例、凭据形状字符串及 URL 用户密码，使用通用模式而非在脚本里保留原私有值。公开完整 README 的安装段有公开占位样例也被脱敏；工具章节原文与 LICENSE 原样保留用于审计，原完整文件哈希单独保留。',
                    'uncertainties': '私有工具许可证不可核实，标 NOASSERTION。whitelist 描述同时宣称本机 HTTP 与 SSH 到 CLI 环境，未执行探测，中文能力不选择具体拓扑。query_env_master 的表格保留指令、TQL 无需调用说明与其他来源文案原样保留，数据不将其当执行授权。公开工具 availability/可选能力/权限只来自文档，不代表部署时已启用。',
                    'review': '数量、唯一性、字段精确集合、来源一一对应、哈希、确定性分组、两 split 来源覆盖、每工具至少两条相关问题、无逐字重复需求及来源示例脱敏均有离线验证。需求含义与全替代标签无法用结构校验证明完备，已手工跨表复核，仍欢迎逐行复审。详细说明放 manifest 数据集注记，未创建项目设计文档。',
                    'pre_model_label_corrections': '模型运行前按逐题审查仅修正六条 relevant_tool_ids：q0181/q0182 已定位上传控件但选择器尚未打开，移除 playwright/browser_file_upload；q0365 已打开文件选择器，移除 chrome-devtools/upload_file；q0295/q0296 单文件新增或更新允许 github/push_files 的单元素文件数组，补充该替代标签；q0353 未声明当前页不是最后一页，移除 chrome-devtools/close_page。400 条题面的 id、query、intent_id、category、split 全部不变，保留原 79 条 test，不重新划分。三个上传问题仍保守共享同一意图组。tools.jsonl 与全部来源定义保持原字节。'
                },
                'limitations': ['TAPD contains only four multiplexed entrypoints; no parameter-value pseudo-tools.',
                                'Local licenses are unverified (NOASSERTION); private cache definitions are not claimed to be public.',
                                'README-reconstructed schemas preserve documented types, requiredness and parameter prose, not undocumented runtime constraints.',
                                'Public definitions are canonical documented names, not a claim of deployment, enabled capabilities, credentials or tool execution.',
                                'Offline manually curated demands; multi-label relevance denotes direct functional alternatives, not complete workflows or prerequisite steps.',
                                'Public set uses GitHub and Playwright only; no fallback reference server revision needed.',
                                'Local whitelist description has contradictory execution-location claims; capability is curated without choosing a topology.'],
                'hashes_sha256': hashes}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--acquire', action='store_true')
    parser.add_argument('--list-public', action='store_true')
    parser.add_argument('--audit-public', action='store_true')
    args = parser.parse_args()
    if args.acquire:
        acquire()
    elif args.audit_public:
        audit_public()
    elif args.list_public:
        for server in PUBLIC:
            for definition in public_definitions(server).values():
                print(server + '/' + definition['name'] + '\t' + definition['description'])
    else:
        build()
