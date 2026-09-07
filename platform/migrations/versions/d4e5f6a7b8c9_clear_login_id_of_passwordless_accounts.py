"""Clear the login ID copied onto accounts that never had a password.

The first login-ID migration copied every unique name, including the names
of Google-created accounts that had not finished onboarding. Those accounts
never logged in by name, and the copied ID made the onboarding page suggest
the display name as the ID. They choose an ID during onboarding instead.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "b7c1e4d2a9f3"
branch_labels = None
depends_on = None


def upgrade():
    users = sa.table(
        "users",
        sa.column("login_id", sa.String),
        sa.column("name", sa.String),
        sa.column("password", sa.String),
    )
    op.execute(
        users.update()
        .where(users.c.password.is_(None))
        .where(users.c.login_id == users.c.name)
        .values(login_id=None)
    )


def downgrade():
    # The copy was an artifact; nothing to restore.
    pass
