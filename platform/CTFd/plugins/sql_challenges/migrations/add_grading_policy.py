"""Complete the public policy schema after SQL plugin tables are created."""

from sqlalchemy import Column, JSON, inspect

revision = "add_grading_policy"
down_revision = "update_init_query_column"
branch_labels = None
depends_on = None


def upgrade(op=None):
    columns = inspect(op.get_bind()).get_columns("sql_challenge")
    # Existing installs may already have the column from core revision 9a21e0846b73.
    if "grading_policy" not in {column["name"] for column in columns}:
        op.add_column("sql_challenge", Column("grading_policy", JSON(), nullable=True))


def downgrade(op=None):
    # Core revision 9a21e0846b73 owns removal. A plugin downgrade must not erase
    # policies created by that revision or by an operator's reviewed setup.
    pass
