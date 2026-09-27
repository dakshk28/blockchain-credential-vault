"""add Ed25519 key ids, anchor receipts, and credential Merkle proofs

Revision ID: e5b8c2f4a901
Revises: d7a3e91c5b20
"""
from alembic import op
import sqlalchemy as sa

revision = "e5b8c2f4a901"
down_revision = "d7a3e91c5b20"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("credential_signature") as batch:
        batch.add_column(sa.Column("key_id", sa.String(32), nullable=True))
    with op.batch_alter_table("audit_anchor") as batch:
        batch.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="audit"))
        batch.add_column(sa.Column("item_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("network", sa.String(64), nullable=True))
        batch.add_column(sa.Column("tx_hash", sa.String(80), nullable=True))
        batch.add_column(sa.Column("block_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("explorer_url", sa.String(255), nullable=True))
    op.create_table(
        "credential_anchor_proof",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credential_id", sa.Integer(), sa.ForeignKey("credential.id"), nullable=False, unique=True),
        sa.Column("anchor_id", sa.Integer(), sa.ForeignKey("audit_anchor.id"), nullable=False),
        sa.Column("leaf_hash", sa.String(64), nullable=False),
        sa.Column("proof", sa.JSON(), nullable=False),
    )
    op.create_index("ix_credential_anchor_proof_anchor_id", "credential_anchor_proof", ["anchor_id"])


def downgrade():
    op.drop_index("ix_credential_anchor_proof_anchor_id", table_name="credential_anchor_proof")
    op.drop_table("credential_anchor_proof")
    with op.batch_alter_table("audit_anchor") as batch:
        for column in ("explorer_url", "block_number", "tx_hash", "network", "item_count", "kind"):
            batch.drop_column(column)
    with op.batch_alter_table("credential_signature") as batch:
        batch.drop_column("key_id")
