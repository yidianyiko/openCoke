from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260607_0001"
down_revision = "20260531_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "delivery_attempt",
        sa.Column("delivery_source", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "delivery_attempt",
        sa.Column("delivery_intent", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "delivery_attempt",
        sa.Column("retry_attempt", sa.Integer(), nullable=True),
    )
    op.add_column(
        "delivery_attempt",
        sa.Column("traceparent", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "delivery_attempt",
        sa.Column("container", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "delivery_attempt",
        sa.Column("context_token_source", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "delivery_attempt",
        sa.Column("context_token_age_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "delivery_attempt",
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("delivery_attempt", "latency_ms")
    op.drop_column("delivery_attempt", "context_token_age_seconds")
    op.drop_column("delivery_attempt", "context_token_source")
    op.drop_column("delivery_attempt", "container")
    op.drop_column("delivery_attempt", "traceparent")
    op.drop_column("delivery_attempt", "retry_attempt")
    op.drop_column("delivery_attempt", "delivery_intent")
    op.drop_column("delivery_attempt", "delivery_source")
