# sagent

A small web agent chat: FastAPI + LangGraph react agent (Postgres memory) with a React UI.

## Run

```bash
# 1. Postgres (host port 5433)
docker compose up -d --wait

# 2. Backend
cd backend
cp .env.example .env          # set OPENAI_API_KEY (and OPENAI_BASE_URL / OPENAI_MODEL if needed)
uv sync
uv run alembic upgrade head   # creates the threads table; checkpoint tables are created on startup
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
Tests use database `sagent_test` on the same Postgres and a scripted fake model.

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/threads` | create session |
| GET | `/api/threads` | list, newest first |
| DELETE | `/api/threads/{id}` | delete session and its checkpoints |
| GET | `/api/threads/{id}/messages` | history incl. tool calls |
| POST | `/api/threads/{id}/chat` | body `{message}`; SSE events `token`, `tool_call`, `tool_result`, `done`, `error` |
