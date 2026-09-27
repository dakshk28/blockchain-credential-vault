"""add expansion models and credential replacement link"""
from alembic import op
import sqlalchemy as sa

revision = "c41f2d9a7b10"
down_revision = "8a1b15bca694"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("credential") as batch:
        batch.add_column(sa.Column("replacement_of_id", sa.Integer(), nullable=True))
        batch.create_index("ix_credential_replacement_of_id", ["replacement_of_id"])
        batch.create_foreign_key("fk_credential_replacement", "credential", ["replacement_of_id"], ["id"])
    op.create_table("credential_template", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("institution_id", sa.Integer(), nullable=False), sa.Column("created_by_user_id", sa.Integer(), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("programme", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()), sa.ForeignKeyConstraint(["institution_id"], ["institution.id"]), sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]))
    op.create_table("credential_signature", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("credential_id", sa.Integer(), nullable=False, unique=True), sa.Column("algorithm", sa.String(32), nullable=False), sa.Column("signature", sa.String(128), nullable=False), sa.ForeignKeyConstraint(["credential_id"], ["credential.id"]))
    op.create_table("audit_anchor", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("audit_root", sa.String(64), nullable=False), sa.Column("provider", sa.String(64), nullable=False), sa.Column("anchored_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("share_link", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("token", sa.String(96), nullable=False, unique=True), sa.Column("credential_id", sa.Integer(), nullable=False), sa.Column("student_user_id", sa.Integer(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()), sa.ForeignKeyConstraint(["credential_id"], ["credential.id"]), sa.ForeignKeyConstraint(["student_user_id"], ["user.id"]))

def downgrade():
    op.drop_table("share_link"); op.drop_table("audit_anchor"); op.drop_table("credential_signature"); op.drop_table("credential_template")
    with op.batch_alter_table("credential") as batch:
        batch.drop_constraint("fk_credential_replacement", type_="foreignkey"); batch.drop_index("ix_credential_replacement_of_id"); batch.drop_column("replacement_of_id")
