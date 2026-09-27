"""add claim requests, institution branding, and email verification

Revision ID: f81d0c7e3a12
Revises: e5b8c2f4a901
"""
from alembic import op
import sqlalchemy as sa

revision = "f81d0c7e3a12"
down_revision = "e5b8c2f4a901"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("institution") as batch:
        batch.add_column(sa.Column("accent_color", sa.String(7), nullable=True))
        batch.add_column(sa.Column("website", sa.String(255), nullable=True))
        batch.add_column(sa.Column("logo_key", sa.String(64), nullable=True))
    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "claim_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institution.id"), nullable=False),
        sa.Column("student_identifier", sa.String(100), nullable=False),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("user_id", "institution_id", "status"):
        op.create_index(f"ix_claim_request_{column}", "claim_request", [column])


def downgrade():
    for column in ("status", "institution_id", "user_id"):
        op.drop_index(f"ix_claim_request_{column}", table_name="claim_request")
    op.drop_table("claim_request")
    with op.batch_alter_table("user") as batch:
        batch.drop_column("email_verified")
    with op.batch_alter_table("institution") as batch:
        for column in ("logo_key", "website", "accent_color"):
            batch.drop_column(column)
