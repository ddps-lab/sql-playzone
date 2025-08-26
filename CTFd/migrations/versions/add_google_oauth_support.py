"""Add Google OAuth support

Revision ID: add_google_oauth
Revises: f73a96c97449
Create Date: 2025-01-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_google_oauth'
down_revision = 'f73a96c97449'
branch_labels = None
depends_on = None


def upgrade():
    # Change oauth_id column type from Integer to String to support Google OAuth IDs
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('oauth_id',
                            existing_type=sa.Integer(),
                            type_=sa.String(128),
                            existing_nullable=True)
    
    with op.batch_alter_table('teams') as batch_op:
        batch_op.alter_column('oauth_id',
                            existing_type=sa.Integer(),
                            type_=sa.String(128),
                            existing_nullable=True)


def downgrade():
    # Revert oauth_id column type back to Integer
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('oauth_id',
                            existing_type=sa.String(128),
                            type_=sa.Integer(),
                            existing_nullable=True)
    
    with op.batch_alter_table('teams') as batch_op:
        batch_op.alter_column('oauth_id',
                            existing_type=sa.String(128),
                            type_=sa.Integer(),
                            existing_nullable=True)