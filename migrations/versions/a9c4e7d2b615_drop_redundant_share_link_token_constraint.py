"""drop the redundant share_link token unique constraint (the unique index remains)

The initial share_link table declared token UNIQUE, and d7a3e91c5b20 added the unique index the model
declares. On PostgreSQL that left both, which `flask db check` reports as drift. SQLite never named
the inline constraint, so this migration only changes PostgreSQL.

Revision ID: a9c4e7d2b615
Revises: f81d0c7e3a12
"""
from alembic import op

revision = "a9c4e7d2b615"
down_revision = "f81d0c7e3a12"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE share_link DROP CONSTRAINT IF EXISTS share_link_token_key")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint("share_link_token_key", "share_link", ["token"])
