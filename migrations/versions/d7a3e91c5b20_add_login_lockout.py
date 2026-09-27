"""add login lockout fields to user and missing model indexes

Revision ID: d7a3e91c5b20
Revises: c41f2d9a7b10
"""
from alembic import op
import sqlalchemy as sa

revision = "d7a3e91c5b20"
down_revision = "c41f2d9a7b10"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    # Indexes declared on the models but never migrated (found by `flask db check`).
    op.create_index("ix_credential_template_institution_id", "credential_template", ["institution_id"])
    op.create_index("ix_share_link_token", "share_link", ["token"], unique=True)


def downgrade():
    op.drop_index("ix_share_link_token", table_name="share_link")
    op.drop_index("ix_credential_template_institution_id", table_name="credential_template")
    with op.batch_alter_table("user") as batch:
        batch.drop_column("locked_until")
        batch.drop_column("failed_login_count")
