from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ParamKeySpec:
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = field(default_factory=tuple)


ParamKeySchema = Mapping[str, Mapping[str, ParamKeySpec]]
RequiredParams = Mapping[str, Mapping[str, tuple[str, ...]]]


PARAM_KEY_SCHEMA: ParamKeySchema = MappingProxyType(
    {
        "calendar_import": MappingProxyType(
            {
                "import": ParamKeySpec(
                    required=("source",),
                    optional=(
                        "account_id",
                        "owner_account_id",
                        "auth_handle",
                        "provider_account_id",
                        "visible_start",
                        "visible_end",
                        "captured_timezone",
                        "auth_artifact_id",
                    ),
                ),
            }
        ),
        "friendship": MappingProxyType(
            {
                "add_via_code": ParamKeySpec(
                    required=("code",),
                    optional=(
                        "account_id",
                        "owner_account_id",
                        "joiner_account_id",
                    ),
                ),
                "get_friend_link": ParamKeySpec(
                    optional=("account_id", "owner_account_id"),
                ),
                "list_friends": ParamKeySpec(
                    optional=("account_id", "owner_account_id"),
                ),
                "remove_friend": ParamKeySpec(
                    required=("friend",),
                    optional=(
                        "account_id",
                        "owner_account_id",
                        "friend_account_id",
                    ),
                ),
            }
        ),
        "reminder": MappingProxyType(
            {
                "batch_create": ParamKeySpec(
                    required=("items",),
                    optional=(
                        "owner_account_id",
                        "account_id",
                        "captured_timezone",
                        "display_timezone",
                    ),
                ),
                "complete": ParamKeySpec(
                    required=("match",),
                    optional=("owner_account_id", "account_id"),
                ),
                "create": ParamKeySpec(
                    required=("content", "time_phrase"),
                    optional=(
                        "owner_account_id",
                        "account_id",
                        "captured_timezone",
                        "display_timezone",
                        "duration_minutes",
                        "kind",
                        "raw_text",
                        "text",
                    ),
                ),
                "delete": ParamKeySpec(
                    required=("match",),
                    optional=("owner_account_id", "account_id"),
                ),
                "list": ParamKeySpec(
                    optional=(
                        "owner_account_id",
                        "account_id",
                        "keyword",
                        "lifecycle",
                        "status",
                        "kind",
                        "reminder_type",
                        "date_phrase",
                        "trigger_after",
                        "trigger_before",
                        "captured_timezone",
                        "display_timezone",
                    ),
                ),
                "update": ParamKeySpec(
                    required=("match",),
                    optional=(
                        "owner_account_id",
                        "account_id",
                        "content",
                        "time_phrase",
                        "captured_timezone",
                        "display_timezone",
                        "duration_minutes",
                        "raw_text",
                        "text",
                    ),
                ),
            }
        ),
        "settings": MappingProxyType(
            {
                "set_timezone": ParamKeySpec(
                    required=("timezone_text",),
                    optional=("account_id", "owner_account_id"),
                ),
                "toggle_memory": ParamKeySpec(
                    required=("enabled",),
                    optional=("account_id", "owner_account_id"),
                ),
                "toggle_proactive": ParamKeySpec(
                    required=("enabled",),
                    optional=("account_id", "owner_account_id"),
                ),
                "update_settings": ParamKeySpec(
                    required=("preference",),
                    optional=(
                        "account_id",
                        "owner_account_id",
                        "fields",
                        "default_timezone",
                        "assistant_name",
                        "user_address_name",
                        "persona",
                        "background",
                        "speaking_style",
                        "extra_rules",
                        "proactive_enabled",
                        "memory_enabled",
                    ),
                ),
            }
        ),
        "social_scheduling": MappingProxyType(
            {
                "availability_query": ParamKeySpec(
                    required=("participant",),
                    optional=(
                        "account_id",
                        "owner_account_id",
                        "creator_account_id",
                        "requester_account_id",
                        "date_phrase",
                        "local_start",
                        "local_end",
                        "captured_timezone",
                        "requester_timezone",
                    ),
                ),
                "cancel_shared_reminder": ParamKeySpec(
                    required=("participant",),
                    optional=(
                        "match",
                        "account_id",
                        "owner_account_id",
                        "creator_account_id",
                    ),
                ),
                "create_shared_reminder": ParamKeySpec(
                    required=("participant", "content", "time_phrase"),
                    optional=(
                        "creator_account_id",
                        "account_id",
                        "owner_account_id",
                        "captured_timezone",
                        "requester_timezone",
                        "duration_minutes",
                        "raw_text",
                        "text",
                        "local_trigger_at",
                        "trigger_time",
                        "title",
                    ),
                ),
                "update_shared_reminder": ParamKeySpec(
                    optional=(
                        "account_id",
                        "owner_account_id",
                        "creator_account_id",
                        "participant",
                        "match",
                        "shared_reminder_id",
                        "captured_timezone",
                        "requester_timezone",
                        "duration_minutes",
                        "local_trigger_at",
                        "trigger_time",
                        "time_phrase",
                        "raw_text",
                        "text",
                    ),
                ),
                "list_shared": ParamKeySpec(
                    optional=(
                        "account_id",
                        "owner_account_id",
                        "creator_account_id",
                        "participant",
                    ),
                ),
            }
        ),
    }
)


def allowed_actions_from_schema(
    schema: ParamKeySchema = PARAM_KEY_SCHEMA,
) -> dict[str, frozenset[str]]:
    return {
        domain: frozenset(operations.keys()) for domain, operations in schema.items()
    }


def required_params_by_operation(
    schema: ParamKeySchema = PARAM_KEY_SCHEMA,
) -> dict[str, dict[str, tuple[str, ...]]]:
    return {
        domain: {operation: spec.required for operation, spec in operations.items()}
        for domain, operations in schema.items()
    }


def param_key_schema_payload(
    schema: ParamKeySchema = PARAM_KEY_SCHEMA,
) -> dict[str, dict[str, dict[str, list[str]]]]:
    return {
        domain: {
            operation: {
                "required": list(spec.required),
                "optional": list(spec.optional),
            }
            for operation, spec in operations.items()
        }
        for domain, operations in schema.items()
    }
