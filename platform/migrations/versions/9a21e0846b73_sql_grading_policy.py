"""Add explicit SQL grading policy without guessing existing problem requirements."""

from alembic import op
import sqlalchemy as sa

revision = "9a21e0846b73"
down_revision = "48d8250d19bd"
branch_labels = None
depends_on = None


def upgrade():
    # On a fresh installation the SQL plugin creates its table after migrations.
    if sa.inspect(op.get_bind()).has_table("sql_challenge"):
        op.add_column(
            "sql_challenge", sa.Column("grading_policy", sa.JSON(), nullable=True)
        )


def downgrade():
    if sa.inspect(op.get_bind()).has_table("sql_challenge"):
        op.drop_column("sql_challenge", "grading_policy")
