"""Separate the login ID from the display name.

The display name (users.name) becomes a student's real name and may repeat;
users.login_id is the unique handle used to log in. Existing accounts that
log in with a password keep their current name as the ID, copied here when it
is unique (MySQL compares names case-insensitively, so case variants are left
empty and those accounts log in with their email address). Accounts without a
password (Google sign-in only, onboarding pending) never logged in by name;
they get no ID here and choose one during onboarding.
"""

from collections import Counter

import sqlalchemy as sa
from alembic import op

revision = "b7c1e4d2a9f3"
down_revision = "9a21e0846b73"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("login_id", sa.String(length=128), nullable=True))
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("login_id", sa.String),
        sa.column("password", sa.String),
    )
    rows = bind.execute(
        sa.select(users.c.id, users.c.name).where(users.c.password.isnot(None))
    ).fetchall()
    counts = Counter(str(name or "").strip().lower() for _, name in rows)
    for user_id, name in rows:
        key = str(name or "").strip().lower()
        if key and counts[key] == 1:
            bind.execute(
                users.update()
                .where(users.c.id == user_id)
                .values(login_id=name.strip())
            )
    op.create_index(op.f("ix_users_login_id"), "users", ["login_id"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_users_login_id"), table_name="users")
    op.drop_column("users", "login_id")
