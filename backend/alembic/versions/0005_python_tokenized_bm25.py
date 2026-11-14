"""Python-tokenized text and pg_textsearch BM25.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

from app.rag.persistence.fts import search_text

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_textsearch")
    op.add_column("chunks", sa.Column("search_text", sa.Text(), nullable=False, server_default=""))
    conn = op.get_bind()
    last_id = None
    while True:
        rows = conn.execute(sa.text("""
            SELECT c.id, d.title, c.heading_path, c.content
            FROM chunks c JOIN documents d ON d.id = c.doc_id
            WHERE CAST(:last AS uuid) IS NULL OR c.id > CAST(:last AS uuid)
            ORDER BY c.id LIMIT 200
        """), {"last": last_id}).all()
        if not rows:
            break
        conn.execute(sa.text("UPDATE chunks SET search_text = :value WHERE id = :id"), [
            {"id": row.id, "value": search_text("\n".join(
                part for part in (row.title, row.heading_path, row.content) if part
            ))} for row in rows
        ])
        last_id = rows[-1].id
    op.execute("CREATE INDEX ix_chunks_bm25 ON chunks USING bm25(search_text) WITH (text_config='simple')")
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_column("chunks", "tsv")
    op.execute("DROP EXTENSION IF EXISTS pg_jieba")


def downgrade() -> None:
    op.add_column("chunks", sa.Column("tsv", sa.dialects.postgresql.TSVECTOR(), nullable=True))
    op.execute("UPDATE chunks SET tsv = to_tsvector('simple', search_text)")
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.drop_index("ix_chunks_bm25", table_name="chunks")
    op.drop_column("chunks", "search_text")
