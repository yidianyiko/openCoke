from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from coke import schema

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)

ACCOUNT_A = "00000000000000000000000000000001"
ACCOUNT_B = "00000000000000000000000000000002"
ACCOUNT_C = "00000000000000000000000000000003"
CHANNEL_IDENTITY_A = "10000000000000000000000000000001"
CHANNEL_A = "20000000000000000000000000000001"
CONVERSATION_A = "30000000000000000000000000000001"
TURN_A = "40000000000000000000000000000001"
MESSAGE_A = "50000000000000000000000000000001"
REMINDER_A = "60000000000000000000000000000001"
OUTBOX_A = "70000000000000000000000000000001"
AUTH_ARTIFACT_A = "80000000000000000000000000000001"


@pytest.fixture
def postgres_session() -> Iterator[Session]:
    database_url = os.environ.get("COKE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("COKE_TEST_DATABASE_URL is not set")

    engine = sa.create_engine(database_url, future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def seed_account(session: Session, account_id: str = ACCOUNT_A) -> None:
    if session.execute(
        sa.select(schema.account.c.id).where(schema.account.c.id == account_id)
    ).first():
        return
    session.execute(
        schema.account.insert().values(
            id=account_id,
            origin="web_first",
            default_timezone="UTC",
            lifecycle="active",
            created_at=NOW,
            updated_at=NOW,
        )
    )


def seed_channel_identity(
    session: Session,
    account_id: str = ACCOUNT_A,
    channel_identity_id: str = CHANNEL_IDENTITY_A,
    provider_subject: str = "whatsapp:+15555550100",
) -> None:
    seed_account(session, account_id)
    session.execute(
        schema.channel_identity.insert().values(
            id=channel_identity_id,
            account_id=account_id,
            provider_type="whatsapp_evolution",
            provider_subject=provider_subject,
            lifecycle="active",
            is_account_anchor=True,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def seed_channel(
    session: Session,
    account_id: str = ACCOUNT_A,
    channel_identity_id: str = CHANNEL_IDENTITY_A,
    channel_id: str = CHANNEL_A,
) -> None:
    seed_channel_identity(session, account_id, channel_identity_id)
    session.execute(
        schema.channel.insert().values(
            id=channel_id,
            account_id=account_id,
            channel_identity_id=channel_identity_id,
            provider_type="whatsapp_evolution",
            lifecycle="active",
            connection_state="connected",
            removable=True,
            connected_at=NOW,
            removed_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def seed_conversation(
    session: Session,
    account_id: str = ACCOUNT_A,
    conversation_id: str = CONVERSATION_A,
) -> None:
    seed_account(session, account_id)
    session.execute(
        schema.conversation.insert().values(
            id=conversation_id,
            account_id=account_id,
            latest_inbound_seq=1,
            last_closed_inbound_seq=0,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def seed_turn(
    session: Session,
    conversation_id: str = CONVERSATION_A,
    turn_id: str = TURN_A,
) -> None:
    seed_conversation(session, conversation_id=conversation_id)
    session.execute(
        schema.turn.insert().values(
            id=turn_id,
            conversation_id=conversation_id,
            trigger_id="trigger:seed",
            trigger_type="inbound_message",
            mode="interactive",
            input_from_seq=1,
            input_to_seq=1,
            superseded_by_inbound_seq=None,
            started_at=NOW,
            completed_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def seed_reminder(
    session: Session,
    account_id: str = ACCOUNT_A,
    reminder_id: str = REMINDER_A,
) -> None:
    seed_account(session, account_id)
    session.execute(
        schema.reminder.insert().values(
            id=reminder_id,
            owner_account_id=account_id,
            content="seed reminder",
            content_hash="seed-reminder",
            kind="timed",
            next_fire_at=NOW,
            recurrence_rule={},
            captured_timezone="UTC",
            duration_minutes=15,
            lifecycle="active",
            hidden_from_calendar=False,
            shared_reminder_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def seed_outbox(session: Session, outbox_id: str = OUTBOX_A) -> None:
    session.execute(
        schema.outbox.insert().values(
            id=outbox_id,
            topic="notification.render",
            idempotency_key=f"idempotency:{outbox_id}",
            payload={"seed": True},
            traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            status="pending",
            created_at=NOW,
            published_at=None,
            processed_at=None,
            acked_at=None,
            retry_count=0,
            last_error=None,
        )
    )
