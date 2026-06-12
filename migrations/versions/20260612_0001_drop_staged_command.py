from __future__ import annotations

from alembic import op

revision = "20260612_0001"
down_revision = "20260611_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("staged_command", if_exists=True)


def downgrade() -> None:
    # Downgrade policy: do not recreate retired optimistic-staging storage.
    # The current runtime has no model, repository, or materializer for this table.
    pass
