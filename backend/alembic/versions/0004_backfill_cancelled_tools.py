"""mark tools cut off by a cancelled or failed turn

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older recorders left such tools as status=ok with no duration.
    op.execute(
        """
        UPDATE turn_tool_calls AS tc
        SET status = 'cancelled',
            duration_ms = GREATEST(t.duration_ms - tc.started_offset_ms, 0)
        FROM turns AS t
        WHERE tc.turn_id = t.id
          AND tc.duration_ms IS NULL
          AND t.status <> 'ok'
        """
    )


def downgrade() -> None:
    # Data fix only; the previous values are not recoverable.
    pass
