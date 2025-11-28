"""add password_hash to users

Revision ID: 0002_add_pw_hash
Revises: 0001_initial
Create Date: 2025-11-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_pw_hash'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255)))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('password_hash')
