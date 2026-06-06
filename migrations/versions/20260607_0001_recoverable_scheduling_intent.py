from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260607_0001"
down_revision = "20260531_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recoverable_scheduling_intent",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("creator_account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocker", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("local_trigger_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("captured_timezone", sa.String(length=64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("unresolved_reference_text", sa.Text(), nullable=False),
        sa.Column("source_turn_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("source_input_from_seq", sa.BigInteger(), nullable=False),
        sa.Column("source_input_to_seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_message_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("facts_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_turn_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_recoverable_scheduling_intent"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name="fk_recoverable_scheduling_intent_conversation_id_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["creator_account_id"],
            ["account.id"],
            name="fk_recoverable_scheduling_intent_creator_account_id_account",
        ),
        sa.ForeignKeyConstraint(
            ["source_turn_id"],
            ["turn.id"],
            name="fk_recoverable_scheduling_intent_source_turn_id_turn",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_turn_id"],
            ["turn.id"],
            name="fk_recoverable_scheduling_intent_consumed_turn_id_turn",
        ),
        sa.CheckConstraint(
            "operation in ('shared_reminder_create')",
            name=op.f("ck_recoverable_scheduling_intent_recoverable_operation"),
        ),
        sa.CheckConstraint(
            "status in ('open', 'consumed', 'expired', 'superseded')",
            name=op.f("ck_recoverable_scheduling_intent_recoverable_status"),
        ),
        sa.CheckConstraint(
            "blocker in ('unmatched_friend', 'ambiguous_friend')",
            name=op.f("ck_recoverable_scheduling_intent_recoverable_blocker"),
        ),
        sa.CheckConstraint(
            "source_input_from_seq <= source_input_to_seq",
            name=op.f(
                "ck_recoverable_scheduling_intent_recoverable_input_window_order"
            ),
        ),
    )
    op.create_index(
        "uq_recoverable_intent_one_open_per_conversation",
        "recoverable_scheduling_intent",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_recoverable_intent_one_open_per_conversation",
        table_name="recoverable_scheduling_intent",
    )
    op.drop_table("recoverable_scheduling_intent")
