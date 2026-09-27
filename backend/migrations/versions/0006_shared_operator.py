"""Create the shared operator account every installation can sign in with.

The values are frozen here on purpose (a migration is a snapshot); they match
tram.infrastructure.shared_operator, which also restores the account on stack start.
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

USERNAME = "operator"
PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$6VTe8AWzqOGfq+pfK+TYrQ$FF+IC78DyTy2V9UVBNGunzZROQDLk9FotnsiEhzhcEY"
users = sa.table(
    "users",
    sa.column("id", sa.String),
    sa.column("username", sa.String),
    sa.column("password_hash", sa.String),
    sa.column("role", sa.String),
    sa.column("is_active", sa.Integer),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    exists = op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(users).where(users.c.username == USERNAME)
    )
    if not exists:
        op.bulk_insert(
            users,
            [
                {
                    "id": str(uuid4()),
                    "username": USERNAME,
                    "password_hash": PASSWORD_HASH,
                    "role": "operator",
                    "is_active": 1,
                    "created_at": datetime.now(UTC),
                }
            ],
        )


def downgrade() -> None:
    op.execute(users.delete().where(users.c.username == USERNAME))
