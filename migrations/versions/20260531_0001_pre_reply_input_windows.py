from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260531_0001"
down_revision = "20260529_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation",
        sa.Column(
            "last_closed_inbound_seq",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        op.f("ck_conversation_input_window_order"),
        "conversation",
        "last_closed_inbound_seq >= 0 and latest_inbound_seq >= last_closed_inbound_seq",
    )
    op.execute("""
        update conversation as c
        set last_closed_inbound_seq = least(
            c.latest_inbound_seq,
            closed.max_based_on_inbound_seq
        )
        from (
            select
                t.conversation_id,
                max(t.based_on_inbound_seq) as max_based_on_inbound_seq
            from turn as t
            join output_disposition as od on od.turn_id = t.id
            where t.based_on_inbound_seq is not null
              and od.disposition in ('replied', 'no_reply', 'pending_async_reply')
            group by t.conversation_id
        ) as closed
        where c.id = closed.conversation_id
        """)
    op.alter_column("conversation", "last_closed_inbound_seq", server_default=None)
    op.add_column("turn", sa.Column("input_from_seq", sa.BigInteger(), nullable=True))
    op.add_column("turn", sa.Column("input_to_seq", sa.BigInteger(), nullable=True))
    op.add_column(
        "turn",
        sa.Column("superseded_by_inbound_seq", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "update turn set input_from_seq = based_on_inbound_seq, "
        "input_to_seq = based_on_inbound_seq "
        "where based_on_inbound_seq is not null"
    )
    op.drop_column("turn", "based_on_inbound_seq")
    op.create_check_constraint(
        op.f("ck_turn_input_window_order"),
        "turn",
        "(input_from_seq is null and input_to_seq is null) or "
        "(input_from_seq is not null and input_to_seq is not null and input_from_seq <= input_to_seq)",
    )
    op.create_table(
        "staged_command",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "command_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "preview_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_staged_command"),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["turn.id"],
            name="fk_staged_command_turn_id_turn",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_staged_command_idempotency"),
        sa.CheckConstraint(
            "status in ('staged', 'materialized', 'superseded')",
            name=op.f("ck_staged_command_status"),
        ),
    )


def downgrade() -> None:
    op.drop_table("staged_command")
    op.drop_constraint("ck_turn_input_window_order", "turn", type_="check")
    op.add_column(
        "turn", sa.Column("based_on_inbound_seq", sa.BigInteger(), nullable=True)
    )
    op.execute("update turn set based_on_inbound_seq = input_to_seq")
    op.drop_column("turn", "superseded_by_inbound_seq")
    op.drop_column("turn", "input_to_seq")
    op.drop_column("turn", "input_from_seq")
    op.drop_constraint(
        "ck_conversation_input_window_order", "conversation", type_="check"
    )
    op.drop_column("conversation", "last_closed_inbound_seq")
