# Artoria

A small web agent chat: FastAPI + LangGraph react agent (Postgres memory) with a React UI.

## Run

```bash
# 1. Postgres (host port 5433)
docker compose up -d --build --wait   # first build compiles pgvector + pg_jieba (a few minutes)

# 2. Backend
cd backend
cp .env.example .env          # set OPENAI_API_KEY (and OPENAI_BASE_URL / OPENAI_MODEL if needed)
uv sync
uv run alembic upgrade head   # app tables (threads, turns, turn_tool_calls); checkpoint tables come from startup
uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173, /api is proxied to :8000
```

## Using TT Switch (local OpenAI-compatible proxy)

pi reaches models through the TT Switch proxy. Reuse its provider settings in `backend/.env`
(values come from `~/.pi/agent/models.json`, provider `tencent-intranet`):

```
OPENAI_BASE_URL=http://127.0.0.1:15721/pi/tencent-intranet/v1
OPENAI_API_KEY=<apiKey of that provider>
OPENAI_MODEL=hy4-preview-ioa        # any model id listed under that provider
```
TT Switch must be running (it listens on 127.0.0.1:15721). `.env` is git-ignored.

## Test (backend)

```bash
cd backend && uv run pytest
```
Tests use the database `sagent_rag_test` on the same Postgres (created on demand) and a scripted fake model.
The real-model tests are skipped by default: `uv run pytest -m slow` (needs the models, see below).

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/threads` | create session |
| GET | `/api/threads` | list, newest first |
| DELETE | `/api/threads/{id}` | delete session and its checkpoints |
| GET | `/api/threads/{id}/messages` | history incl. tool calls |
| POST | `/api/threads/{id}/chat` | body `{message}`; SSE events `reasoning`, `token`, `tool_call`, `tool_result`, `done`, `error` |

## Knowledge base

Hybrid search (pgvector + Chinese full text via pg_jieba, fused with RRF, reranked by a cross-encoder) over
markdown and PDF documents from a git repository, exposed to the agent as three tools:
`list_knowledge_bases`, `search_knowledge_base`, `read_document`.

```bash
# 1. models (about 4.5 GB), with the SYSTEM python: uv's Python fails the TLS handshake with huggingface.co here
python3 -m venv /tmp/hfv && /tmp/hfv/bin/pip install huggingface_hub
/tmp/hfv/bin/python backend/scripts/download_models.py --dir backend/models

# 2. enable it (backend/.env)
RAG_ENABLED=true
RAG_DEVICE=auto               # cuda, then mps (Apple), then cpu; rerank of 20 passages: ~1 s on mps, ~2.5 s on cpu
RAG_ADMIN_TOKEN=<secret>      # without it the HTTP API cannot create knowledge bases or start syncs (403)

# 3. create and sync a knowledge base (operator CLI; any local directory or git url)
cd backend
uv run python -m app.rag.interfaces.cli create docs --repo https://host/org/docs.git --description "team docs"
uv run python -m app.rag.interfaces.cli sync docs        # incremental: only changed files are re-embedded
uv run python -m app.rag.interfaces.cli list
```

| Method | Path | Notes |
|---|---|---|
| GET | `/api/kbs`, `/api/kbs/{name}` | status, document count, last sync / error, `running` |
| POST | `/api/kbs` | body `{name, description, repo_url, branch, subdir}`; header `X-Admin-Token`; remote git urls only (local paths need `RAG_LOCAL_ROOT`) |
| POST | `/api/kbs/{name}/sync` | 202, runs in the background; header `X-Admin-Token`; 409 while one is running |

Notes: documents over `RAG_MAX_DOCUMENT_BYTES` (20 MB) are skipped and listed in `last_error`; a document that
fits in one chunk (about 100 tokens or less) is a single chunk labelled with its first heading; the first query
after start-up loads the models (about 1.5 s warm, a minute from a cold disk).
