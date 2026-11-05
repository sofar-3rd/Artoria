import psycopg

from tests.conftest import TEST_URL


def test_pgvector_and_jieba_available():
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_jieba")
        tokens = conn.execute(
            "SELECT to_tsvector('jiebacfg', '回滚部署')::text"
        ).fetchone()[0]
        assert "'回滚'" in tokens and "'部署'" in tokens
        dist = conn.execute("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector").fetchone()[0]
        assert dist == 0
