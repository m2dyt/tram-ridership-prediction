"""Store login attempt windows across API processes."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="login_attempt_count"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        op.f("ix_login_attempts_window_started_at"),
        "login_attempts",
        ["window_started_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_login_attempts_window_started_at"), table_name="login_attempts")
    op.drop_table("login_attempts")
