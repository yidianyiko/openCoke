from __future__ import annotations

import sqlalchemy as sa
from alembic import op

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
    op.create_unique_constraint(
        op.f("uq_message_inbound_seq"),
        "message",
        ["conversation_id", "direction", "seq"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_message_inbound_seq", "message", type_="unique")
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
