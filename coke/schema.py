from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _id_column() -> Column:
    return Column("id", UUID(as_uuid=False), primary_key=True)


def _created_at() -> Column:
    return Column("created_at", DateTime(timezone=True), nullable=False)


def _updated_at() -> Column:
    return Column("updated_at", DateTime(timezone=True), nullable=False)


account = Table(
    "account",
    metadata,
    _id_column(),
    Column("origin", String(32), nullable=False),
    Column("default_timezone", String(64), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    _created_at(),
    _updated_at(),
    CheckConstraint(
        "origin in ('web_first', 'messaging_first')", name="account_origin"
    ),
    CheckConstraint("lifecycle in ('active', 'disabled')", name="account_lifecycle"),
)

agent_settings = Table(
    "agent_settings",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("assistant_name", String(128), nullable=False),
    Column("user_address_name", String(128), nullable=True),
    Column("persona", Text(), nullable=True),
    Column("background", Text(), nullable=True),
    Column("speaking_style", Text(), nullable=True),
    Column("extra_rules", Text(), nullable=True),
    Column("proactive_enabled", Boolean(), nullable=False),
    Column("memory_enabled", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_agent_settings_account"),
)

user_profile = Table(
    "user_profile",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("real_name", String(160), nullable=True),
    Column("nickname", String(160), nullable=True),
    Column("description", Text(), nullable=True),
    Column("relationship_description", Text(), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_user_profile_account"),
)

account_activation = Table(
    "account_activation",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("first_inbound_received_at", DateTime(timezone=True), nullable=True),
    Column("activation_completed_at", DateTime(timezone=True), nullable=True),
    Column("first_guidance_sent_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_account_activation_account"),
)

account_access = Table(
    "account_access",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("email_verification_state", String(32), nullable=False),
    Column("subscription_state", String(32), nullable=False),
    Column("suspension_state", String(32), nullable=False),
    Column("access_allowed", Boolean(), nullable=False),
    Column("denial_reason", String(160), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_account_access_account"),
)

credential = Table(
    "credential",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("email", String(320), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("email_verified_at", DateTime(timezone=True), nullable=True),
    Column("reset_required", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_credential_account"),
    UniqueConstraint("email", name="uq_credential_email"),
)

session = Table(
    "session",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("token_hash", String(255), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("token_hash", name="uq_session_token_hash"),
)

channel_identity = Table(
    "channel_identity",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("provider_type", String(64), nullable=False),
    Column("provider_subject", String(255), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("is_account_anchor", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "provider_type",
        "provider_subject",
        name="uq_channel_identity_provider_subject",
    ),
)

auth_artifact = Table(
    "auth_artifact",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=True),
    Column(
        "target_account_id",
        UUID(as_uuid=False),
        ForeignKey("account.id"),
        nullable=True,
    ),
    Column("type", String(64), nullable=False),
    Column("purpose", String(128), nullable=False),
    Column("delivery", String(64), nullable=False),
    Column("token_hash", String(255), nullable=False),
    Column("browser_session", String(255), nullable=True),
    Column("continuation", JSONB(), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True), nullable=True),
    Column("delivery_state", String(64), nullable=False),
    Column("resend_count", Integer(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("token_hash", name="uq_auth_artifact_token_hash"),
)

channel = Table(
    "channel",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column(
        "channel_identity_id",
        UUID(as_uuid=False),
        ForeignKey("channel_identity.id"),
        nullable=False,
    ),
    Column("provider_type", String(64), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("connection_state", String(64), nullable=False),
    Column("removable", Boolean(), nullable=False),
    Column("connected_at", DateTime(timezone=True), nullable=True),
    Column("removed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
)

delivery_route = Table(
    "delivery_route",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("channel_id", UUID(as_uuid=False), ForeignKey("channel.id"), nullable=False),
    Column("provider_type", String(64), nullable=False),
    Column("provider_address", String(255), nullable=False),
    Column("route_key", String(255), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("route_key", name="uq_delivery_route_route_key"),
)

conversation = Table(
    "conversation",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("latest_inbound_seq", BigInteger(), nullable=False),
    Column("last_closed_inbound_seq", BigInteger(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_conversation_account"),
    CheckConstraint(
        "last_closed_inbound_seq >= 0 and latest_inbound_seq >= last_closed_inbound_seq",
        name="input_window_order",
    ),
)

turn = Table(
    "turn",
    metadata,
    _id_column(),
    Column(
        "conversation_id",
        UUID(as_uuid=False),
        ForeignKey("conversation.id"),
        nullable=False,
    ),
    Column("trigger_id", String(255), nullable=False),
    Column("trigger_type", String(64), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("input_from_seq", BigInteger(), nullable=True),
    Column("input_to_seq", BigInteger(), nullable=True),
    Column("superseded_by_inbound_seq", BigInteger(), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("trigger_id", name="uq_turn_trigger_id"),
    CheckConstraint(
        "(input_from_seq is null and input_to_seq is null) or "
        "(input_from_seq is not null and input_to_seq is not null and input_from_seq <= input_to_seq)",
        name="input_window_order",
    ),
)

staged_command = Table(
    "staged_command",
    metadata,
    _id_column(),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=False),
    Column("domain", String(64), nullable=False),
    Column("operation", String(128), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("command_payload", JSONB(), nullable=False),
    Column("preview_facts", JSONB(), nullable=False),
    Column("status", String(32), nullable=False),
    Column("materialized_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("idempotency_key", name="uq_staged_command_idempotency"),
    CheckConstraint(
        "status in ('staged', 'materialized', 'superseded')",
        name="status",
    ),
)

message = Table(
    "message",
    metadata,
    _id_column(),
    Column(
        "conversation_id",
        UUID(as_uuid=False),
        ForeignKey("conversation.id"),
        nullable=False,
    ),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=True),
    Column("direction", String(32), nullable=False),
    Column("segment_index", Integer(), nullable=True),
    Column("seq", BigInteger(), nullable=True),
    Column(
        "channel_identity_id",
        UUID(as_uuid=False),
        ForeignKey("channel_identity.id"),
        nullable=True,
    ),
    Column("causal_inbound_event_id", String(255), nullable=True),
    Column("text", Text(), nullable=True),
    Column("payload", JSONB(), nullable=False),
    Column("facts_hash", String(128), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("turn_id", "segment_index", name="uq_message_turn_segment"),
    UniqueConstraint(
        "conversation_id",
        "direction",
        "seq",
        name="uq_message_inbound_seq",
    ),
)

inbound_media = Table(
    "inbound_media",
    metadata,
    _id_column(),
    Column("message_id", UUID(as_uuid=False), ForeignKey("message.id"), nullable=False),
    Column("media_type", String(64), nullable=False),
    Column("storage_uri", Text(), nullable=False),
    Column("processing_status", String(64), nullable=False),
    Column("agent_reference", JSONB(), nullable=False),
    _created_at(),
    _updated_at(),
)

output_disposition = Table(
    "output_disposition",
    metadata,
    _id_column(),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=False),
    Column("disposition", String(64), nullable=False),
    Column("reason_code", String(160), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("turn_id", name="uq_output_disposition_turn"),
)

pending_clarification = Table(
    "pending_clarification",
    metadata,
    _id_column(),
    Column(
        "conversation_id",
        UUID(as_uuid=False),
        ForeignKey("conversation.id"),
        nullable=False,
    ),
    Column("unresolved_action_fingerprint", String(255), nullable=False),
    Column("candidates", JSONB(), nullable=False),
    Column("source_input_from_seq", BigInteger(), nullable=False),
    Column("source_input_to_seq", BigInteger(), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("status", String(32), nullable=False),
    Column("consumed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    CheckConstraint(
        "status in ('open', 'consumed', 'expired', 'superseded')",
        name="pending_clarification_status",
    ),
    CheckConstraint(
        "source_input_from_seq <= source_input_to_seq",
        name="pending_clarification_input_window_order",
    ),
)

outbox = Table(
    "outbox",
    metadata,
    _id_column(),
    Column("topic", String(128), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("traceparent", String(55), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("processed_at", DateTime(timezone=True), nullable=True),
    Column("acked_at", DateTime(timezone=True), nullable=True),
    Column("retry_count", Integer(), nullable=False),
    Column("last_error", Text(), nullable=True),
    UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
)

delivery_attempt = Table(
    "delivery_attempt",
    metadata,
    _id_column(),
    Column(
        "route_id", UUID(as_uuid=False), ForeignKey("delivery_route.id"), nullable=False
    ),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=True),
    Column("message_id", UUID(as_uuid=False), ForeignKey("message.id"), nullable=True),
    Column("provider_type", String(64), nullable=False),
    Column("provider_message_id", String(255), nullable=True),
    Column("provider_idempotency_key", String(255), nullable=False),
    Column("status", String(32), nullable=False),
    Column("error_code", String(160), nullable=True),
    Column("delivery_source", String(64), nullable=True),
    Column("delivery_intent", String(255), nullable=True),
    Column("retry_attempt", Integer(), nullable=True),
    Column("traceparent", String(255), nullable=True),
    Column("container", String(255), nullable=True),
    Column("context_token_source", String(64), nullable=True),
    Column("context_token_age_seconds", Integer(), nullable=True),
    Column("latency_ms", Integer(), nullable=True),
    Column("attempted_at", DateTime(timezone=True), nullable=False),
    Column("delivered_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "provider_type",
        "provider_idempotency_key",
        name="uq_delivery_attempt_provider_idempotency",
    ),
)

reminder = Table(
    "reminder",
    metadata,
    _id_column(),
    Column(
        "owner_account_id",
        UUID(as_uuid=False),
        ForeignKey("account.id"),
        nullable=False,
    ),
    Column("content", Text(), nullable=False),
    Column("content_hash", String(128), nullable=False),
    Column("kind", String(64), nullable=False),
    Column("next_fire_at", DateTime(timezone=True), nullable=True),
    Column("recurrence_rule", JSONB(), nullable=False),
    Column("captured_timezone", String(64), nullable=False),
    Column("duration_minutes", Integer(), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("hidden_from_calendar", Boolean(), nullable=False),
    Column(
        "shared_reminder_id",
        UUID(as_uuid=False),
        ForeignKey("shared_reminder.id"),
        nullable=True,
    ),
    _created_at(),
    _updated_at(),
)

reminder_fire = Table(
    "reminder_fire",
    metadata,
    _id_column(),
    Column(
        "reminder_id", UUID(as_uuid=False), ForeignKey("reminder.id"), nullable=False
    ),
    Column("occurrence_key", String(255), nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=False),
    Column("fire_state", String(64), nullable=False),
    Column("delivery_result", String(64), nullable=True),
    Column("handled_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("missed_catch_up", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "reminder_id",
        "occurrence_key",
        name="uq_reminder_fire_occurrence",
    ),
)

friend_link = Table(
    "friend_link",
    metadata,
    _id_column(),
    Column(
        "owner_account_id",
        UUID(as_uuid=False),
        ForeignKey("account.id"),
        nullable=False,
    ),
    Column("token_hash", String(255), nullable=False),
    Column("link_code_hash", String(255), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("reset_at", DateTime(timezone=True), nullable=True),
    Column("disabled_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("token_hash", name="uq_friend_link_token_hash"),
    UniqueConstraint("link_code_hash", name="uq_friend_link_code_hash"),
)

friendship = Table(
    "friendship",
    metadata,
    _id_column(),
    Column(
        "account_low_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False
    ),
    Column(
        "account_high_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False
    ),
    Column("lifecycle", String(32), nullable=False),
    Column("established_at", DateTime(timezone=True), nullable=False),
    Column("removed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    CheckConstraint("account_low_id <> account_high_id", name="friendship_not_self"),
)

shared_reminder = Table(
    "shared_reminder",
    metadata,
    _id_column(),
    Column(
        "creator_account_id",
        UUID(as_uuid=False),
        ForeignKey("account.id"),
        nullable=False,
    ),
    Column("participant_set_hash", String(128), nullable=False),
    Column("title", Text(), nullable=False),
    Column("title_hash", String(128), nullable=False),
    Column("local_trigger_at", DateTime(timezone=False), nullable=False),
    Column("captured_timezone", String(64), nullable=False),
    Column("duration_minutes", Integer(), nullable=False),
    Column("status", String(32), nullable=False),
    Column("cancelled_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
)

recoverable_scheduling_intent = Table(
    "recoverable_scheduling_intent",
    metadata,
    _id_column(),
    Column(
        "conversation_id",
        UUID(as_uuid=False),
        ForeignKey("conversation.id"),
        nullable=False,
    ),
    Column(
        "creator_account_id",
        UUID(as_uuid=False),
        ForeignKey("account.id"),
        nullable=False,
    ),
    Column("operation", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("blocker", String(64), nullable=False),
    Column("title", Text(), nullable=False),
    Column("local_trigger_at", DateTime(timezone=False), nullable=False),
    Column("captured_timezone", String(64), nullable=False),
    Column("duration_minutes", Integer(), nullable=True),
    Column("unresolved_reference_text", Text(), nullable=False),
    Column(
        "source_turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=False
    ),
    Column("source_input_from_seq", BigInteger(), nullable=False),
    Column("source_input_to_seq", BigInteger(), nullable=False),
    Column("source_message_ids", JSONB(), nullable=False),
    Column("facts", JSONB(), nullable=False),
    Column("facts_hash", String(128), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column(
        "consumed_turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=True
    ),
    _created_at(),
    _updated_at(),
    CheckConstraint(
        "operation in ('shared_reminder_create')",
        name="recoverable_operation",
    ),
    CheckConstraint(
        "status in ('open', 'consumed', 'expired', 'superseded')",
        name="recoverable_status",
    ),
    CheckConstraint(
        "blocker in ('unmatched_friend', 'ambiguous_friend')",
        name="recoverable_blocker",
    ),
    CheckConstraint(
        "source_input_from_seq <= source_input_to_seq",
        name="recoverable_input_window_order",
    ),
)

reminder_projection = Table(
    "reminder_projection",
    metadata,
    _id_column(),
    Column(
        "shared_reminder_id",
        UUID(as_uuid=False),
        ForeignKey("shared_reminder.id"),
        nullable=False,
    ),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column(
        "reminder_id", UUID(as_uuid=False), ForeignKey("reminder.id"), nullable=False
    ),
    Column("lifecycle", String(32), nullable=False),
    Column("completion_status", String(64), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "shared_reminder_id",
        "account_id",
        name="uq_reminder_projection_participant",
    ),
)

notification_fact = Table(
    "notification_fact",
    metadata,
    _id_column(),
    Column("type", String(64), nullable=False),
    Column(
        "actor_account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=True
    ),
    Column("object_type", String(64), nullable=False),
    Column("object_id", UUID(as_uuid=False), nullable=False),
    Column("status", String(64), nullable=False),
    Column("facts", JSONB(), nullable=False),
    Column("facts_hash", String(128), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("outbox_id", UUID(as_uuid=False), ForeignKey("outbox.id"), nullable=False),
    _created_at(),
    UniqueConstraint("idempotency_key", name="uq_notification_fact_idempotency"),
)

notification_recipient = Table(
    "notification_recipient",
    metadata,
    _id_column(),
    Column(
        "notification_fact_id",
        UUID(as_uuid=False),
        ForeignKey("notification_fact.id", name="fk_notification_recipient_fact"),
        nullable=False,
    ),
    Column(
        "recipient_account_id",
        UUID(as_uuid=False),
        ForeignKey("account.id"),
        nullable=False,
    ),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=True),
    Column("delivery_state", String(64), nullable=False),
    Column("error_facts", JSONB(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "notification_fact_id",
        "recipient_account_id",
        name="uq_notification_recipient_fact_account",
    ),
)

calendar_import_run = Table(
    "calendar_import_run",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("provider_type", String(64), nullable=False),
    Column("provider_account_id", String(255), nullable=True),
    Column(
        "auth_artifact_id",
        UUID(as_uuid=False),
        ForeignKey("auth_artifact.id"),
        nullable=True,
    ),
    Column("status", String(64), nullable=False),
    Column("imported_count", Integer(), nullable=False),
    Column("skipped_count", Integer(), nullable=False),
    Column("downgraded_count", Integer(), nullable=False),
    Column("failed_count", Integer(), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
)

calendar_import_item = Table(
    "calendar_import_item",
    metadata,
    _id_column(),
    Column(
        "run_id",
        UUID(as_uuid=False),
        ForeignKey("calendar_import_run.id"),
        nullable=False,
    ),
    Column("provider_calendar_id", String(255), nullable=False),
    Column("source_event_id", String(255), nullable=False),
    Column("recurrence_instance_key", String(255), nullable=False),
    Column("status", String(64), nullable=False),
    Column("reason", Text(), nullable=True),
    Column("source_metadata", JSONB(), nullable=False),
    Column(
        "reminder_id", UUID(as_uuid=False), ForeignKey("reminder.id"), nullable=True
    ),
    _created_at(),
    UniqueConstraint(
        "provider_calendar_id",
        "source_event_id",
        "recurrence_instance_key",
        name="uq_calendar_import_item_source_occurrence",
    ),
)

Index(
    "uq_reminder_active_timed_duplicate",
    reminder.c.owner_account_id,
    reminder.c.content_hash,
    reminder.c.next_fire_at,
    unique=True,
    postgresql_where=(
        (reminder.c.lifecycle == "active") & reminder.c.next_fire_at.is_not(None)
    ),
)
Index(
    "uq_reminder_active_no_trigger_duplicate",
    reminder.c.owner_account_id,
    reminder.c.content_hash,
    unique=True,
    postgresql_where=(
        (reminder.c.lifecycle == "active") & reminder.c.next_fire_at.is_(None)
    ),
)
Index(
    "uq_channel_one_active_per_account",
    channel.c.account_id,
    unique=True,
    postgresql_where=channel.c.lifecycle == "active",
)
Index(
    "uq_friendship_one_active_pair",
    friendship.c.account_low_id,
    friendship.c.account_high_id,
    unique=True,
    postgresql_where=friendship.c.lifecycle == "active",
)
Index(
    "uq_shared_reminder_active_duplicate",
    shared_reminder.c.creator_account_id,
    shared_reminder.c.participant_set_hash,
    shared_reminder.c.title_hash,
    shared_reminder.c.local_trigger_at,
    shared_reminder.c.captured_timezone,
    shared_reminder.c.duration_minutes,
    unique=True,
    postgresql_where=shared_reminder.c.status == "active",
)
Index(
    "uq_recoverable_intent_one_open_per_conversation",
    recoverable_scheduling_intent.c.conversation_id,
    unique=True,
    postgresql_where=recoverable_scheduling_intent.c.status == "open",
)
Index(
    "uq_pending_clarification_one_open_per_conversation",
    pending_clarification.c.conversation_id,
    unique=True,
    postgresql_where=pending_clarification.c.status == "open",
)
