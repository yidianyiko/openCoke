from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260529_0001"
down_revision = None
branch_labels = None
depends_on = None


def _id_column() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False)


def _pk(table_name: str) -> sa.PrimaryKeyConstraint:
    return sa.PrimaryKeyConstraint("id", name=f"pk_{table_name}")


def _fk(
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str = "id",
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column_name],
        [f"{referred_table}.{referred_column}"],
        name=f"fk_{table_name}_{column_name}_{referred_table}",
    )


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "account",
        _id_column(),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("default_timezone", sa.String(length=64), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("account"),
        sa.CheckConstraint("origin in ('web_first', 'messaging_first')", name=op.f("ck_account_account_origin")),
        sa.CheckConstraint("lifecycle in ('active', 'disabled')", name=op.f("ck_account_account_lifecycle")),
    )
    op.create_table(
        "agent_settings",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("assistant_name", sa.String(length=128), nullable=False),
        sa.Column("user_address_name", sa.String(length=128), nullable=True),
        sa.Column("persona", sa.Text(), nullable=True),
        sa.Column("background", sa.Text(), nullable=True),
        sa.Column("speaking_style", sa.Text(), nullable=True),
        sa.Column("extra_rules", sa.Text(), nullable=True),
        sa.Column("proactive_enabled", sa.Boolean(), nullable=False),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("agent_settings"),
        _fk("agent_settings", "account_id", "account"),
        sa.UniqueConstraint("account_id", name="uq_agent_settings_account"),
    )
    op.create_table(
        "user_profile",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("real_name", sa.String(length=160), nullable=True),
        sa.Column("nickname", sa.String(length=160), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("relationship_description", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("user_profile"),
        _fk("user_profile", "account_id", "account"),
        sa.UniqueConstraint("account_id", name="uq_user_profile_account"),
    )
    op.create_table(
        "account_activation",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("first_inbound_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activation_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_guidance_sent_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("account_activation"),
        _fk("account_activation", "account_id", "account"),
        sa.UniqueConstraint("account_id", name="uq_account_activation_account"),
    )
    op.create_table(
        "account_access",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("email_verification_state", sa.String(length=32), nullable=False),
        sa.Column("subscription_state", sa.String(length=32), nullable=False),
        sa.Column("suspension_state", sa.String(length=32), nullable=False),
        sa.Column("access_allowed", sa.Boolean(), nullable=False),
        sa.Column("denial_reason", sa.String(length=160), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("account_access"),
        _fk("account_access", "account_id", "account"),
        sa.UniqueConstraint("account_id", name="uq_account_access_account"),
    )
    op.create_table(
        "credential",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_required", sa.Boolean(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("credential"),
        _fk("credential", "account_id", "account"),
        sa.UniqueConstraint("account_id", name="uq_credential_account"),
        sa.UniqueConstraint("email", name="uq_credential_email"),
    )
    op.create_table(
        "session",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("session"),
        _fk("session", "account_id", "account"),
        sa.UniqueConstraint("token_hash", name="uq_session_token_hash"),
    )
    op.create_table(
        "channel_identity",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("is_account_anchor", sa.Boolean(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("channel_identity"),
        _fk("channel_identity", "account_id", "account"),
        sa.UniqueConstraint("provider_type", "provider_subject", name="uq_channel_identity_provider_subject"),
    )
    op.create_table(
        "auth_artifact",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("target_account_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("delivery", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("browser_session", sa.String(length=255), nullable=True),
        sa.Column("continuation", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_state", sa.String(length=64), nullable=False),
        sa.Column("resend_count", sa.Integer(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("auth_artifact"),
        _fk("auth_artifact", "account_id", "account"),
        _fk("auth_artifact", "target_account_id", "account"),
        sa.UniqueConstraint("token_hash", name="uq_auth_artifact_token_hash"),
    )
    op.create_table(
        "channel",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("channel_identity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("connection_state", sa.String(length=64), nullable=False),
        sa.Column("removable", sa.Boolean(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("channel"),
        _fk("channel", "account_id", "account"),
        _fk("channel", "channel_identity_id", "channel_identity"),
    )
    op.create_table(
        "delivery_route",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("provider_address", sa.String(length=255), nullable=False),
        sa.Column("route_key", sa.String(length=255), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("delivery_route"),
        _fk("delivery_route", "account_id", "account"),
        _fk("delivery_route", "channel_id", "channel"),
        sa.UniqueConstraint("route_key", name="uq_delivery_route_route_key"),
    )
    op.create_table(
        "conversation",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("latest_inbound_seq", sa.BigInteger(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("conversation"),
        _fk("conversation", "account_id", "account"),
        sa.UniqueConstraint("account_id", name="uq_conversation_account"),
    )
    op.create_table(
        "turn",
        _id_column(),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("trigger_id", sa.String(length=255), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("based_on_inbound_seq", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("turn"),
        _fk("turn", "conversation_id", "conversation"),
        sa.UniqueConstraint("trigger_id", name="uq_turn_trigger_id"),
    )
    op.create_table(
        "message",
        _id_column(),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=True),
        sa.Column("seq", sa.BigInteger(), nullable=True),
        sa.Column("channel_identity_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("causal_inbound_event_id", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("facts_hash", sa.String(length=128), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("message"),
        _fk("message", "conversation_id", "conversation"),
        _fk("message", "turn_id", "turn"),
        _fk("message", "channel_identity_id", "channel_identity"),
        sa.UniqueConstraint("turn_id", "segment_index", name="uq_message_turn_segment"),
    )
    op.create_table(
        "inbound_media",
        _id_column(),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("processing_status", sa.String(length=64), nullable=False),
        sa.Column("agent_reference", postgresql.JSONB(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("inbound_media"),
        _fk("inbound_media", "message_id", "message"),
    )
    op.create_table(
        "output_disposition",
        _id_column(),
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("disposition", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=160), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("output_disposition"),
        _fk("output_disposition", "turn_id", "turn"),
        sa.UniqueConstraint("turn_id", name="uq_output_disposition_turn"),
    )
    op.create_table(
        "outbox",
        _id_column(),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("traceparent", sa.String(length=55), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        _pk("outbox"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
    )
    op.create_table(
        "delivery_attempt",
        _id_column(),
        sa.Column("route_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("provider_idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("delivery_attempt"),
        _fk("delivery_attempt", "route_id", "delivery_route"),
        _fk("delivery_attempt", "turn_id", "turn"),
        _fk("delivery_attempt", "message_id", "message"),
        sa.UniqueConstraint("provider_type", "provider_idempotency_key", name="uq_delivery_attempt_provider_idempotency"),
    )
    op.create_table(
        "friend_link",
        _id_column(),
        sa.Column("owner_account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("link_code_hash", sa.String(length=255), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("friend_link"),
        _fk("friend_link", "owner_account_id", "account"),
        sa.UniqueConstraint("token_hash", name="uq_friend_link_token_hash"),
        sa.UniqueConstraint("link_code_hash", name="uq_friend_link_code_hash"),
    )
    op.create_table(
        "friendship",
        _id_column(),
        sa.Column("account_low_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("account_high_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("established_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("friendship"),
        _fk("friendship", "account_low_id", "account"),
        _fk("friendship", "account_high_id", "account"),
        sa.CheckConstraint("account_low_id <> account_high_id", name=op.f("ck_friendship_friendship_not_self")),
    )
    op.create_table(
        "shared_reminder",
        _id_column(),
        sa.Column("creator_account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("participant_set_hash", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_hash", sa.String(length=128), nullable=False),
        sa.Column("local_trigger_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("captured_timezone", sa.String(length=64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("shared_reminder"),
        _fk("shared_reminder", "creator_account_id", "account"),
    )
    op.create_table(
        "reminder",
        _id_column(),
        sa.Column("owner_account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recurrence_rule", postgresql.JSONB(), nullable=False),
        sa.Column("captured_timezone", sa.String(length=64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("hidden_from_calendar", sa.Boolean(), nullable=False),
        sa.Column("shared_reminder_id", postgresql.UUID(as_uuid=False), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("reminder"),
        _fk("reminder", "owner_account_id", "account"),
        _fk("reminder", "shared_reminder_id", "shared_reminder"),
    )
    op.create_table(
        "reminder_fire",
        _id_column(),
        sa.Column("reminder_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("occurrence_key", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fire_state", sa.String(length=64), nullable=False),
        sa.Column("delivery_result", sa.String(length=64), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("missed_catch_up", sa.Boolean(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("reminder_fire"),
        _fk("reminder_fire", "reminder_id", "reminder"),
        sa.UniqueConstraint("reminder_id", "occurrence_key", name="uq_reminder_fire_occurrence"),
    )
    op.create_table(
        "reminder_projection",
        _id_column(),
        sa.Column("shared_reminder_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("reminder_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("completion_status", sa.String(length=64), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("reminder_projection"),
        _fk("reminder_projection", "shared_reminder_id", "shared_reminder"),
        _fk("reminder_projection", "account_id", "account"),
        _fk("reminder_projection", "reminder_id", "reminder"),
        sa.UniqueConstraint("shared_reminder_id", "account_id", name="uq_reminder_projection_participant"),
    )
    op.create_table(
        "notification_fact",
        _id_column(),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("actor_account_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("facts_hash", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("outbox_id", postgresql.UUID(as_uuid=False), nullable=False),
        _created_at(),
        _pk("notification_fact"),
        _fk("notification_fact", "actor_account_id", "account"),
        _fk("notification_fact", "outbox_id", "outbox"),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_fact_idempotency"),
    )
    op.create_table(
        "notification_recipient",
        _id_column(),
        sa.Column("notification_fact_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("recipient_account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("delivery_state", sa.String(length=64), nullable=False),
        sa.Column("error_facts", postgresql.JSONB(), nullable=False),
        _created_at(),
        _updated_at(),
        _pk("notification_recipient"),
        sa.ForeignKeyConstraint(
            ["notification_fact_id"],
            ["notification_fact.id"],
            name="fk_notification_recipient_fact",
        ),
        _fk("notification_recipient", "recipient_account_id", "account"),
        _fk("notification_recipient", "turn_id", "turn"),
        sa.UniqueConstraint("notification_fact_id", "recipient_account_id", name="uq_notification_recipient_fact_account"),
    )
    op.create_table(
        "calendar_import_run",
        _id_column(),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=True),
        sa.Column("auth_artifact_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("downgraded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _pk("calendar_import_run"),
        _fk("calendar_import_run", "account_id", "account"),
        _fk("calendar_import_run", "auth_artifact_id", "auth_artifact"),
    )
    op.create_table(
        "calendar_import_item",
        _id_column(),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("provider_calendar_id", sa.String(length=255), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=False),
        sa.Column("recurrence_instance_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("reminder_id", postgresql.UUID(as_uuid=False), nullable=True),
        _created_at(),
        _pk("calendar_import_item"),
        _fk("calendar_import_item", "run_id", "calendar_import_run"),
        _fk("calendar_import_item", "reminder_id", "reminder"),
        sa.UniqueConstraint(
            "provider_calendar_id",
            "source_event_id",
            "recurrence_instance_key",
            name="uq_calendar_import_item_source_occurrence",
        ),
    )
    op.create_index(
        "uq_channel_one_active_per_account",
        "channel",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle = 'active'"),
    )
    op.create_index(
        "uq_friendship_one_active_pair",
        "friendship",
        ["account_low_id", "account_high_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle = 'active'"),
    )
    op.create_index(
        "uq_shared_reminder_active_duplicate",
        "shared_reminder",
        [
            "creator_account_id",
            "participant_set_hash",
            "title_hash",
            "local_trigger_at",
            "captured_timezone",
            "duration_minutes",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_reminder_active_timed_duplicate",
        "reminder",
        ["owner_account_id", "content_hash", "next_fire_at"],
        unique=True,
        postgresql_where=sa.text("lifecycle = 'active' AND next_fire_at IS NOT NULL"),
    )
    op.create_index(
        "uq_reminder_active_no_trigger_duplicate",
        "reminder",
        ["owner_account_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("lifecycle = 'active' AND next_fire_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_reminder_active_no_trigger_duplicate", table_name="reminder")
    op.drop_index("uq_reminder_active_timed_duplicate", table_name="reminder")
    op.drop_index("uq_shared_reminder_active_duplicate", table_name="shared_reminder")
    op.drop_index("uq_friendship_one_active_pair", table_name="friendship")
    op.drop_index("uq_channel_one_active_per_account", table_name="channel")
    op.drop_table("calendar_import_item")
    op.drop_table("calendar_import_run")
    op.drop_table("notification_recipient")
    op.drop_table("notification_fact")
    op.drop_table("reminder_projection")
    op.drop_table("reminder_fire")
    op.drop_table("reminder")
    op.drop_table("shared_reminder")
    op.drop_table("friendship")
    op.drop_table("friend_link")
    op.drop_table("delivery_attempt")
    op.drop_table("outbox")
    op.drop_table("output_disposition")
    op.drop_table("inbound_media")
    op.drop_table("message")
    op.drop_table("turn")
    op.drop_table("conversation")
    op.drop_table("delivery_route")
    op.drop_table("channel")
    op.drop_table("auth_artifact")
    op.drop_table("channel_identity")
    op.drop_table("session")
    op.drop_table("credential")
    op.drop_table("account_access")
    op.drop_table("account_activation")
    op.drop_table("user_profile")
    op.drop_table("agent_settings")
    op.drop_table("account")
