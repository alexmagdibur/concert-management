"""Store revocable session digests on accounts."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "3f52e6da10ac"
down_revision = "9b5e9ccffef3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "account",
        sa.Column("session_tokens", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade():
    op.drop_column("account", "session_tokens")
