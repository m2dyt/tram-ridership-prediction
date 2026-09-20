"""Persist transition times for stable status-filtered pagination."""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("forecast_runs", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("forecast_runs", sa.Column("finished_at", sa.DateTime(timezone=True)))
    table = sa.table(
        "forecast_runs",
        sa.column("id", sa.String()),
        sa.column("document", sa.JSON()),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("finished_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(table.c.id, table.c.document)).mappings():
        values = {
            key: datetime.fromisoformat(row["document"][key]) if row["document"].get(key) else None
            for key in ("started_at", "finished_at")
        }
        connection.execute(table.update().where(table.c.id == row["id"]).values(**values))


def downgrade():
    op.drop_column("forecast_runs", "finished_at")
    op.drop_column("forecast_runs", "started_at")
