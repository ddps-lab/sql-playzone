"""Create SQL challenge table

Revision ID: create_sql_challenge
Revises:
Create Date: 2025-08-26

"""
from CTFd.models import db
from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime

revision = "create_sql_challenge"
down_revision = None
branch_labels = None
depends_on = None


def upgrade(op=None):
    """Create sql_challenge table if it doesn't exist"""
    bind = op.get_bind()
    inspector = db.inspect(bind)
    
    # Check if table already exists
    if 'sql_challenge' not in inspector.get_table_names():
        op.create_table(
            'sql_challenge',
            Column('id', Integer, ForeignKey('challenges.id', ondelete='CASCADE'), primary_key=True),
            Column('init_query', Text, nullable=True),  # LONGTEXT equivalent in MySQL
            Column('solution_query', Text, nullable=True),  # LONGTEXT equivalent in MySQL
            Column('deadline', DateTime, nullable=True)
        )


def downgrade(op=None):
    """Drop sql_challenge table"""
    op.drop_table('sql_challenge')