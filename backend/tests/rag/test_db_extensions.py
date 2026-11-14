import psycopg

from tests.conftest import TEST_URL


def test_pgvector_and_bm25_available():
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_textsearch")
        assert conn.execute("SELECT amname FROM pg_am WHERE amname='bm25'").fetchone()[0] == "bm25"
        dist = conn.execute("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector").fetchone()[0]
        assert dist == 0
