from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260610_0001"
down_revision = "20260607_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_clarification",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "unresolved_action_fingerprint",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("source_input_from_seq", sa.BigInteger(), nullable=False),
        sa.Column("source_input_to_seq", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pending_clarification"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name="fk_pending_clarification_conversation_id_conversation",
        ),
        sa.CheckConstraint(
            "status in ('open', 'consumed', 'expired', 'superseded')",
            name=op.f("ck_pending_clarification_pending_clarification_status"),
        ),
        sa.CheckConstraint(
            "source_input_from_seq <= source_input_to_seq",
            name=op.f(
                "ck_pending_clarification_pending_clarification_input_window_order"
            ),
        ),
    )
    op.create_index(
        "uq_pending_clarification_one_open_per_conversation",
        "pending_clarification",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pending_clarification_one_open_per_conversation",
        table_name="pending_clarification",
    )
    op.drop_table("pending_clarification")
