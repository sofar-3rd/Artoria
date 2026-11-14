import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://sagent:sagent@localhost:5433/sagent")
TEST_DB = "sagent_rag_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Must be set before any `app` module is imported.
os.environ["DATABASE_URL"] = TEST_URL
os.environ["OPENAI_API_KEY"] = "test-key"


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f"CREATE DATABASE {TEST_DB}")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=True,
    )


def count_checkpoints(thread_id: str) -> int:
    with psycopg.connect(TEST_URL) as conn:
        row = conn.execute(
            "SELECT count(*) FROM checkpoints WHERE thread_id = %s", (thread_id,)
        ).fetchone()
        return row[0]


def _truncate() -> None:
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE threads, turns, turn_tool_calls, "
            "checkpoints, checkpoint_blobs, checkpoint_writes, "
            "chunks, documents, knowledge_bases CASCADE"
        )


@pytest.fixture(autouse=True)
def _clean_rag_tables(request):
    """Start every rag test from empty rag tables, so tests neither depend on order nor on earlier failures."""
    if "tests/rag" in str(request.node.fspath).replace("\\", "/"):
        with psycopg.connect(TEST_URL, autocommit=True) as conn:
            conn.execute("TRUNCATE chunks, documents, knowledge_bases CASCADE")
    yield


@pytest.fixture
def running_app():
    from tests.fakes import Scripted

    @asynccontextmanager
    async def factory(script, model_cls=Scripted, rag=None):
        from app.main import create_app

        model = model_cls(script=script)
        app = create_app(model=model, rag=rag)
        app.state.test_model = model
        async with app.router.lifespan_context(app):
            _truncate()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield app, client

    return factory
