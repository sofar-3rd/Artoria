import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

ADMIN_URL = "postgresql://sagent:sagent@localhost:5433/sagent"
TEST_URL = "postgresql://sagent:sagent@localhost:5433/sagent_test"
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Must be set before any `app` module is imported.
os.environ["DATABASE_URL"] = TEST_URL
os.environ["OPENAI_API_KEY"] = "test-key"


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'sagent_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE sagent_test")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=True,
    )
