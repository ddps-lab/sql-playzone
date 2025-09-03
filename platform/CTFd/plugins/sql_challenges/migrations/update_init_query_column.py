"""Update query columns to LONGTEXT

Revision ID: update_init_query_column
Revises: create_sql_challenge
Create Date: 2025-09-03

"""
from CTFd.models import db

revision = "update_init_query_column"
down_revision = "create_sql_challenge"
branch_labels = None
depends_on = None


def upgrade(op=None):
    """Update query columns to LONGTEXT"""
    bind = op.get_bind()
    
    # Change init_query column to LONGTEXT
    bind.execute("ALTER TABLE sql_challenge MODIFY COLUMN init_query LONGTEXT")
    
    # Change solution_query column to LONGTEXT
    bind.execute("ALTER TABLE sql_challenge MODIFY COLUMN solution_query LONGTEXT")


def downgrade(op=None):
    """Revert query columns back to TEXT"""
    bind = op.get_bind()
    
    # Change columns back to TEXT
    bind.execute("ALTER TABLE sql_challenge MODIFY COLUMN init_query TEXT")
    bind.execute("ALTER TABLE sql_challenge MODIFY COLUMN solution_query TEXT")
