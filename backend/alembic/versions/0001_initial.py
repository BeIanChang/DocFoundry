"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2025-11-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Use models metadata to create all tables
    bind = op.get_bind()
    from app.db import models
    models.Base.metadata.create_all(bind=bind)


def downgrade():
    bind = op.get_bind()
    from app.db import models
    models.Base.metadata.drop_all(bind=bind)
