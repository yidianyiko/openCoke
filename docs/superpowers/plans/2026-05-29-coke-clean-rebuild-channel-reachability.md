# Coke Clean Rebuild ChannelReachability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the clean-rebuild ChannelReachability domain, provider adapter contract, provider webhook ingress, and thin channel JSON routes without integrating real provider networks or ConversationRuntime processing.

**Architecture:** ChannelReachability owns only `channel`, `delivery_route`, and `delivery_attempt`; it reads IdentityAccess-owned `channel_identity` through service methods and never writes that table. The first implementation uses frozen dataclasses plus a protocol-friendly in-memory repository so lifecycle, route resolution, route retirement, and provider idempotency are locked down before a SQLAlchemy repository slice maps the same boundary to the existing clean schema. Provider adapters are edge modules behind one canonical protocol, and webhook routes return structured accepted/identity facts only.

**Tech Stack:** Python 3.12, Flask blueprints, dataclasses, typing protocols, pytest, existing `coke` backend package, existing clean schema tables in `coke/schema.py`.

---

**Plan Status:** ready for execution
**Status Date:** 2026-05-29
**Parent Plan:** `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`, Task 5: ChannelReachability And Provider Adapter Contract

**Source Specs:**
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`

**Freshness Check:** Before executing, compare this plan against current `main`, `docs/ARCHITECTURE.md`, `docs/design-docs/coke-working-contract.md`, `docs/product-specs/FEATURE_TREE.md`, `coke/schema.py`, and `coke/domains/identity_access/service.py`.

## Scope

In scope:

- Channel lifecycle for one active personal channel per account.
- Channel states: `not_connected`, `connecting`, `connected`, `connection_failed`, `reconnection_required`, and `removed`.
- Active channel ownership for `channel`; route ownership for `delivery_route`; provider send evidence ownership for `delivery_attempt`.
- Read-only use of IdentityAccess channel identity methods.
- Account access gate for channel connection entry and connection actions through `IdentityAccessService.check_access_for_action(account_id, "connect_channel")`.
- Removal gate through `IdentityAccessService.can_remove_channel_identity(account_id, channel_identity_id)`.
- Provider adapter protocol with `provider_type`, `normalize_inbound(payload) -> NormalizedInbound`, and `send_text(route, text, idempotency_key) -> DeliveryAttemptResult`.
- Minimal contract-preserving adapters for `whatsapp_evolution`, `wechat_personal`, `wechat_ecloud`, and `linq`.
- Product personal-channel allowlist for ChannelReachability creation and webhook binding: only `whatsapp_evolution` and `wechat_personal`.
- Retained non-product provider adapters `wechat_ecloud` and `linq` remain behind the provider protocol but cannot be connected or auto-bound as personal channels in this slice.
- Provider-edge send idempotency by `provider_type + provider_idempotency_key`.
- Provider webhook ingress on canonical routes `/webhooks/whatsapp/evolution`, `/webhooks/wechat/personal`, `/webhooks/wechat/ecloud`, and `/webhooks/linq`; only product personal-channel providers may bind/connect.
- Thin Flask channel routes for status, create, connect, poll, remove, retry, and resolve route.
- Internal/domain `ChannelReachabilityService.send_text(...)` for future runtime-owned delivery evidence; no public raw text send route in this slice.

Out of scope:

- SQLAlchemy repository implementation for ChannelReachability.
- Alembic schema changes.
- Provider network integration.
- ConversationRuntime, Turn processing, assistant prose rendering, reminders, notifications, web UI, worker queues, and deployment.
- Public API route for arbitrary raw text send.
- Multiple active personal channels per account.
- Account merge, unlink, heuristic identity matching, legacy route compatibility, and fallback parsers.

## File Structure

- Create `coke/domains/channel_reachability/__init__.py`: exports public ChannelReachability service/model classes.
- Create `coke/domains/channel_reachability/models.py`: dataclasses, literal constants, result objects, and domain exceptions for channels, routes, attempts, provider results, and inbound events.
- Create `coke/domains/channel_reachability/repository.py`: protocol-style repository boundary plus in-memory repository for unit tests.
- Create `coke/domains/channel_reachability/service.py`: application/domain service for channel lifecycle, route resolution, removal, retry, reconnection, webhook identity binding, and idempotent send attempts.
- Create `coke/providers/base.py`: canonical provider adapter protocol and provider registry helper.
- Create `coke/providers/whatsapp_evolution.py`: shared WhatsApp adapter fake using the canonical contract.
- Create `coke/providers/wechat_personal.py`: personal WeChat adapter fake using the canonical contract.
- Create `coke/providers/wechat_ecloud.py`: eCloud WeChat adapter fake using the canonical contract.
- Create `coke/providers/linq.py`: SMS/Linq adapter fake using the canonical contract.
- Create `coke/api/channel_routes.py`: thin JSON blueprint for channel status and actions.
- Create `coke/api/provider_webhooks.py`: thin JSON blueprint for provider inbound normalization and identity binding.
- Modify `coke/app.py`: optionally register channel and provider webhook blueprints when a `channel_reachability_service` is passed.
- Modify `coke/domains/identity_access/service.py`: add a read-only `get_owned_channel_identity(account_id, channel_identity_id)` method if it is absent in the executing worktree.
- Test `tests/unit/coke/channel_reachability/test_provider_adapters.py`: provider protocol and normalization tests.
- Test `tests/unit/coke/channel_reachability/test_channel_reachability_service.py`: lifecycle, removal, retry, route resolution, idempotency, send evidence, and no `channel_identity` write tests.
- Test `tests/unit/coke/channel_reachability/test_channel_routes.py`: thin Flask route adapter tests and JSON error shape tests.
- Test `tests/unit/coke/channel_reachability/test_provider_webhooks.py`: provider webhook structured response and IdentityAccess binding tests.

## Execution Preflight

- [ ] **Step 1: Enter the requested worktree**

Run:

```bash
cd /data/projects/coke/.worktrees/clean-rebuild-exec
git status --short --branch
```

Expected: branch is `clean-rebuild-exec`. Any unrelated changes remain untouched.

- [ ] **Step 2: Select the Python command**

Run:

```bash
python_cmd=".venv/bin/python"
if [[ ! -x "$python_cmd" ]]; then
  python_cmd="python3"
fi
printf '%s\n' "$python_cmd"
```

Expected: prints `.venv/bin/python` when the local virtualenv exists, otherwise `python3`.

- [ ] **Step 3: Run diff-aware routing before edits**

Run:

```bash
slice_base=$(git rev-parse HEAD)
printf 'slice_base=%s\n' "$slice_base"
zsh scripts/suggest-verification --base "$slice_base"
```

Expected: prints the pre-edit commit SHA and output includes backend or repo-OS surfaces. Keep `slice_base` and the command output in the handoff notes for the implementation session.

- [ ] **Step 4: Verify current backend foundation before edits**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/test_backend_foundation.py tests/unit/coke/test_clean_schema_contract.py tests/unit/coke/identity_access -v
```

Expected: all selected tests pass before ChannelReachability files are added.

## Task 1: Provider Adapter Contract And Provider Fakes

**Files:**
- Create: `coke/providers/base.py`
- Create: `coke/providers/whatsapp_evolution.py`
- Create: `coke/providers/wechat_personal.py`
- Create: `coke/providers/wechat_ecloud.py`
- Create: `coke/providers/linq.py`
- Test: `tests/unit/coke/channel_reachability/test_provider_adapters.py`

- [ ] **Step 1: Write the failing provider contract tests**

Create `tests/unit/coke/channel_reachability/test_provider_adapters.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryRoute,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
    RETAINED_PROVIDER_TYPES,
)
from coke.providers.base import provider_registry
from coke.providers.linq import LinqAdapter
from coke.providers.wechat_ecloud import WeChatECloudAdapter
from coke.providers.wechat_personal import WeChatPersonalAdapter
from coke.providers.whatsapp_evolution import WhatsAppEvolutionAdapter


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("adapter", "payload", "provider_subject", "text", "raw_event_id", "pairing_code"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "pair code ABC123",
                "pairing_code": "ABC123",
            },
            "whatsapp:+15555550123",
            "pair code ABC123",
            "wa_msg_1",
            "ABC123",
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {
                "message_id": "wx_msg_1",
                "wxid": "wxid_alice",
                "text": "hello",
                "pairing_code": "WXPAIR",
            },
            "wxid_alice",
            "hello",
            "wx_msg_1",
            "WXPAIR",
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {
                "msg_id": "gewe_msg_1",
                "sender_id": "gewe_alice",
                "content": "hello",
            },
            "gewe_alice",
            "hello",
            "gewe_msg_1",
            None,
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {
                "id": "sms_msg_1",
                "from": "+15555550123",
                "body": "hello",
            },
            "+15555550123",
            "hello",
            "sms_msg_1",
            None,
        ),
    ],
)
def test_provider_adapters_normalize_inbound_payloads(
    adapter,
    payload,
    provider_subject,
    text,
    raw_event_id,
    pairing_code,
):
    inbound = adapter.normalize_inbound(payload)

    assert inbound.provider_type == adapter.provider_type
    assert inbound.provider_subject == provider_subject
    assert inbound.text == text
    assert inbound.raw_event_id == raw_event_id
    assert inbound.pairing_code == pairing_code
    assert inbound.received_at == NOW
    assert inbound.payload is not payload


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {
                "message_id": "wa_msg_blank",
                "sender": "whatsapp:+15555550123",
                "text": "",
            },
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {
                "message_id": "wx_msg_blank",
                "wxid": "wxid_alice",
                "text": "   ",
            },
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {
                "msg_id": "gewe_msg_blank",
                "sender_id": "gewe_alice",
                "content": "",
            },
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {
                "id": "sms_msg_blank",
                "from": "+15555550123",
                "body": "   ",
            },
        ),
    ],
)
def test_provider_adapters_normalize_explicit_blank_text(adapter, payload):
    inbound = adapter.normalize_inbound(payload)

    assert inbound.text == ""


def test_normalized_inbound_payload_is_recursively_immutable_copy():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)
    payload = {
        "message_id": "wa_msg_1",
        "sender": "whatsapp:+15555550123",
        "text": "hello",
        "metadata": {
            "headers": {"x-provider": "evolution"},
            "attachments": [{"id": "att_1", "labels": ["receipt", "image"]}],
        },
    }

    inbound = adapter.normalize_inbound(payload)
    payload["text"] = "mutated"
    payload["metadata"]["headers"]["x-provider"] = "mutated"
    payload["metadata"]["attachments"][0]["labels"].append("mutated")

    assert inbound.text == "hello"
    assert inbound.payload["text"] == "hello"
    assert inbound.payload["metadata"]["headers"]["x-provider"] == "evolution"
    assert inbound.payload["metadata"]["attachments"][0]["labels"] == ("receipt", "image")
    with pytest.raises(TypeError):
        inbound.payload["text"] = "corrupt"
    with pytest.raises(TypeError):
        inbound.payload["metadata"]["headers"]["x-provider"] = "corrupt"
    with pytest.raises(TypeError):
        inbound.payload["metadata"]["attachments"][0]["id"] = "corrupt"
    with pytest.raises(AttributeError):
        inbound.payload["metadata"]["attachments"].append({"id": "corrupt"})


def test_provider_adapters_reject_non_json_payload_evidence_values():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)

    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "hello",
                "metadata": {"raw_bytes": b"not-json"},
            }
        )

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": "whatsapp_evolution",
        "field": "payload.metadata.raw_bytes",
        "reason": "non_json_payload_value",
    }


def test_provider_adapters_reject_tuple_payload_evidence_values():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)

    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "hello",
                "metadata": {"attachments": ("att_1",)},
            }
        )

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": "whatsapp_evolution",
        "field": "payload.metadata.attachments",
        "reason": "non_json_payload_value",
    }


@pytest.mark.parametrize(
    ("adapter", "payload", "missing_field"),
    [
        (WhatsAppEvolutionAdapter(now=lambda: NOW), {"sender": "whatsapp:+15555550123"}, "message_id"),
        (WeChatPersonalAdapter(now=lambda: NOW), {"message_id": "wx_msg_1"}, "wxid"),
        (WeChatECloudAdapter(now=lambda: NOW), {"msg_id": "gewe_msg_1"}, "sender_id"),
        (LinqAdapter(now=lambda: NOW), {"id": "sms_msg_1"}, "from"),
    ],
)
def test_provider_adapters_reject_missing_required_fields(adapter, payload, missing_field):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": missing_field,
        "reason": "missing_required_field",
    }


@pytest.mark.parametrize(
    ("adapter", "payload", "field"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {"message_id": "wa_msg_1", "sender": "", "text": "hello"},
            "sender",
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {"message_id": "wx_msg_1", "wxid": None, "text": "hello"},
            "wxid",
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {"msg_id": "gewe_msg_1", "sender_id": [], "content": "hello"},
            "sender_id",
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {"id": "sms_msg_1", "from": {}, "body": "hello"},
            "from",
        ),
    ],
)
def test_provider_adapters_reject_malformed_required_fields(adapter, payload, field):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": field,
        "reason": "invalid_required_field",
    }


@pytest.mark.parametrize(
    ("adapter", "payload", "field"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {"message_id": True, "sender": "whatsapp:+15555550123", "text": "hello"},
            "message_id",
        ),
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {"message_id": "wa_msg_1", "sender": False, "text": "hello"},
            "sender",
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {"message_id": "wx_msg_1", "wxid": True, "text": "hello"},
            "wxid",
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {"msg_id": "gewe_msg_1", "sender_id": False, "content": "hello"},
            "sender_id",
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {"id": "sms_msg_1", "from": True, "body": "hello"},
            "from",
        ),
    ],
)
def test_provider_adapters_reject_boolean_required_fields(adapter, payload, field):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": field,
        "reason": "invalid_required_field",
    }


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            {
                "message_id": "wa_msg_1",
                "sender": "whatsapp:+15555550123",
                "text": "hello",
                "pairing_code": ["ABC123"],
            },
        ),
        (
            WeChatPersonalAdapter(now=lambda: NOW),
            {
                "message_id": "wx_msg_1",
                "wxid": "wxid_alice",
                "text": "hello",
                "pairing_code": {"code": "WXPAIR"},
            },
        ),
        (
            WeChatECloudAdapter(now=lambda: NOW),
            {
                "msg_id": "gewe_msg_1",
                "sender_id": "gewe_alice",
                "content": "hello",
                "pairing_code": ("ECLOUDPAIR",),
            },
        ),
        (
            LinqAdapter(now=lambda: NOW),
            {
                "id": "sms_msg_1",
                "from": "+15555550123",
                "body": "hello",
                "pairing_code": {"code": "SMSPAIR"},
            },
        ),
    ],
)
def test_provider_adapters_reject_malformed_pairing_code(adapter, payload):
    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        adapter.normalize_inbound(payload)

    assert exc_info.value.fact == {
        "type": "invalid_provider_payload",
        "provider_type": adapter.provider_type,
        "field": "pairing_code",
        "reason": "invalid_optional_field",
    }


def test_registry_contains_all_retained_provider_adapters():
    registry = provider_registry(
        [
            WhatsAppEvolutionAdapter(now=lambda: NOW),
            WeChatPersonalAdapter(now=lambda: NOW),
            WeChatECloudAdapter(now=lambda: NOW),
            LinqAdapter(now=lambda: NOW),
        ]
    )

    assert set(registry) == {
        "whatsapp_evolution",
        "wechat_personal",
        "wechat_ecloud",
        "linq",
    }
    assert RETAINED_PROVIDER_TYPES == {
        "whatsapp_evolution",
        "wechat_personal",
        "wechat_ecloud",
        "linq",
    }
    assert PRODUCT_CHANNEL_PROVIDER_TYPES == {
        "whatsapp_evolution",
        "wechat_personal",
    }


def test_fake_send_text_returns_provider_attempt_result():
    adapter = WhatsAppEvolutionAdapter(now=lambda: NOW)
    route = DeliveryRoute(
        id="route_1",
        account_id="acct_1",
        channel_id="channel_1",
        provider_type="whatsapp_evolution",
        provider_address="whatsapp:+15555550123",
        route_key="whatsapp_evolution:whatsapp:+15555550123",
        lifecycle="active",
        created_at=NOW,
        updated_at=NOW,
    )

    result = adapter.send_text(
        route=route,
        text="hello",
        idempotency_key="send_1",
    )

    assert result.status == "sent"
    assert result.provider_message_id == "whatsapp_evolution:send_1"
    assert result.error_code is None
    assert result.delivered_at is None
```

- [ ] **Step 2: Run the provider tests to verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py -v
```

Expected: fail during import because `coke.providers.base` and `coke.domains.channel_reachability.models` do not exist.

- [ ] **Step 3: Add provider-facing models**

Create `coke/domains/channel_reachability/__init__.py`:

```python
from coke.domains.channel_reachability.models import (
    Channel,
    ChannelReachabilityError,
    DeliveryAttempt,
    DeliveryAttemptResult,
    DeliveryRoute,
    ImmutableJsonValue,
    NormalizedInbound,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
    RETAINED_PROVIDER_TYPES,
)

__all__ = [
    "Channel",
    "ChannelReachabilityError",
    "DeliveryAttempt",
    "DeliveryAttemptResult",
    "DeliveryRoute",
    "ImmutableJsonValue",
    "NormalizedInbound",
    "PRODUCT_CHANNEL_PROVIDER_TYPES",
    "RETAINED_PROVIDER_TYPES",
]
```

Create `coke/domains/channel_reachability/models.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeAlias


ChannelConnectionState = Literal[
    "not_connected",
    "connecting",
    "connected",
    "connection_failed",
    "reconnection_required",
    "removed",
]
ChannelLifecycle = Literal["active", "removed"]
DeliveryRouteLifecycle = Literal["active", "removed"]
DeliveryAttemptStatus = Literal["sent", "delivered", "failed"]

PRODUCT_CHANNEL_PROVIDER_TYPES = frozenset({"whatsapp_evolution", "wechat_personal"})
RETAINED_PROVIDER_TYPES = frozenset(
    {
        "whatsapp_evolution",
        "wechat_personal",
        "wechat_ecloud",
        "linq",
    }
)
ImmutableJsonValue: TypeAlias = (
    str | int | float | bool | None | tuple["ImmutableJsonValue", ...] | Mapping[str, "ImmutableJsonValue"]
)


class ChannelReachabilityError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        fact: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.fact = fact
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class Channel:
    id: str
    account_id: str
    channel_identity_id: str
    provider_type: str
    lifecycle: ChannelLifecycle
    connection_state: ChannelConnectionState
    removable: bool
    connected_at: datetime | None
    removed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryRoute:
    id: str
    account_id: str
    channel_id: str
    provider_type: str
    provider_address: str
    route_key: str
    lifecycle: DeliveryRouteLifecycle
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    id: str
    route_id: str
    provider_type: str
    provider_idempotency_key: str
    status: DeliveryAttemptStatus
    provider_message_id: str | None
    error_code: str | None
    attempted_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    turn_id: str | None = None
    message_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryAttemptResult:
    status: DeliveryAttemptStatus
    provider_message_id: str | None
    error_code: str | None
    delivered_at: datetime | None


@dataclass(frozen=True, slots=True)
class NormalizedInbound:
    provider_type: str
    provider_subject: str
    text: str
    raw_event_id: str
    received_at: datetime
    pairing_code: str | None = None
    payload: Mapping[str, ImmutableJsonValue] | None = None
```

`NormalizedInbound.payload` is provider evidence, not a mutable working object. Provider adapters must set it to an immutable mapping whose nested mappings are immutable, whose nested JSON arrays are tuples, and whose scalar values are JSON scalars. The implementation helper below rejects non-JSON evidence values instead of storing opaque mutable objects; tuple input is rejected because provider webhook ingress is JSON-shaped, even though accepted JSON arrays are frozen as tuples internally.

- [ ] **Step 4: Add the provider protocol and fakes**

Create `coke/providers/base.py`:

```python
from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from types import MappingProxyType
from typing import Protocol

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    ImmutableJsonValue,
    NormalizedInbound,
)


class ProviderAdapter(Protocol):
    provider_type: str

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        ...

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        ...


def provider_registry(adapters: Iterable[ProviderAdapter]) -> dict[str, ProviderAdapter]:
    registry: dict[str, ProviderAdapter] = {}
    for adapter in adapters:
        if adapter.provider_type in registry:
            raise ValueError(f"duplicate_provider_adapter:{adapter.provider_type}")
        registry[adapter.provider_type] = adapter
    return registry


def optional_string_field(
    provider_type: str,
    payload: Mapping[str, object],
    field: str,
    allow_blank: bool = False,
) -> str | None:
    if field not in payload or payload[field] is None:
        return None
    value = _string_value(payload[field], allow_blank=allow_blank)
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_optional_field",
            },
        )
    return value


def required_string_field(
    provider_type: str,
    payload: Mapping[str, object],
    field: str,
) -> str:
    if field not in payload:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "missing_required_field",
            },
        )
    value = _string_value(payload[field], allow_blank=False)
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_required_field",
            },
        )
    return value


def _string_value(value: object, allow_blank: bool) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    if text:
        return text
    if allow_blank:
        return ""
    return None


def freeze_json(value: object, provider_type: str, path: str = "payload") -> ImmutableJsonValue:
    if isinstance(value, Mapping):
        frozen: dict[str, ImmutableJsonValue] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ChannelReachabilityError(
                    "invalid_provider_payload",
                    fact={
                        "type": "invalid_provider_payload",
                        "provider_type": provider_type,
                        "field": path,
                        "reason": "non_json_payload_key",
                    },
                )
            frozen[key] = freeze_json(nested_value, provider_type, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(
            freeze_json(nested_value, provider_type, f"{path}[{index}]")
            for index, nested_value in enumerate(value)
        )
    if isinstance(value, float) and not isfinite(value):
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": path,
                "reason": "non_json_payload_value",
            },
        )
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ChannelReachabilityError(
        "invalid_provider_payload",
        fact={
            "type": "invalid_provider_payload",
            "provider_type": provider_type,
            "field": path,
            "reason": "non_json_payload_value",
        },
    )
```

Create `coke/providers/whatsapp_evolution.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import freeze_json, optional_string_field, required_string_field


class WhatsAppEvolutionAdapter:
    provider_type = "whatsapp_evolution"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(self.provider_type, payload, "sender"),
            text=optional_string_field(
                self.provider_type, payload, "text", allow_blank=True
            )
            or "",
            raw_event_id=required_string_field(self.provider_type, payload, "message_id"),
            received_at=self._now(),
            pairing_code=optional_string_field(self.provider_type, payload, "pairing_code"),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
        )

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id=f"{self.provider_type}:{idempotency_key}",
            error_code=None,
            delivered_at=None,
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _required_string(provider_type: str, payload: Mapping[str, object], field: str) -> str:
    if field not in payload:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "missing_required_field",
            },
        )
    value = _optional_string(payload[field])
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_required_field",
            },
        )
    return value
```

Create `coke/providers/wechat_personal.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import freeze_json, optional_string_field, required_string_field


class WeChatPersonalAdapter:
    provider_type = "wechat_personal"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(self.provider_type, payload, "wxid"),
            text=optional_string_field(
                self.provider_type, payload, "text", allow_blank=True
            )
            or "",
            raw_event_id=required_string_field(self.provider_type, payload, "message_id"),
            received_at=self._now(),
            pairing_code=optional_string_field(self.provider_type, payload, "pairing_code"),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
        )

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id=f"{self.provider_type}:{idempotency_key}",
            error_code=None,
            delivered_at=None,
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _required_string(provider_type: str, payload: Mapping[str, object], field: str) -> str:
    if field not in payload:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "missing_required_field",
            },
        )
    value = _optional_string(payload[field])
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_required_field",
            },
        )
    return value
```

Create `coke/providers/wechat_ecloud.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import freeze_json, optional_string_field, required_string_field


class WeChatECloudAdapter:
    provider_type = "wechat_ecloud"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(self.provider_type, payload, "sender_id"),
            text=optional_string_field(
                self.provider_type, payload, "content", allow_blank=True
            )
            or "",
            raw_event_id=required_string_field(self.provider_type, payload, "msg_id"),
            received_at=self._now(),
            pairing_code=optional_string_field(self.provider_type, payload, "pairing_code"),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
        )

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id=f"{self.provider_type}:{idempotency_key}",
            error_code=None,
            delivered_at=None,
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _required_string(provider_type: str, payload: Mapping[str, object], field: str) -> str:
    if field not in payload:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "missing_required_field",
            },
        )
    value = _optional_string(payload[field])
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_required_field",
            },
        )
    return value
```

Create `coke/providers/linq.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.providers.base import freeze_json, optional_string_field, required_string_field


class LinqAdapter:
    provider_type = "linq"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(self.provider_type, payload, "from"),
            text=optional_string_field(
                self.provider_type, payload, "body", allow_blank=True
            )
            or "",
            raw_event_id=required_string_field(self.provider_type, payload, "id"),
            received_at=self._now(),
            pairing_code=optional_string_field(self.provider_type, payload, "pairing_code"),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
        )

    def send_text(
        self,
        route: DeliveryRoute,
        text: str,
        idempotency_key: str,
    ) -> DeliveryAttemptResult:
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id=f"{self.provider_type}:{idempotency_key}",
            error_code=None,
            delivered_at=None,
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _required_string(provider_type: str, payload: Mapping[str, object], field: str) -> str:
    if field not in payload:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "missing_required_field",
            },
        )
    value = _optional_string(payload[field])
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_payload",
            fact={
                "type": "invalid_provider_payload",
                "provider_type": provider_type,
                "field": field,
                "reason": "invalid_required_field",
            },
        )
    return value
```

- [ ] **Step 5: Run the provider tests to verify they pass**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py -v
```

Expected: all provider adapter tests pass.

- [ ] **Step 6: Commit provider contract**

Run:

```bash
git add coke/domains/channel_reachability/__init__.py coke/domains/channel_reachability/models.py coke/providers tests/unit/coke/channel_reachability/test_provider_adapters.py
git commit -m "feat: add channel provider adapter contract"
```

Expected: commit succeeds.

## Task 2: ChannelReachability Lifecycle, Route Resolution, And Send Idempotency

**Files:**
- Modify: `coke/domains/identity_access/service.py`
- Create: `coke/domains/channel_reachability/repository.py`
- Create: `coke/domains/channel_reachability/service.py`
- Modify: `coke/domains/channel_reachability/models.py`
- Modify test: `tests/unit/coke/identity_access/test_identity_access_service.py`
- Test: `tests/unit/coke/channel_reachability/test_channel_reachability_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/unit/coke/channel_reachability/test_channel_reachability_service.py`:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from itertools import count

import pytest

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    NormalizedInbound,
)
from coke.domains.channel_reachability.repository import InMemoryChannelReachabilityRepository
from coke.domains.channel_reachability.service import ChannelReachabilityService
from coke.domains.identity_access.models import IdentityAccessError
from coke.domains.identity_access.repository import InMemoryIdentityAccessRepository
from coke.domains.identity_access.service import IdentityAccessService


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


class RecordingAdapter:
    provider_type = "whatsapp_evolution"

    def __init__(self, status: str = "sent") -> None:
        self.status = status
        self.calls: list[tuple[str, str, str]] = []

    def normalize_inbound(self, payload):
        raise AssertionError("not used by these tests")

    def send_text(self, route, text, idempotency_key):
        self.calls.append((route.id, text, idempotency_key))
        if self.status == "failed":
            return DeliveryAttemptResult(
                status="failed",
                provider_message_id=None,
                error_code="provider_down",
                delivered_at=None,
            )
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id=f"provider:{idempotency_key}",
            error_code=None,
            delivered_at=None,
        )


class PassiveAdapter(RecordingAdapter):
    def __init__(self, provider_type: str) -> None:
        super().__init__()
        self.provider_type = provider_type


@pytest.fixture
def identity_service() -> IdentityAccessService:
    return IdentityAccessService(
        repository=InMemoryIdentityAccessRepository(now=lambda: NOW),
        now=lambda: NOW,
        token_factory=sequence_factory("token"),
        id_factory=sequence_factory("id"),
        checkout_url_factory=lambda account_id: f"https://checkout.example/{account_id}",
    )


@pytest.fixture
def reachability(identity_service):
    adapter = RecordingAdapter()
    wechat_personal = PassiveAdapter("wechat_personal")
    wechat_ecloud = PassiveAdapter("wechat_ecloud")
    linq = PassiveAdapter("linq")
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={
            adapter.provider_type: adapter,
            wechat_personal.provider_type: wechat_personal,
            wechat_ecloud.provider_type: wechat_ecloud,
            linq.provider_type: linq,
        },
        now=lambda: NOW,
        id_factory=sequence_factory("channel"),
    )
    return service, adapter


def verified_web_account(identity_service):
    registered = identity_service.register_web_account("a@example.com", "hash_1")
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(registered.account.id)
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=pairing.code,
    )
    return registered.account, resolved.channel_identity


def messaging_first_account(identity_service):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550999",
    )
    return resolved.account, resolved.channel_identity


def paired_identity(identity_service, account_id, provider_type, provider_subject):
    pairing = identity_service.issue_pairing_code(account_id)
    return identity_service.resolve_or_create_channel_identity(
        provider_type=provider_type,
        provider_subject=provider_subject,
        pairing_code=pairing.code,
    ).channel_identity


def test_single_active_channel_requires_remove_before_switch(identity_service, reachability):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )

    with pytest.raises(ChannelReachabilityError, match="active_channel_exists"):
        service.create_channel(
            account_id=account.id,
            provider_type="whatsapp_evolution",
            channel_identity_id=identity.id,
            removable=True,
        )

    removed = service.remove_channel(account_id=account.id, channel_id=first.id)
    second = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )

    assert removed.connection_state == "removed"
    assert removed.lifecycle == "removed"
    assert second.id != first.id
    assert service.get_status(account.id).channel_id == second.id


def test_connecting_is_not_reachable_and_connected_is_reachable(identity_service, reachability):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )
    connecting = service.connect_channel(account_id=account.id, channel_id=channel.id)

    assert connecting.connection_state == "connecting"
    assert service.get_status(account.id).reachable is False

    connected = service.mark_connected(account_id=account.id, channel_id=channel.id)

    assert connected.connection_state == "connected"
    assert service.get_status(account.id).reachable is True


def test_revoked_access_blocks_existing_channel_completion_from_webhook(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )
    identity_service.set_access_state(
        account_id=account.id,
        email_verification_state="verified",
        subscription_state="inactive",
        suspension_state="active",
    )
    before_identities = dict(identity_service.repository.channel_identities_by_id)
    before_accounts = dict(identity_service.repository.accounts)

    with pytest.raises(ChannelReachabilityError, match="access_denied") as exc_info:
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="whatsapp_evolution",
                provider_subject="whatsapp:+15555550123",
                text="connection callback",
                raw_event_id="wa_msg_after_revocation",
                received_at=NOW,
            )
        )

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": account.id,
        "denial_reason": "subscription_inactive",
        "checkout_url": None,
    }
    saved = service.repository.get_channel(channel.id)
    assert saved.connection_state == "not_connected"
    assert service.repository.get_active_route_for_channel(channel.id) is None
    assert identity_service.repository.channel_identities_by_id == before_identities
    assert identity_service.repository.accounts == before_accounts
    assert service.get_status(account.id).reachable is False


def test_account_access_gate_blocks_channel_creation(identity_service):
    registered = identity_service.register_web_account("a@example.com", "hash_1")
    repository = InMemoryChannelReachabilityRepository()
    adapter = RecordingAdapter()
    service = ChannelReachabilityService(
        repository=repository,
        identity_access=identity_service,
        providers={adapter.provider_type: adapter},
        now=lambda: NOW,
        id_factory=sequence_factory("blocked"),
    )

    with pytest.raises(ChannelReachabilityError, match="access_denied") as exc_info:
        service.create_channel(
            account_id=registered.account.id,
            provider_type="whatsapp_evolution",
            channel_identity_id="channel_identity_missing",
            removable=True,
        )

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": registered.account.id,
        "denial_reason": "email_verification_required",
        "checkout_url": None,
    }
    assert repository.list_channels(registered.account.id) == []


def test_unsupported_provider_inbound_fails_before_identity_access_writes(
    identity_service,
    reachability,
):
    service, _adapter = reachability
    before_identities = dict(identity_service.repository.channel_identities_by_id)
    before_accounts = dict(identity_service.repository.accounts)

    with pytest.raises(ChannelReachabilityError, match="unsupported_provider"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="unknown_provider",
                provider_subject="unknown_subject",
                text="hello",
                raw_event_id="unknown_event_1",
                received_at=NOW,
            )
        )

    assert identity_service.repository.channel_identities_by_id == before_identities
    assert identity_service.repository.accounts == before_accounts


@pytest.mark.parametrize("provider_type", ["wechat_ecloud", "linq"])
def test_retained_non_product_adapters_cannot_be_connected_as_personal_channels(
    identity_service,
    reachability,
    provider_type,
):
    account, _identity = verified_web_account(identity_service)
    provider_subject = "gewe_alice" if provider_type == "wechat_ecloud" else "+15555550125"
    retained_identity = paired_identity(
        identity_service,
        account.id,
        provider_type,
        provider_subject,
    )
    service, _adapter = reachability

    with pytest.raises(ChannelReachabilityError, match="unsupported_product_channel"):
        service.create_channel(
            account_id=account.id,
            provider_type=provider_type,
            channel_identity_id=retained_identity.id,
            removable=True,
        )

    assert service.get_status(account.id).reachable is False
    assert service.repository.list_channels(account.id) == []


@pytest.mark.parametrize(
    ("provider_type", "provider_subject"),
    [
        ("wechat_ecloud", "gewe_alice"),
        ("linq", "+15555550125"),
    ],
)
def test_retained_non_product_inbound_cannot_auto_bind_personal_channel(
    identity_service,
    reachability,
    provider_type,
    provider_subject,
):
    service, _adapter = reachability
    before_identities = dict(identity_service.repository.channel_identities_by_id)
    before_accounts = dict(identity_service.repository.accounts)

    with pytest.raises(ChannelReachabilityError, match="unsupported_product_channel"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type=provider_type,
                provider_subject=provider_subject,
                text="hello",
                raw_event_id=f"{provider_type}_event_1",
                received_at=NOW,
            )
        )

    assert identity_service.repository.channel_identities_by_id == before_identities
    assert identity_service.repository.accounts == before_accounts
    assert service.repository.list_attempts() == []


def test_pairing_webhook_active_channel_conflict_does_not_consume_or_bind_identity(
    identity_service,
    reachability,
):
    account, first_identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=first_identity.id,
        removable=True,
    )
    pairing = identity_service.issue_pairing_code(account.id)

    with pytest.raises(ChannelReachabilityError, match="active_channel_exists"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="whatsapp_evolution",
                provider_subject="whatsapp:+15555550124",
                text="pairing callback",
                raw_event_id="wa_pair_conflict",
                received_at=NOW,
                pairing_code=pairing.code,
            )
        )

    assert service.repository.get_active_channel(account.id).id == first.id
    assert identity_service.repository.get_artifact_by_code(pairing.code).consumed_at is None
    assert (
        identity_service.repository.get_channel_identity_by_provider(
            "whatsapp_evolution",
            "whatsapp:+15555550124",
        )
        is None
    )


def test_non_removable_messaging_anchor_cannot_be_removed(identity_service, reachability):
    account, identity = messaging_first_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=False,
    )

    with pytest.raises(ChannelReachabilityError, match="channel_identity_not_removable"):
        service.remove_channel(account_id=account.id, channel_id=channel.id)

    assert service.get_status(account.id).channel_id == channel.id


def test_removable_web_first_channel_removal_keeps_account_and_stops_reachability(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)
    service.mark_connected(account_id=account.id, channel_id=channel.id)

    removed = service.remove_channel(account_id=account.id, channel_id=channel.id)

    assert identity_service.repository.get_account(account.id) is not None
    assert removed.connection_state == "removed"
    assert service.get_status(account.id).reachable is False
    assert service.get_status(account.id).channel_id is None


def test_retry_from_failure_and_reconnection_required_returns_connecting(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)

    failed = service.mark_connection_failed(account.id, channel.id, "scan_expired")
    retrying = service.retry_connection(account.id, failed.id)
    required = service.mark_reconnection_required(account.id, retrying.id, "provider_session_lost")
    retrying_again = service.retry_connection(account.id, required.id)

    assert failed.connection_state == "connection_failed"
    assert retrying.connection_state == "connecting"
    assert required.connection_state == "reconnection_required"
    assert retrying_again.connection_state == "connecting"


def test_reconnect_reuses_route_key_safely(identity_service, reachability):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)
    service.mark_connected(account.id, channel.id)
    first_route = service.resolve_route(account.id)
    service.mark_reconnection_required(account.id, channel.id, "provider_session_lost")
    service.retry_connection(account.id, channel.id)
    service.mark_connected(account.id, channel.id)
    second_route = service.resolve_route(account.id)

    assert second_route.id == first_route.id
    assert second_route.route_key == f"{channel.id}:whatsapp_evolution:whatsapp:+15555550123"
    assert service.get_status(account.id).reachable is True


def test_remove_relink_same_address_retires_old_route_and_preserves_attempt_history(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)
    service.mark_connected(account.id, first.id)
    first_attempt = service.send_text(account.id, "first", "idem_original")
    first_route = service.repository.get_route(first_attempt.route_id)

    service.remove_channel(account.id, first.id)
    second = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)
    service.mark_connected(account.id, second.id)
    second_attempt = service.send_text(account.id, "second", "idem_second")
    retired_first_route = service.repository.get_route(first_attempt.route_id)
    second_route = service.repository.get_route(second_attempt.route_id)

    assert first_route.channel_id == first.id
    assert retired_first_route.id == first_route.id
    assert retired_first_route.lifecycle == "removed"
    assert retired_first_route.channel_id == first.id
    assert service.repository.get_route(first_attempt.route_id).id == first_attempt.route_id
    assert second_route.id != first_route.id
    assert second_route.lifecycle == "active"
    assert second_route.channel_id == second.id
    assert second_route.provider_address == first_route.provider_address


def test_send_resolves_current_connected_route_at_send_time(identity_service, reachability):
    account, first_identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(account.id, "whatsapp_evolution", first_identity.id, removable=True)
    service.mark_connected(account.id, first.id)
    first_attempt = service.send_text(account.id, "first", "idem_1")
    service.remove_channel(account.id, first.id)
    pairing = identity_service.issue_pairing_code(account.id)
    second_resolution = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550124",
        pairing_code=pairing.code,
    )
    second = service.create_channel(
        account.id,
        "whatsapp_evolution",
        second_resolution.channel_identity.id,
        removable=True,
    )
    service.mark_connected(account.id, second.id)
    second_attempt = service.send_text(account.id, "second", "idem_2")

    first_route = service.repository.get_route(first_attempt.route_id)
    second_route = service.repository.get_route(second_attempt.route_id)
    assert first_route.provider_address == "whatsapp:+15555550123"
    assert second_route.provider_address == "whatsapp:+15555550124"


def test_provider_edge_idempotency_reuses_attempt_without_second_adapter_call(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, adapter = reachability
    channel = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)
    service.mark_connected(account.id, channel.id)

    first = service.send_text(account.id, "hello", "idem_same")
    second = service.send_text(account.id, "hello again", "idem_same")

    assert second.id == first.id
    assert adapter.calls == [(first.route_id, "hello", "idem_same")]


def test_same_idempotency_key_after_route_switch_is_conflict_not_suppressed(
    identity_service,
    reachability,
):
    account, first_identity = verified_web_account(identity_service)
    service, adapter = reachability
    first = service.create_channel(account.id, "whatsapp_evolution", first_identity.id, removable=True)
    service.mark_connected(account.id, first.id)
    first_attempt = service.send_text(account.id, "first", "idem_conflict")
    service.remove_channel(account.id, first.id)
    pairing = identity_service.issue_pairing_code(account.id)
    second_identity = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550124",
        pairing_code=pairing.code,
    ).channel_identity
    second = service.create_channel(account.id, "whatsapp_evolution", second_identity.id, removable=True)
    service.mark_connected(account.id, second.id)

    with pytest.raises(ChannelReachabilityError, match="provider_idempotency_conflict") as exc_info:
        service.send_text(account.id, "second", "idem_conflict")

    assert exc_info.value.fact == {
        "type": "provider_idempotency_conflict",
        "provider_type": "whatsapp_evolution",
        "provider_idempotency_key": "idem_conflict",
        "existing_account_id": account.id,
        "current_account_id": account.id,
        "existing_route_id": first_attempt.route_id,
        "current_route_id": service.resolve_route(account.id).id,
    }
    assert adapter.calls == [(first_attempt.route_id, "first", "idem_conflict")]


def test_same_idempotency_key_for_different_account_is_conflict_not_suppressed(
    identity_service,
    reachability,
):
    first_account, first_identity = verified_web_account(identity_service)
    second_registration = identity_service.register_web_account("b@example.com", "hash_2")
    identity_service.set_access_state(
        account_id=second_registration.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    second_identity = paired_identity(
        identity_service,
        second_registration.account.id,
        "whatsapp_evolution",
        "whatsapp:+15555550126",
    )
    service, adapter = reachability
    first_channel = service.create_channel(
        first_account.id,
        "whatsapp_evolution",
        first_identity.id,
        removable=True,
    )
    second_channel = service.create_channel(
        second_registration.account.id,
        "whatsapp_evolution",
        second_identity.id,
        removable=True,
    )
    service.mark_connected(first_account.id, first_channel.id)
    service.mark_connected(second_registration.account.id, second_channel.id)
    first_attempt = service.send_text(first_account.id, "first", "idem_cross_account")

    with pytest.raises(ChannelReachabilityError, match="provider_idempotency_conflict") as exc_info:
        service.send_text(second_registration.account.id, "second", "idem_cross_account")

    assert exc_info.value.fact == {
        "type": "provider_idempotency_conflict",
        "provider_type": "whatsapp_evolution",
        "provider_idempotency_key": "idem_cross_account",
        "existing_account_id": first_account.id,
        "current_account_id": second_registration.account.id,
        "existing_route_id": first_attempt.route_id,
        "current_route_id": service.resolve_route(second_registration.account.id).id,
    }
    assert adapter.calls == [(first_attempt.route_id, "first", "idem_cross_account")]


def test_failed_provider_send_is_never_delivered(identity_service):
    account, identity = verified_web_account(identity_service)
    adapter = RecordingAdapter(status="failed")
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={adapter.provider_type: adapter},
        now=lambda: NOW,
        id_factory=sequence_factory("failed"),
    )
    channel = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)
    service.mark_connected(account.id, channel.id)

    attempt = service.send_text(account.id, "hello", "idem_failed")

    assert attempt.status == "failed"
    assert attempt.delivered_at is None
    assert attempt.provider_message_id is None
    assert attempt.error_code == "provider_down"


def test_absent_send_without_connected_channel_is_never_delivered(identity_service, reachability):
    account, identity = verified_web_account(identity_service)
    service, adapter = reachability
    service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)

    with pytest.raises(ChannelReachabilityError, match="no_connected_channel"):
        service.send_text(account.id, "hello", "idem_absent")

    assert adapter.calls == []
    assert service.repository.list_attempts() == []


def test_channel_reachability_does_not_write_channel_identity(identity_service, reachability):
    account, identity = verified_web_account(identity_service)
    before = dict(identity_service.repository.channel_identities_by_id)
    service, _adapter = reachability
    channel = service.create_channel(account.id, "whatsapp_evolution", identity.id, removable=True)
    service.mark_connected(account.id, channel.id)
    service.send_text(account.id, "hello", "idem_nowrite")
    service.remove_channel(account.id, channel.id)

    assert identity_service.repository.channel_identities_by_id == before
```

Task 2 also must include the quality-hardening regressions from code review:

- `test_revoked_access_blocks_already_connected_channel_inbound`: after an already connected account loses `connect_channel` access, provider inbound raises `ChannelReachabilityError("access_denied")` and does not call `mark_first_inbound_received`.
- `test_mark_connected_does_not_save_connected_state_when_route_resolution_fails`: if owned identity/route validation fails, the channel remains not connected and no active route is created.
- `test_invalid_pairing_code_maps_identity_error_to_channel_error`: invalid pairing artifacts are surfaced as `ChannelReachabilityError`, not leaked `IdentityAccessError`.
- `test_remove_missing_identity_maps_identity_error_to_channel_error`: removal-time IdentityAccess failures map to `ChannelReachabilityError` and leave the channel active.
- `test_repository_refuses_to_reactivate_retired_route_key`: a retired route key cannot be upserted back to active because retired routes are historical delivery evidence.
- `test_missing_account_access_error_maps_to_channel_error`: access checks for missing or corrupted accounts raise `ChannelReachabilityError`, not `IdentityAccessError`.
- `test_mark_connected_missing_activation_maps_error_without_connection_write`: missing activation records fail before route or connected-state writes.
- `test_inbound_missing_activation_maps_identity_error_to_channel_error`: inbound activation updates are mapped at the ChannelReachability boundary.
- `test_repository_rejects_duplicate_route_id_for_different_route_key`: route id collisions cannot corrupt route history.
- `test_repository_rejects_second_active_route_for_same_channel`: a channel cannot have multiple active delivery routes.
- `test_repository_rejects_existing_route_key_reassigned_to_another_channel`: an existing route key cannot be mutated onto another account/channel/provider address.

- [ ] **Step 2: Run the service tests to verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_channel_reachability_service.py -v
```

Expected: fail during import because `coke.domains.channel_reachability.repository` and `service` do not exist.

- [ ] **Step 3: Add focused IdentityAccess preview tests**

Append to `tests/unit/coke/identity_access/test_identity_access_service.py`:

```python
def test_preview_pairing_code_account_returns_account_without_consuming(identity_service):
    registered = identity_service.register_web_account(
        email="preview@example.com",
        password_hash="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)

    account_id = identity_service.preview_pairing_code_account(pairing.code)

    assert account_id == registered.account.id
    assert identity_service.repository.get_artifact_by_code(pairing.code).consumed_at is None


def test_preview_pairing_code_account_rejects_wrong_expired_or_consumed_artifact(identity_service):
    registered = identity_service.register_web_account(
        email="preview@example.com",
        password_hash="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    login_url = identity_service.issue_login_url(account_id=registered.account.id)
    consumed = identity_service.issue_pairing_code(account_id=registered.account.id)
    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=consumed.code,
    )
    expiring = identity_service.issue_pairing_code(account_id=registered.account.id)
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=2),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_wrong_type"):
        identity_service.preview_pairing_code_account(login_url.code)

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.preview_pairing_code_account(consumed.code)

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.preview_pairing_code_account(expiring.code)
```

- [ ] **Step 4: Run IdentityAccess preview tests to verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_identity_access_service.py::test_preview_pairing_code_account_returns_account_without_consuming tests/unit/coke/identity_access/test_identity_access_service.py::test_preview_pairing_code_account_rejects_wrong_expired_or_consumed_artifact -v
```

Expected: fail with `AttributeError` for `preview_pairing_code_account`.

- [ ] **Step 5: Add read-only IdentityAccess methods when absent**

Modify `coke/domains/identity_access/service.py` by adding these methods immediately after `can_remove_channel_identity`:

```python
    def get_owned_channel_identity(self, account_id: str, channel_identity_id: str) -> ChannelIdentity:
        self._require_account(account_id)
        identity = self.repository.get_channel_identity(channel_identity_id)
        if identity is None or identity.account_id != account_id or identity.lifecycle != "active":
            raise IdentityAccessError("channel_identity_not_found")
        return identity

    def preview_pairing_code_account(self, pairing_code: str) -> str:
        artifact = self._require_unconsumed_artifact(
            pairing_code,
            expected_type=ArtifactType.PAIRING_CODE,
        )
        if artifact.account_id is None:
            raise IdentityAccessError("artifact_missing_account")
        self._require_account(artifact.account_id)
        return artifact.account_id
```

Expected: both methods read IdentityAccess-owned data and do not add any channel identity writer or consume any artifact.

- [ ] **Step 6: Run IdentityAccess preview tests to verify they pass**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_identity_access_service.py::test_preview_pairing_code_account_returns_account_without_consuming tests/unit/coke/identity_access/test_identity_access_service.py::test_preview_pairing_code_account_rejects_wrong_expired_or_consumed_artifact -v
```

Expected: both preview tests pass.

- [ ] **Step 7: Add channel repository boundary**

Create `coke/domains/channel_reachability/repository.py`:

```python
from __future__ import annotations

from typing import Protocol

from coke.domains.channel_reachability.models import Channel, DeliveryAttempt, DeliveryRoute


class ChannelReachabilityRepository(Protocol):
    def add_channel(self, channel: Channel) -> None: ...

    def save_channel(self, channel: Channel) -> None: ...

    def get_channel(self, channel_id: str) -> Channel | None: ...

    def get_active_channel(self, account_id: str) -> Channel | None: ...

    def list_channels(self, account_id: str) -> list[Channel]: ...

    def upsert_route(self, route: DeliveryRoute) -> DeliveryRoute: ...

    def get_route(self, route_id: str) -> DeliveryRoute | None: ...

    def get_active_route_for_channel(self, channel_id: str) -> DeliveryRoute | None: ...

    def retire_routes_for_channel(self, channel_id: str, retired_at) -> None: ...

    def save_attempt(self, attempt: DeliveryAttempt) -> None: ...

    def get_attempt_by_provider_idempotency(
        self,
        provider_type: str,
        provider_idempotency_key: str,
    ) -> DeliveryAttempt | None: ...


class InMemoryChannelReachabilityRepository:
    def __init__(self) -> None:
        self.channels_by_id: dict[str, Channel] = {}
        self.routes_by_id: dict[str, DeliveryRoute] = {}
        self.routes_by_key: dict[str, DeliveryRoute] = {}
        self.attempts_by_id: dict[str, DeliveryAttempt] = {}
        self.attempts_by_provider_idempotency: dict[tuple[str, str], DeliveryAttempt] = {}

    def add_channel(self, channel: Channel) -> None:
        if channel.id in self.channels_by_id:
            raise ValueError("duplicate_channel_id")
        if channel.lifecycle == "active" and self.get_active_channel(channel.account_id) is not None:
            raise ValueError("duplicate_active_channel")
        self.channels_by_id[channel.id] = channel

    def save_channel(self, channel: Channel) -> None:
        if channel.id not in self.channels_by_id:
            raise ValueError("channel_not_found")
        if channel.lifecycle == "active":
            active = self.get_active_channel(channel.account_id)
            if active is not None and active.id != channel.id:
                raise ValueError("duplicate_active_channel")
        self.channels_by_id[channel.id] = channel

    def get_channel(self, channel_id: str) -> Channel | None:
        return self.channels_by_id.get(channel_id)

    def get_active_channel(self, account_id: str) -> Channel | None:
        for channel in self.channels_by_id.values():
            if channel.account_id == account_id and channel.lifecycle == "active":
                return channel
        return None

    def list_channels(self, account_id: str) -> list[Channel]:
        return [channel for channel in self.channels_by_id.values() if channel.account_id == account_id]

    def upsert_route(self, route: DeliveryRoute) -> DeliveryRoute:
        existing = self.routes_by_key.get(route.route_key)
        if existing is not None:
            if existing.lifecycle != "active":
                raise ValueError("retired_route_key")
            existing_by_id = self.routes_by_id.get(route.id)
            if existing_by_id is not None and existing_by_id.id != existing.id:
                raise ValueError("duplicate_delivery_route_id")
            if (
                route.account_id != existing.account_id
                or route.channel_id != existing.channel_id
                or route.provider_type != existing.provider_type
                or route.provider_address != existing.provider_address
            ):
                raise ValueError("delivery_route_identity_mismatch")
            updated = DeliveryRoute(
                id=existing.id,
                account_id=existing.account_id,
                channel_id=existing.channel_id,
                provider_type=existing.provider_type,
                provider_address=existing.provider_address,
                route_key=route.route_key,
                lifecycle="active",
                created_at=existing.created_at,
                updated_at=route.updated_at,
            )
            self.routes_by_id[updated.id] = updated
            self.routes_by_key[updated.route_key] = updated
            return updated
        if route.id in self.routes_by_id:
            raise ValueError("duplicate_delivery_route_id")
        active_for_channel = self.get_active_route_for_channel(route.channel_id)
        if active_for_channel is not None:
            raise ValueError("duplicate_active_route_for_channel")
        self.routes_by_id[route.id] = route
        self.routes_by_key[route.route_key] = route
        return route

    def get_route(self, route_id: str) -> DeliveryRoute | None:
        return self.routes_by_id.get(route_id)

    def get_active_route_for_channel(self, channel_id: str) -> DeliveryRoute | None:
        for route in self.routes_by_id.values():
            if route.channel_id == channel_id and route.lifecycle == "active":
                return route
        return None

    def retire_routes_for_channel(self, channel_id: str, retired_at) -> None:
        for route in list(self.routes_by_id.values()):
            if route.channel_id == channel_id and route.lifecycle == "active":
                retired = DeliveryRoute(
                    id=route.id,
                    account_id=route.account_id,
                    channel_id=route.channel_id,
                    provider_type=route.provider_type,
                    provider_address=route.provider_address,
                    route_key=route.route_key,
                    lifecycle="removed",
                    created_at=route.created_at,
                    updated_at=retired_at,
                )
                self.routes_by_id[retired.id] = retired
                self.routes_by_key[retired.route_key] = retired

    def save_attempt(self, attempt: DeliveryAttempt) -> None:
        key = (attempt.provider_type, attempt.provider_idempotency_key)
        if attempt.id in self.attempts_by_id:
            raise ValueError("duplicate_delivery_attempt_id")
        if key in self.attempts_by_provider_idempotency:
            raise ValueError("duplicate_provider_idempotency_key")
        self.attempts_by_id[attempt.id] = attempt
        self.attempts_by_provider_idempotency[key] = attempt

    def get_attempt_by_provider_idempotency(
        self,
        provider_type: str,
        provider_idempotency_key: str,
    ) -> DeliveryAttempt | None:
        return self.attempts_by_provider_idempotency.get((provider_type, provider_idempotency_key))

    def list_attempts(self) -> list[DeliveryAttempt]:
        return list(self.attempts_by_id.values())
```

- [ ] **Step 8: Add status and webhook result models**

Append to `coke/domains/channel_reachability/models.py`:

```python
@dataclass(frozen=True, slots=True)
class ChannelStatus:
    account_id: str
    channel_id: str | None
    provider_type: str | None
    connection_state: ChannelConnectionState
    reachable: bool


@dataclass(frozen=True, slots=True)
class ProviderWebhookAcceptance:
    accepted: bool
    provider_type: str
    provider_subject: str
    account_id: str
    channel_identity_id: str
    channel_id: str
    created_account: bool
    raw_event_id: str
```

- [ ] **Step 9: Add the ChannelReachability service**

Create `coke/domains/channel_reachability/service.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol, TypeVar
from uuid import uuid4

from coke.domains.channel_reachability.models import (
    Channel,
    ChannelReachabilityError,
    ChannelStatus,
    DeliveryAttempt,
    DeliveryRoute,
    NormalizedInbound,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
    ProviderWebhookAcceptance,
)
from coke.domains.channel_reachability.repository import ChannelReachabilityRepository
from coke.domains.identity_access.models import (
    AccessDecision,
    AccountActivation,
    ChannelIdentity,
    ChannelIdentityResolution,
    IdentityAccessError,
)
from coke.providers.base import ProviderAdapter


IdentityCallResult = TypeVar("IdentityCallResult")


class IdentityAccessPort(Protocol):
    def check_access_for_action(self, account_id: str, action: str) -> AccessDecision:
        ...

    def get_activation(self, account_id: str) -> AccountActivation:
        ...

    def observe_usable_channel(self, account_id: str) -> AccountActivation:
        ...

    def mark_first_inbound_received(self, account_id: str) -> AccountActivation:
        ...

    def can_remove_channel_identity(
        self, account_id: str, channel_identity_id: str
    ) -> bool:
        ...

    def get_owned_channel_identity(
        self, account_id: str, channel_identity_id: str
    ) -> ChannelIdentity:
        ...

    def preview_pairing_code_account(self, pairing_code: str) -> str:
        ...

    def resolve_or_create_channel_identity(
        self,
        provider_type: str,
        provider_subject: str,
        pairing_code: str | None = None,
    ) -> ChannelIdentityResolution:
        ...


class ChannelReachabilityService:
    def __init__(
        self,
        repository: ChannelReachabilityRepository,
        identity_access: IdentityAccessPort,
        providers: Mapping[str, ProviderAdapter],
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.identity_access = identity_access
        self.providers = dict(providers)
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: f"{prefix}_{uuid4().hex}")

    def get_status(self, account_id: str) -> ChannelStatus:
        channel = self.repository.get_active_channel(account_id)
        if channel is None:
            return ChannelStatus(
                account_id=account_id,
                channel_id=None,
                provider_type=None,
                connection_state="not_connected",
                reachable=False,
            )
        return ChannelStatus(
            account_id=account_id,
            channel_id=channel.id,
            provider_type=channel.provider_type,
            connection_state=channel.connection_state,
            reachable=channel.connection_state == "connected",
        )

    def create_channel(
        self,
        account_id: str,
        provider_type: str,
        channel_identity_id: str,
        removable: bool,
    ) -> Channel:
        self._require_provider(provider_type)
        self._require_product_channel(provider_type)
        self._require_access(account_id)
        identity = self._require_owned_identity(account_id, channel_identity_id)
        if identity.provider_type != provider_type:
            raise ChannelReachabilityError("provider_identity_mismatch")
        if self.repository.get_active_channel(account_id) is not None:
            raise ChannelReachabilityError("active_channel_exists")
        channel = Channel(
            id=self._id_factory("channel"),
            account_id=account_id,
            channel_identity_id=channel_identity_id,
            provider_type=provider_type,
            lifecycle="active",
            connection_state="not_connected",
            removable=removable,
            connected_at=None,
            removed_at=None,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.add_channel(channel)
        return channel

    def connect_channel(self, account_id: str, channel_id: str) -> Channel:
        self._require_access(account_id)
        channel = self._require_channel(account_id, channel_id)
        return self._save_state(channel, "connecting")

    def poll_channel(self, account_id: str, channel_id: str) -> Channel:
        return self._require_channel(account_id, channel_id)

    def mark_connected(self, account_id: str, channel_id: str) -> Channel:
        self._require_access(account_id)
        channel = self._require_channel(account_id, channel_id)
        self._identity_call(lambda: self.identity_access.get_activation(account_id))
        self._resolve_route_for_channel(channel)
        updated = replace(
            channel,
            connection_state="connected",
            connected_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.save_channel(updated)
        self._identity_call(
            lambda: self.identity_access.observe_usable_channel(account_id)
        )
        return updated

    def mark_connection_failed(self, account_id: str, channel_id: str, reason: str) -> Channel:
        channel = self._require_channel(account_id, channel_id)
        return self._save_state(channel, "connection_failed")

    def mark_reconnection_required(self, account_id: str, channel_id: str, reason: str) -> Channel:
        channel = self._require_channel(account_id, channel_id)
        return self._save_state(channel, "reconnection_required")

    def retry_connection(self, account_id: str, channel_id: str) -> Channel:
        self._require_access(account_id)
        channel = self._require_channel(account_id, channel_id)
        if channel.connection_state not in {"connection_failed", "reconnection_required"}:
            raise ChannelReachabilityError("channel_retry_not_allowed")
        return self._save_state(channel, "connecting")

    def remove_channel(self, account_id: str, channel_id: str) -> Channel:
        channel = self._require_channel(account_id, channel_id)
        if not self._identity_call(
            lambda: self.identity_access.can_remove_channel_identity(account_id, channel.channel_identity_id)
        ):
            raise ChannelReachabilityError("channel_identity_not_removable")
        if not channel.removable:
            raise ChannelReachabilityError("channel_not_removable")
        updated = replace(
            channel,
            lifecycle="removed",
            connection_state="removed",
            removed_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.save_channel(updated)
        self.repository.retire_routes_for_channel(channel.id, retired_at=self._now())
        return updated

    def resolve_route(self, account_id: str) -> DeliveryRoute:
        channel = self.repository.get_active_channel(account_id)
        if channel is None or channel.connection_state != "connected":
            raise ChannelReachabilityError("no_connected_channel")
        return self._resolve_route_for_channel(channel)

    def _resolve_route_for_channel(self, channel: Channel) -> DeliveryRoute:
        identity = self._require_owned_identity(channel.account_id, channel.channel_identity_id)
        route_key = f"{channel.id}:{channel.provider_type}:{identity.provider_subject}"
        route = DeliveryRoute(
            id=self._id_factory("delivery_route"),
            account_id=channel.account_id,
            channel_id=channel.id,
            provider_type=channel.provider_type,
            provider_address=identity.provider_subject,
            route_key=route_key,
            lifecycle="active",
            created_at=self._now(),
            updated_at=self._now(),
        )
        return self.repository.upsert_route(route)

    def send_text(
        self,
        account_id: str,
        text: str,
        idempotency_key: str,
        turn_id: str | None = None,
        message_id: str | None = None,
    ) -> DeliveryAttempt:
        route = self.resolve_route(account_id)
        existing = self.repository.get_attempt_by_provider_idempotency(
            route.provider_type,
            idempotency_key,
        )
        if existing is not None:
            existing_route = self.repository.get_route(existing.route_id)
            if existing.route_id != route.id or existing_route is None or existing_route.account_id != account_id:
                raise ChannelReachabilityError(
                    "provider_idempotency_conflict",
                    fact={
                        "type": "provider_idempotency_conflict",
                        "provider_type": route.provider_type,
                        "provider_idempotency_key": idempotency_key,
                        "existing_account_id": existing_route.account_id if existing_route is not None else None,
                        "current_account_id": account_id,
                        "existing_route_id": existing.route_id,
                        "current_route_id": route.id,
                    },
                )
            return existing
        adapter = self._require_provider(route.provider_type)
        result = adapter.send_text(route=route, text=text, idempotency_key=idempotency_key)
        attempt = DeliveryAttempt(
            id=self._id_factory("delivery_attempt"),
            route_id=route.id,
            provider_type=route.provider_type,
            provider_idempotency_key=idempotency_key,
            status=result.status,
            provider_message_id=result.provider_message_id,
            error_code=result.error_code,
            attempted_at=self._now(),
            delivered_at=result.delivered_at if result.status == "delivered" else None,
            created_at=self._now(),
            updated_at=self._now(),
            turn_id=turn_id,
            message_id=message_id,
        )
        self.repository.save_attempt(attempt)
        return attempt

    def accept_provider_inbound(self, inbound: NormalizedInbound) -> ProviderWebhookAcceptance:
        self._require_provider(inbound.provider_type)
        self._require_product_channel(inbound.provider_type)
        if inbound.pairing_code is not None:
            target_account_id = self._identity_call(
                lambda: self.identity_access.preview_pairing_code_account(inbound.pairing_code)
            )
            active = self.repository.get_active_channel(target_account_id)
            if active is not None:
                raise ChannelReachabilityError(
                    "active_channel_exists",
                    fact={"type": "active_channel_exists", "account_id": target_account_id},
                )
        resolution = self._identity_call(
            lambda: self.identity_access.resolve_or_create_channel_identity(
                provider_type=inbound.provider_type,
                provider_subject=inbound.provider_subject,
                pairing_code=inbound.pairing_code,
            )
        )
        account_id = resolution.account.id
        self._require_access(account_id)
        channel = self.repository.get_active_channel(account_id)
        if channel is None:
            channel = self.create_channel(
                account_id=account_id,
                provider_type=inbound.provider_type,
                channel_identity_id=resolution.channel_identity.id,
                removable=not resolution.channel_identity.is_account_anchor,
            )
        elif channel.channel_identity_id != resolution.channel_identity.id:
            raise ChannelReachabilityError("active_channel_exists")
        if channel.connection_state != "connected":
            channel = self.mark_connected(account_id=account_id, channel_id=channel.id)
        self._identity_call(
            lambda: self.identity_access.mark_first_inbound_received(account_id)
        )
        return ProviderWebhookAcceptance(
            accepted=True,
            provider_type=inbound.provider_type,
            provider_subject=inbound.provider_subject,
            account_id=account_id,
            channel_identity_id=resolution.channel_identity.id,
            channel_id=channel.id,
            created_account=resolution.created_account,
            raw_event_id=inbound.raw_event_id,
        )

    def _require_channel(self, account_id: str, channel_id: str) -> Channel:
        channel = self.repository.get_channel(channel_id)
        if channel is None or channel.account_id != account_id or channel.lifecycle != "active":
            raise ChannelReachabilityError("channel_not_found")
        return channel

    def _save_state(self, channel: Channel, state) -> Channel:
        updated = replace(channel, connection_state=state, updated_at=self._now())
        self.repository.save_channel(updated)
        return updated

    def _require_access(self, account_id: str) -> None:
        decision = self._identity_call(
            lambda: self.identity_access.check_access_for_action(
                account_id, "connect_channel"
            )
        )
        if not decision.allowed:
            raise ChannelReachabilityError("access_denied", fact=decision.fact)

    def _require_provider(self, provider_type: str) -> ProviderAdapter:
        try:
            return self.providers[provider_type]
        except KeyError as error:
            raise ChannelReachabilityError("unsupported_provider") from error

    def _require_product_channel(self, provider_type: str) -> None:
        if provider_type not in PRODUCT_CHANNEL_PROVIDER_TYPES:
            raise ChannelReachabilityError(
                "unsupported_product_channel",
                fact={
                    "type": "unsupported_product_channel",
                    "provider_type": provider_type,
                    "supported_provider_types": sorted(PRODUCT_CHANNEL_PROVIDER_TYPES),
                },
            )

    def _require_owned_identity(self, account_id: str, channel_identity_id: str):
        try:
            return self.identity_access.get_owned_channel_identity(account_id, channel_identity_id)
        except IdentityAccessError as error:
            raise ChannelReachabilityError(error.code, fact=error.fact) from error

    def _identity_call(
        self, callback: Callable[[], IdentityCallResult]
    ) -> IdentityCallResult:
        try:
            return callback()
        except IdentityAccessError as error:
            raise ChannelReachabilityError(error.code, fact=error.fact) from error
```

- [ ] **Step 10: Run the service tests to verify they pass**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_channel_reachability_service.py -v
```

Expected: all service tests pass.

- [ ] **Step 11: Export service class from the package initializer**

Modify `coke/domains/channel_reachability/__init__.py`:

```python
from coke.domains.channel_reachability.models import (
    Channel,
    ChannelReachabilityError,
    DeliveryAttempt,
    DeliveryAttemptResult,
    DeliveryRoute,
    ImmutableJsonValue,
    NormalizedInbound,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
    RETAINED_PROVIDER_TYPES,
)
from coke.domains.channel_reachability.service import ChannelReachabilityService

__all__ = [
    "Channel",
    "ChannelReachabilityError",
    "ChannelReachabilityService",
    "DeliveryAttempt",
    "DeliveryAttemptResult",
    "DeliveryRoute",
    "ImmutableJsonValue",
    "NormalizedInbound",
    "PRODUCT_CHANNEL_PROVIDER_TYPES",
    "RETAINED_PROVIDER_TYPES",
]
```

- [ ] **Step 12: Run the service tests after the package export**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_channel_reachability_service.py -v
```

Expected: all service tests still pass.

- [ ] **Step 13: Commit service lifecycle**

Run:

```bash
git add coke/domains/identity_access/service.py coke/domains/channel_reachability tests/unit/coke/channel_reachability/test_channel_reachability_service.py tests/unit/coke/identity_access/test_identity_access_service.py
git commit -m "feat: implement channel reachability service"
```

Expected: commit succeeds.

## Task 3: Provider Webhook Route Without ConversationRuntime

**Files:**
- Create: `coke/api/provider_webhooks.py`
- Test: `tests/unit/coke/channel_reachability/test_provider_webhooks.py`

- [ ] **Step 1: Write the failing webhook route tests**

Create `tests/unit/coke/channel_reachability/test_provider_webhooks.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from coke.api.provider_webhooks import create_provider_webhook_blueprint
from coke.domains.channel_reachability.models import ChannelReachabilityError, ProviderWebhookAcceptance


class FakeAdapter:
    provider_type = "whatsapp_evolution"

    def normalize_inbound(self, payload):
        return SimpleNamespace(
            provider_type="whatsapp_evolution",
            provider_subject=payload["sender"],
            text=payload.get("text", ""),
            raw_event_id=payload["message_id"],
            pairing_code=payload.get("pairing_code"),
        )

    def send_text(self, route, text, idempotency_key):
        raise AssertionError("webhook ingress must not send")


class FakeReachabilityService:
    def __init__(self) -> None:
        self.calls = []

    def accept_provider_inbound(self, inbound):
        self.calls.append(("accept_provider_inbound", inbound))
        return ProviderWebhookAcceptance(
            accepted=True,
            provider_type=inbound.provider_type,
            provider_subject=inbound.provider_subject,
            account_id="acct_1",
            channel_identity_id="ci_1",
            channel_id="channel_1",
            created_account=True,
            raw_event_id=inbound.raw_event_id,
        )


def make_client(service=None, adapters=None):
    service = service or FakeReachabilityService()
    adapters = adapters if adapters is not None else {"whatsapp_evolution": FakeAdapter()}
    app = Flask(__name__)
    app.register_blueprint(create_provider_webhook_blueprint(service, adapters))
    return app.test_client(), service


def test_provider_webhook_normalizes_and_returns_structured_identity_facts_only():
    client, service = make_client()

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={
            "message_id": "wa_msg_1",
            "sender": "whatsapp:+15555550123",
            "text": "hello",
        },
    )

    assert response.status_code == 202
    assert response.get_json() == {
        "accepted": True,
        "provider_type": "whatsapp_evolution",
        "provider_subject": "whatsapp:+15555550123",
        "account_id": "acct_1",
        "channel_identity_id": "ci_1",
        "channel_id": "channel_1",
        "created_account": True,
        "raw_event_id": "wa_msg_1",
    }
    assert service.calls[0][0] == "accept_provider_inbound"


def test_provider_webhook_rejects_unknown_provider_with_json_error():
    client, _service = make_client(adapters={})

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={"message_id": "wa_msg_1", "sender": "whatsapp:+15555550123"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "unsupported_provider"}}


def test_provider_webhook_rejects_retained_non_product_provider_before_binding():
    class WeChatECloudFakeAdapter:
        provider_type = "wechat_ecloud"

        def normalize_inbound(self, payload):
            return SimpleNamespace(
                provider_type="wechat_ecloud",
                provider_subject=payload["sender_id"],
                text=payload.get("content", ""),
                raw_event_id=payload["msg_id"],
                pairing_code=payload.get("pairing_code"),
            )

        def send_text(self, route, text, idempotency_key):
            raise AssertionError("webhook ingress must not send")

    client, service = make_client(adapters={"wechat_ecloud": WeChatECloudFakeAdapter()})

    response = client.post(
        "/webhooks/wechat/ecloud",
        json={"msg_id": "gewe_msg_1", "sender_id": "gewe_alice", "content": "hello"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "unsupported_product_channel",
            "fact": {
                "type": "unsupported_product_channel",
                "provider_type": "wechat_ecloud",
                "supported_provider_types": ["wechat_personal", "whatsapp_evolution"],
            },
        }
    }
    assert service.calls == []


def test_provider_webhook_maps_reachability_error_to_json_error():
    class ErrorService(FakeReachabilityService):
        def accept_provider_inbound(self, inbound):
            raise ChannelReachabilityError(
                "active_channel_exists",
                fact={"type": "channel_conflict", "account_id": "acct_1"},
            )

    client, _service = make_client(service=ErrorService())

    response = client.post(
        "/webhooks/whatsapp/evolution",
        json={"message_id": "wa_msg_1", "sender": "whatsapp:+15555550123"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "active_channel_exists",
            "fact": {"type": "channel_conflict", "account_id": "acct_1"},
        }
    }
```

- [ ] **Step 2: Run the webhook tests to verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_provider_webhooks.py -v
```

Expected: fail during import because `coke.api.provider_webhooks` does not exist.

- [ ] **Step 3: Add the provider webhook blueprint**

Create `coke/api/provider_webhooks.py`:

```python
from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
)


def create_provider_webhook_blueprint(reachability_service, providers) -> Blueprint:
    blueprint = Blueprint("provider_webhooks", __name__)

    @blueprint.errorhandler(ChannelReachabilityError)
    def handle_channel_error(error: ChannelReachabilityError):
        return jsonify(_error_body(error.code, error.fact)), 400

    @blueprint.post("/webhooks/whatsapp/evolution")
    def whatsapp_evolution_inbound():
        return _handle_inbound("whatsapp_evolution")

    @blueprint.post("/webhooks/wechat/personal")
    def wechat_personal_inbound():
        return _handle_inbound("wechat_personal")

    @blueprint.post("/webhooks/wechat/ecloud")
    def wechat_ecloud_inbound():
        return _handle_inbound("wechat_ecloud")

    @blueprint.post("/webhooks/linq")
    def linq_inbound():
        return _handle_inbound("linq")

    def _handle_inbound(provider_type: str):
        adapter = providers.get(provider_type)
        if adapter is None:
            raise ChannelReachabilityError("unsupported_provider")
        if provider_type not in PRODUCT_CHANNEL_PROVIDER_TYPES:
            raise ChannelReachabilityError(
                "unsupported_product_channel",
                fact={
                    "type": "unsupported_product_channel",
                    "provider_type": provider_type,
                    "supported_provider_types": sorted(PRODUCT_CHANNEL_PROVIDER_TYPES),
                },
            )
        payload = _json_payload()
        inbound_event = adapter.normalize_inbound(payload)
        accepted = reachability_service.accept_provider_inbound(inbound_event)
        return (
            jsonify(
                {
                    "accepted": accepted.accepted,
                    "provider_type": accepted.provider_type,
                    "provider_subject": accepted.provider_subject,
                    "account_id": accepted.account_id,
                    "channel_identity_id": accepted.channel_identity_id,
                    "channel_id": accepted.channel_id,
                    "created_account": accepted.created_account,
                    "raw_event_id": accepted.raw_event_id,
                }
            ),
            202,
        )

    return blueprint


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "reason": "json_body_required",
            },
        )
    return payload


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body
```

- [ ] **Step 4: Run the webhook tests to verify they pass**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_provider_webhooks.py -v
```

Expected: all provider webhook tests pass.

- [ ] **Step 5: Commit provider webhook ingress**

Run:

```bash
git add coke/api/provider_webhooks.py tests/unit/coke/channel_reachability/test_provider_webhooks.py
git commit -m "feat: add provider webhook channel binding"
```

Expected: commit succeeds.

## Task 4: Thin Channel API Routes And Optional App Registration

**Files:**
- Create: `coke/api/channel_routes.py`
- Modify: `coke/app.py`
- Test: `tests/unit/coke/channel_reachability/test_channel_routes.py`

- [ ] **Step 1: Write the failing route tests**

Create `tests/unit/coke/channel_reachability/test_channel_routes.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from coke.app import create_app
from coke.api.channel_routes import create_channel_blueprint
from coke.config import Settings
from coke.domains.channel_reachability.models import ChannelReachabilityError


DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeReachabilityService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_status(self, account_id):
        self.calls.append(("get_status", {"account_id": account_id}))
        return SimpleNamespace(
            account_id=account_id,
            channel_id="channel_1",
            provider_type="whatsapp_evolution",
            connection_state="connected",
            reachable=True,
        )

    def create_channel(self, account_id, provider_type, channel_identity_id, removable):
        self.calls.append(
            (
                "create_channel",
                {
                    "account_id": account_id,
                    "provider_type": provider_type,
                    "channel_identity_id": channel_identity_id,
                    "removable": removable,
                },
            )
        )
        return self._channel("not_connected")

    def connect_channel(self, account_id, channel_id):
        self.calls.append(("connect_channel", {"account_id": account_id, "channel_id": channel_id}))
        return self._channel("connecting")

    def poll_channel(self, account_id, channel_id):
        self.calls.append(("poll_channel", {"account_id": account_id, "channel_id": channel_id}))
        return self._channel("connected")

    def remove_channel(self, account_id, channel_id):
        self.calls.append(("remove_channel", {"account_id": account_id, "channel_id": channel_id}))
        return self._channel("removed")

    def retry_connection(self, account_id, channel_id):
        self.calls.append(("retry_connection", {"account_id": account_id, "channel_id": channel_id}))
        return self._channel("connecting")

    def resolve_route(self, account_id):
        self.calls.append(("resolve_route", {"account_id": account_id}))
        return SimpleNamespace(
            id="route_1",
            account_id=account_id,
            channel_id="channel_1",
            provider_type="whatsapp_evolution",
            provider_address="whatsapp:+15555550123",
            route_key="whatsapp_evolution:whatsapp:+15555550123",
            lifecycle="active",
        )

    def _channel(self, state):
        return SimpleNamespace(
            id="channel_1",
            account_id="acct_1",
            provider_type="whatsapp_evolution",
            channel_identity_id="ci_1",
            lifecycle="removed" if state == "removed" else "active",
            connection_state=state,
            removable=True,
        )


class ErrorService(FakeReachabilityService):
    def remove_channel(self, account_id, channel_id):
        raise ChannelReachabilityError(
            "channel_identity_not_removable",
            fact={"type": "channel_identity_anchor", "account_id": account_id},
        )


def make_client(service=None):
    service = service or FakeReachabilityService()
    app = Flask(__name__)
    app.register_blueprint(create_channel_blueprint(service))
    return app.test_client(), service


def test_status_route_is_thin_service_adapter():
    client, service = make_client()

    response = client.get("/api/channels/status?account_id=acct_1")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "channel_id": "channel_1",
        "provider_type": "whatsapp_evolution",
        "connection_state": "connected",
        "reachable": True,
    }
    assert service.calls == [("get_status", {"account_id": "acct_1"})]


def test_channel_action_routes_delegate_to_service_methods():
    client, service = make_client()

    assert client.post(
        "/api/channels",
        json={
            "account_id": "acct_1",
            "provider_type": "whatsapp_evolution",
            "channel_identity_id": "ci_1",
            "removable": True,
        },
    ).status_code == 201
    assert client.post("/api/channels/channel_1/connect", json={"account_id": "acct_1"}).status_code == 200
    assert client.get("/api/channels/channel_1/poll?account_id=acct_1").status_code == 200
    assert client.post("/api/channels/channel_1/retry", json={"account_id": "acct_1"}).status_code == 200
    assert client.post("/api/channels/channel_1/remove", json={"account_id": "acct_1"}).status_code == 200
    assert client.get("/api/channels/resolve-route?account_id=acct_1").status_code == 200

    assert [call[0] for call in service.calls] == [
        "create_channel",
        "connect_channel",
        "poll_channel",
        "retry_connection",
        "remove_channel",
        "resolve_route",
    ]


@pytest.mark.parametrize("provider_type", ["wechat_ecloud", "linq"])
def test_create_route_rejects_retained_non_product_provider_before_service_call(provider_type):
    client, service = make_client()

    response = client.post(
        "/api/channels",
        json={
            "account_id": "acct_1",
            "provider_type": provider_type,
            "channel_identity_id": "ci_1",
            "removable": True,
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "unsupported_product_channel",
            "fact": {
                "type": "unsupported_product_channel",
                "provider_type": provider_type,
                "supported_provider_types": ["wechat_personal", "whatsapp_evolution"],
            },
        }
    }
    assert service.calls == []


def test_create_route_requires_boolean_removable_before_service_call():
    client, service = make_client()

    response = client.post(
        "/api/channels",
        json={
            "account_id": "acct_1",
            "provider_type": "whatsapp_evolution",
            "channel_identity_id": "ci_1",
            "removable": "false",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": "removable",
                "reason": "boolean_field_required",
            },
        }
    }
    assert service.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", 123),
        ("provider_type", []),
        ("provider_type", ""),
        ("channel_identity_id", {}),
    ],
)
def test_create_route_requires_string_body_fields_before_service_call(field, value):
    client, service = make_client()
    payload = {
        "account_id": "acct_1",
        "provider_type": "whatsapp_evolution",
        "channel_identity_id": "ci_1",
        "removable": True,
    }
    payload[field] = value

    response = client.post("/api/channels", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        }
    }
    assert service.calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/channels/channel_1/connect",
        "/api/channels/channel_1/remove",
        "/api/channels/channel_1/retry",
    ],
)
def test_channel_body_action_routes_require_string_account_id_before_service_call(path):
    client, service = make_client()

    response = client.post(path, json={"account_id": []})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": "account_id",
                "reason": "string_field_required",
            },
        }
    }
    assert service.calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/channels/status?account_id=",
        "/api/channels/channel_1/poll?account_id=",
        "/api/channels/resolve-route?account_id=",
    ],
)
def test_channel_query_routes_require_non_empty_account_id_before_service_call(path):
    client, service = make_client()

    response = client.get(path)

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "query",
                "field": "account_id",
                "reason": "string_field_required",
            },
        }
    }
    assert service.calls == []


def test_channel_route_errors_are_json():
    client, _service = make_client(service=ErrorService())

    response = client.post("/api/channels/channel_1/remove", json={"account_id": "acct_1"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "channel_identity_not_removable",
            "fact": {"type": "channel_identity_anchor", "account_id": "acct_1"},
        }
    }


def test_create_app_registers_channel_routes_only_when_service_is_supplied():
    settings = Settings(database_url=DATABASE_URL, redis_url=REDIS_URL, app_env="test")
    bare_app = create_app(settings=settings)
    assert bare_app.test_client().get("/api/channels/status?account_id=acct_1").status_code == 404

    service = FakeReachabilityService()
    app = create_app(settings=settings, channel_reachability_service=service)
    response = app.test_client().get("/api/channels/status?account_id=acct_1")

    assert response.status_code == 200


def test_create_app_registers_provider_webhooks_when_service_and_adapters_are_supplied():
    class FakeAdapter:
        provider_type = "whatsapp_evolution"

        def normalize_inbound(self, payload):
            return SimpleNamespace(
                provider_type="whatsapp_evolution",
                provider_subject=payload["sender"],
                text=payload.get("text", ""),
                raw_event_id=payload["message_id"],
                pairing_code=payload.get("pairing_code"),
            )

        def send_text(self, route, text, idempotency_key):
            raise AssertionError("webhook ingress must not send")

    service = FakeReachabilityService()

    def accept_provider_inbound(inbound):
        return SimpleNamespace(
            accepted=True,
            provider_type=inbound.provider_type,
            provider_subject=inbound.provider_subject,
            account_id="acct_1",
            channel_identity_id="ci_1",
            channel_id="channel_1",
            created_account=False,
            raw_event_id=inbound.raw_event_id,
        )

    service.accept_provider_inbound = accept_provider_inbound
    app = create_app(
        settings=Settings(database_url=DATABASE_URL, redis_url=REDIS_URL, app_env="test"),
        channel_reachability_service=service,
        provider_adapters={"whatsapp_evolution": FakeAdapter()},
    )

    response = app.test_client().post(
        "/webhooks/whatsapp/evolution",
        json={
            "message_id": "wa_msg_1",
            "sender": "whatsapp:+15555550123",
            "text": "hello",
        },
    )

    assert response.status_code == 202
    assert response.get_json()["account_id"] == "acct_1"
```

- [ ] **Step 2: Run the route tests to verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_channel_routes.py -v
```

Expected: fail during import because `coke.api.channel_routes` does not exist or `create_app` lacks `channel_reachability_service`.

- [ ] **Step 3: Add the thin channel blueprint**

Create `coke/api/channel_routes.py`:

```python
from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
)


def create_channel_blueprint(reachability_service) -> Blueprint:
    blueprint = Blueprint("channels", __name__, url_prefix="/api/channels")

    @blueprint.errorhandler(ChannelReachabilityError)
    def handle_channel_error(error: ChannelReachabilityError):
        return jsonify(_error_body(error.code, error.fact)), 400

    @blueprint.get("/status")
    def status():
        result = reachability_service.get_status(account_id=_query_str_field("account_id"))
        return jsonify(
            {
                "account_id": result.account_id,
                "channel_id": result.channel_id,
                "provider_type": result.provider_type,
                "connection_state": result.connection_state,
                "reachable": result.reachable,
            }
        )

    @blueprint.post("")
    def create():
        payload = _json_payload()
        provider_type = _body_str_field(payload, "provider_type")
        if provider_type not in PRODUCT_CHANNEL_PROVIDER_TYPES:
            raise ChannelReachabilityError(
                "unsupported_product_channel",
                fact={
                    "type": "unsupported_product_channel",
                    "provider_type": provider_type,
                    "supported_provider_types": sorted(PRODUCT_CHANNEL_PROVIDER_TYPES),
                },
            )
        channel = reachability_service.create_channel(
            account_id=_body_str_field(payload, "account_id"),
            provider_type=provider_type,
            channel_identity_id=_body_str_field(payload, "channel_identity_id"),
            removable=_body_bool_field(payload, "removable"),
        )
        return jsonify(_channel_body(channel)), 201

    @blueprint.post("/<channel_id>/connect")
    def connect(channel_id: str):
        payload = _json_payload()
        channel = reachability_service.connect_channel(
            account_id=_body_str_field(payload, "account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.get("/<channel_id>/poll")
    def poll(channel_id: str):
        channel = reachability_service.poll_channel(
            account_id=_query_str_field("account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.post("/<channel_id>/remove")
    def remove(channel_id: str):
        payload = _json_payload()
        channel = reachability_service.remove_channel(
            account_id=_body_str_field(payload, "account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.post("/<channel_id>/retry")
    def retry(channel_id: str):
        payload = _json_payload()
        channel = reachability_service.retry_connection(
            account_id=_body_str_field(payload, "account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.get("/resolve-route")
    def resolve_route():
        route = reachability_service.resolve_route(account_id=_query_str_field("account_id"))
        return jsonify(
            {
                "route_id": route.id,
                "account_id": route.account_id,
                "channel_id": route.channel_id,
                "provider_type": route.provider_type,
                "provider_address": route.provider_address,
                "route_key": route.route_key,
                "lifecycle": route.lifecycle,
            }
        )

    return blueprint


def _channel_body(channel) -> dict:
    return {
        "channel_id": channel.id,
        "account_id": channel.account_id,
        "provider_type": channel.provider_type,
        "channel_identity_id": channel.channel_identity_id,
        "lifecycle": channel.lifecycle,
        "connection_state": channel.connection_state,
        "removable": channel.removable,
    }


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "reason": "json_body_required",
            },
        )
    return payload


def _body_field(payload: dict, field: str):
    if field not in payload:
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    return payload[field]


def _body_bool_field(payload: dict, field: str) -> bool:
    value = _body_field(payload, field)
    if not isinstance(value, bool):
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "boolean_field_required",
            },
        )
    return value


def _body_str_field(payload: dict, field: str) -> str:
    value = _body_field(payload, field)
    if not isinstance(value, str) or value.strip() == "":
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value.strip()


def _query_str_field(field: str) -> str:
    value = request.args.get(field)
    if value is None:
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    if value.strip() == "":
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value.strip()


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body
```

- [ ] **Step 4: Register channel routes optionally in app factory**

Modify `coke/app.py`:

```python
from __future__ import annotations

from flask import Flask, jsonify

from coke.config import Settings


def create_app(
    settings: Settings,
    identity_access_service=None,
    channel_reachability_service=None,
    provider_adapters=None,
) -> Flask:
    app = Flask(__name__)
    app.config["COKE_SETTINGS"] = settings
    app.config["APP_ENV"] = settings.app_env

    if identity_access_service is not None:
        from coke.api.auth_routes import create_auth_blueprint
        from coke.api.claim_routes import create_claim_blueprint

        app.register_blueprint(create_auth_blueprint(identity_access_service))
        app.register_blueprint(create_claim_blueprint(identity_access_service))

    if channel_reachability_service is not None:
        from coke.api.channel_routes import create_channel_blueprint

        app.register_blueprint(create_channel_blueprint(channel_reachability_service))
        if provider_adapters is not None:
            from coke.api.provider_webhooks import create_provider_webhook_blueprint

            app.register_blueprint(
                create_provider_webhook_blueprint(
                    channel_reachability_service,
                    provider_adapters,
                )
            )

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app
```

- [ ] **Step 5: Run the route tests to verify they pass**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability/test_channel_routes.py -v
```

Expected: all channel route tests pass.

- [ ] **Step 6: Commit channel routes**

Run:

```bash
git add coke/api/channel_routes.py coke/app.py tests/unit/coke/channel_reachability/test_channel_routes.py
git commit -m "feat: add channel reachability routes"
```

Expected: commit succeeds.

## Task 5: Integrated ChannelReachability Verification

**Files:**
- Review: `coke/schema.py`
- Review: `coke/domains/channel_reachability/*`
- Review: `coke/providers/*`
- Review: `coke/api/channel_routes.py`
- Review: `coke/api/provider_webhooks.py`
- Review: `tests/unit/coke/channel_reachability/*`

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/channel_reachability tests/unit/coke/identity_access -v
```

Expected: all selected tests pass. This proves the in-memory repository contract, IdentityAccess read/anchor integration, API thinness, provider normalization, and route idempotency behavior.

- [ ] **Step 2: Run schema contract tests**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/test_clean_schema_contract.py -v
```

Expected: all selected tests pass. This confirms the existing SQL table names and unique indexes remain available for a future SQLAlchemy repository that implements the same repository protocol.

- [ ] **Step 3: Run backend surface verification**

Run:

```bash
zsh scripts/verify-surface clean-rebuild-backend
```

Expected: command exits 0. If it fails, classify the failure as product/runtime bug, test/eval bug, environment instability, or plan gap before editing.

- [ ] **Step 4: Run diff-aware verification routing**

Run:

```bash
: "${slice_base:?set slice_base to the pre-edit SHA captured in Preflight Step 3}"
zsh scripts/suggest-verification --base "$slice_base"
zsh scripts/review-trigger --base "$slice_base"
git diff --stat "$slice_base"..HEAD
```

Expected: `suggest-verification` prints the relevant surface commands for the whole ChannelReachability slice, `review-trigger` prints a non-blocking risk report, and `git diff --stat` shows the full slice range from the pre-edit `slice_base`. Copy the risk report summary and diff range into the handoff.

- [ ] **Step 5: Run repo structure checks and whitespace guard**

Run:

```bash
zsh scripts/check
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit final verification or documentation adjustments**

Run:

```bash
git status --short
git add coke/domains/channel_reachability coke/providers coke/api/channel_routes.py coke/api/provider_webhooks.py coke/app.py coke/domains/identity_access/service.py tests/unit/coke/channel_reachability tests/unit/coke/identity_access/test_identity_access_service.py
git commit -m "feat: complete channel reachability slice"
```

Expected: commit succeeds if Task 5 produced additional owned edits. If there are no changes after earlier task commits, record that no final commit was needed.

## Behavior Coverage Map

- ChannelReachability owns `channel`, `delivery_route`, and `delivery_attempt`: Task 2 repository and service own only those models.
- ChannelReachability does not write `channel_identity`: Task 2 no-write test snapshots `identity_service.repository.channel_identities_by_id`.
- Single active/reachable channel per account: Task 2 `test_single_active_channel_requires_remove_before_switch`.
- Switching requires removing old channel first when removable: Task 2 remove-then-create flow.
- States include `not_connected`, `connecting`, `connected`, `connection_failed`, `reconnection_required`, and `removed`: Task 2 models and lifecycle tests.
- Connecting is not reachable; connected is reachable: Task 2 `test_connecting_is_not_reachable_and_connected_is_reachable`.
- Account access gate for connection entry/actions: Task 2 `test_account_access_gate_blocks_channel_creation` plus `connect_channel` and `retry_connection` service gate.
- Account access is rechecked before connection completion: Task 2 `test_revoked_access_blocks_existing_channel_completion_from_webhook` and `mark_connected`.
- Removal consults IdentityAccess anchor check: Task 2 `test_non_removable_messaging_anchor_cannot_be_removed`.
- Removable web-first removal keeps account/reminders outside this slice and stops future reachability: Task 2 `test_removable_web_first_channel_removal_keeps_account_and_stops_reachability`.
- Retry and `reconnection_required`: Task 2 retry test.
- Reconnect creates or reuses route safely: Task 2 route-key reuse test.
- Removed channel no longer active: Task 2 status after removal.
- Delivery route resolves at send time: Task 2 stale-route prevention test.
- Active delivery routes are retired when a channel is removed while delivery attempt history remains tied to old routes: Task 2 remove/relink/same-address test and repository `retire_routes_for_channel`.
- Delivery attempt records provider fields, idempotency key, status, provider message id or error code, attempted time, and delivered time: Task 2 send tests.
- Failed/absent send is never delivered: Task 2 failed-provider and no-connected-channel tests.
- Provider adapter protocol follows parent contract exactly: Task 1 `ProviderAdapter`.
- Minimal provider modules for all retained adapters: Task 1 four adapter modules.
- Provider adapters reject malformed payloads with structured `invalid_provider_payload` errors: Task 1 missing-field and malformed-field tests for each adapter.
- `NormalizedInbound.payload` is a recursively immutable JSON evidence copy: Task 1 nested payload mutation and non-JSON rejection tests plus provider `freeze_json`.
- Product personal-channel providers are only `whatsapp_evolution` and `wechat_personal`: Task 1 retained/product constant test, Task 2 service allowlist tests, Task 3 webhook allowlist test, and Task 4 create-route allowlist test.
- Retained non-product adapters `wechat_ecloud` and `linq` normalize behind the provider protocol but cannot be connected or auto-bound as personal channels: Task 1 provider normalization tests and Task 2 retained-provider rejection tests.
- Provider-edge idempotency avoids duplicate adapter calls: Task 2 idempotency test.
- Provider-edge idempotency returns an existing attempt only for the current route/account and raises conflicts for same-key route switches or cross-account collisions: Task 2 idempotency conflict tests.
- Provider webhook normalizes inbound and resolves/binds identity through IdentityAccess without ConversationRuntime: Task 3 route tests and Task 2 `accept_provider_inbound`.
- Webhook binding fails closed before IdentityAccess writes for unsupported providers, retained non-product providers, revoked access, and active-channel conflicts: Task 2 rejection/no-write tests and IdentityAccess `preview_pairing_code_account`.
- Channel API routes are thin service adapters with JSON errors: Task 4 route tests.
- Channel API routes do not expose raw public prose sending; `send_text` remains an internal domain method for a future runtime-owned caller: Task 4 route scope and route tests.
- SQL persistence boundary remains preserved for a future slice: Task 2 protocol boundary and Task 5 schema contract verification.

## Self-Review

Spec coverage:

- Requirement rows 3 and 13 are covered by the one-active-channel tests, product provider allowlist, shared WhatsApp inbound binding, route resolution at send time, and no ConversationRuntime handoff from webhook ingress.
- Account access and channel reachability interactions are covered by creation gate tests, retry/connect service gates, webhook completion revocation test, and JSON error route tests.
- Message sending and outbound delivery are covered by route resolution at send time, provider-edge idempotency, sent/failed attempt records, and absent-send tests.
- Channel removal/relinking and account/data lifecycle are covered by non-removable messaging-anchor tests, removable web-first removal tests, retry/reconnection tests, removed-channel status tests, and identity no-write tests.
- Provider adapter boundary is covered by the exact `ProviderAdapter` protocol, all four retained adapter modules, retained/product provider constants, and webhook route normalization tests.

Placeholder scan:

- Before committing the implementation slice, run:

```bash
rg -n "T[O]DO|T[B]D|F[I]XME|implement la[t]er|fill in de[t]ails|add appropria[t]e|add valida[t]ion|handle edge ca[s]es|Similar to Ta[s]k" docs/superpowers/plans/2026-05-29-coke-clean-rebuild-channel-reachability.md coke/domains/channel_reachability coke/providers coke/api/channel_routes.py coke/api/provider_webhooks.py tests/unit/coke/channel_reachability tests/unit/coke/identity_access/test_identity_access_service.py
```

- Expected: no red-flag planning terms are reported.

Type and boundary consistency:

- `PRODUCT_CHANNEL_PROVIDER_TYPES` lives in `coke.domains.channel_reachability.models` and is imported by the service, channel route, and provider webhook route.
- `RETAINED_PROVIDER_TYPES` documents all provider adapters; it is not used to authorize personal channel creation.
- `ChannelReachabilityService.create_channel`, `accept_provider_inbound`, `coke/api/channel_routes.py`, and `coke/api/provider_webhooks.py` all reject retained non-product providers with `unsupported_product_channel`.
- `mark_connected` calls `_require_access(account_id)` before setting `connected`, resolving a route, or calling `observe_usable_channel`.
- `accept_provider_inbound` rejects unregistered and retained non-product providers before any IdentityAccess call that can create or bind `channel_identity`, so `wechat_ecloud` and `linq` inbound payloads cannot auto-create identities through this slice.
- Pairing-code inbound calls `preview_pairing_code_account` first, checks active channel conflicts before consuming the code, and only then calls the existing IdentityAccess bind/resolve method.
- The app factory examples instantiate `Settings(database_url=DATABASE_URL, redis_url=REDIS_URL, app_env="test")` so route tests match the required config contract.
- New runtime IDs use `uuid4().hex` defaults when callers do not inject deterministic test factories; no default ID generation is derived from wall-clock time.
