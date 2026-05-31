from dataclasses import FrozenInstanceError
import builtins
import importlib
import re
import sys

import pytest

POSTGRES_URL = "postgresql+psycopg://coke:pass@localhost:5432/coke"
REDIS_URL = "redis://localhost:6379/0"
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_settings_from_env_reads_required_urls_and_default_app_env(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.delenv("APP_ENV", raising=False)

    settings = Settings.from_env()

    assert settings.database_url == POSTGRES_URL
    assert settings.redis_url == REDIS_URL
    assert settings.app_env == "local"


def test_settings_from_env_reads_app_env(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("APP_ENV", "test")

    settings = Settings.from_env()

    assert settings.app_env == "test"


def test_settings_from_env_reads_runtime_entrypoint_configuration(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("COKE_PROVIDER_EVOLUTION_BASE_URL", "https://evolution.test")
    monkeypatch.setenv("COKE_PROVIDER_EVOLUTION_API_KEY", "evolution-key")
    monkeypatch.setenv("COKE_PROVIDER_EVOLUTION_INSTANCE", "coke")
    monkeypatch.setenv("SiliconFlow_API_KEY", "sf-key")
    monkeypatch.setenv("COKE_INTERACTION_MODEL", "custom/interaction")
    monkeypatch.setenv("COKE_INTERPRETER_MODEL", "custom/interpreter")
    monkeypatch.setenv("COKE_DETECTOR_MODEL", "custom/detector")
    monkeypatch.setenv("COKE_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("COKE_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("COKE_LOCK_TTL_MS", "45000")
    monkeypatch.setenv("COKE_WORK_STREAM", "coke.work.test")
    monkeypatch.setenv("COKE_WORK_GROUP", "workers-test")
    monkeypatch.setenv("COKE_WORK_CONSUMER", "worker-a")
    monkeypatch.setenv("COKE_REPLY_CHANNEL_PREFIX", "coke:reply:test")
    monkeypatch.setenv("COKE_WAITING_REPLY_AFTER_SECONDS", "12")
    monkeypatch.setenv("COKE_WEBHOOK_INBOUND_SECRET", "webhook-secret")
    monkeypatch.setenv("COKE_LLM_FAKE", "0")

    settings = Settings.from_env()

    assert settings.evolution_base_url == "https://evolution.test"
    assert settings.evolution_api_key == "evolution-key"
    assert settings.evolution_instance == "coke"
    assert settings.siliconflow_api_key == "sf-key"
    assert settings.interaction_model == "custom/interaction"
    assert settings.interpreter_model == "custom/interpreter"
    assert settings.detector_model == "custom/detector"
    assert settings.google_client_id == "google-client"
    assert settings.google_client_secret == "google-secret"
    assert settings.lock_ttl_ms == 45000
    assert settings.work_stream_name == "coke.work.test"
    assert settings.work_group_name == "workers-test"
    assert settings.work_consumer_name == "worker-a"
    assert settings.reply_channel_prefix == "coke:reply:test"
    assert settings.waiting_reply_after_seconds == 12
    assert settings.webhook_inbound_secret == "webhook-secret"
    assert settings.llm_fake is False


def test_settings_from_env_allows_fake_llm_without_siliconflow_key(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("COKE_LLM_FAKE", "1")
    monkeypatch.delenv("SiliconFlow_API_KEY", raising=False)

    settings = Settings.from_env()

    assert settings.llm_fake is True
    assert settings.siliconflow_api_key is None


def test_settings_from_env_requires_siliconflow_key_for_real_llm(monkeypatch):
    from coke.config import ConfigurationError, Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("COKE_LLM_FAKE", raising=False)
    monkeypatch.delenv("SiliconFlow_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="SiliconFlow_API_KEY"):
        Settings.from_env()


def test_settings_from_env_rejects_invalid_lock_ttl(monkeypatch):
    from coke.config import ConfigurationError, Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("COKE_LLM_FAKE", "1")
    monkeypatch.setenv("COKE_LOCK_TTL_MS", "0")

    with pytest.raises(ConfigurationError, match="COKE_LOCK_TTL_MS"):
        Settings.from_env()


def test_settings_from_env_fails_closed_without_database_url(monkeypatch):
    from coke.config import ConfigurationError, Settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)

    with pytest.raises(ConfigurationError, match="DATABASE_URL is required"):
        Settings.from_env()


def test_settings_from_env_fails_closed_without_redis_url(monkeypatch):
    from coke.config import ConfigurationError, Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(ConfigurationError, match="REDIS_URL is required"):
        Settings.from_env()


def test_create_app_exposes_health_and_registers_settings():
    from flask import Flask

    from coke.app import create_app
    from coke.config import Settings

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    app = create_app(settings)

    assert isinstance(app, Flask)
    assert app.config["COKE_SETTINGS"] is settings
    assert app.config["APP_ENV"] == "test"
    assert app.test_client().get("/healthz").get_json() == {"ok": True}


def test_create_app_does_not_start_network_services(monkeypatch):
    from coke.app import create_app
    from coke.config import Settings
    from coke.infra import postgres, redis

    def forbidden_postgres_call(settings):
        raise AssertionError("create_app must not create a Postgres engine")

    def forbidden_redis_call(settings):
        raise AssertionError("create_app must not create a Redis client")

    monkeypatch.setattr(postgres, "create_engine", forbidden_postgres_call)
    monkeypatch.setattr(redis, "create_redis_client", forbidden_redis_call)

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    app = create_app(settings)

    assert app.test_client().get("/healthz").status_code == 200


def test_create_app_commits_composed_session_after_success_and_rolls_back_errors():
    from types import SimpleNamespace

    from coke.app import create_app
    from coke.config import Settings

    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    session = FakeSession()
    runtime = SimpleNamespace(
        identity_access_service=None,
        channel_reachability_service=None,
        reminder_service=None,
        social_scheduling_service=None,
        calendar_import_service=None,
        provider_adapters=None,
        conversation_runtime_service=None,
        session=session,
    )
    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    app = create_app(settings, composed_runtime=runtime)

    @app.get("/bad-request")
    def bad_request():
        return {"error": "bad"}, 400

    client = app.test_client()
    assert client.get("/healthz").status_code == 200
    assert session.commits == 1
    assert session.rollbacks == 0

    assert client.get("/bad-request").status_code == 400
    assert session.commits == 1
    assert session.rollbacks == 1


def test_postgres_factories_are_lazy(monkeypatch):
    from coke.config import Settings
    from coke.infra import postgres

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    calls = []
    fake_engine = object()

    def fake_create_engine(url, **kwargs):
        calls.append(("engine", url, kwargs))
        return fake_engine

    class FakeSessionFactory:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_sessionmaker(**kwargs):
        calls.append(("sessionmaker", kwargs))
        return FakeSessionFactory(**kwargs)

    monkeypatch.setattr(postgres, "sqlalchemy_create_engine", fake_create_engine)
    monkeypatch.setattr(postgres, "sessionmaker", fake_sessionmaker)

    assert calls == []
    engine = postgres.create_engine(settings)
    session_factory = postgres.create_session_factory(engine)

    assert engine is fake_engine
    assert session_factory.kwargs["bind"] is fake_engine
    assert calls[0][0] == "engine"
    assert calls[0][1] == POSTGRES_URL
    assert calls[0][2]["pool_pre_ping"] is True
    assert calls[1][0] == "sessionmaker"
    assert calls[1][1]["bind"] is fake_engine
    assert calls[1][1]["autoflush"] is False
    assert calls[1][1]["autocommit"] is False
    assert calls[1][1]["expire_on_commit"] is False


def test_redis_factory_is_lazy(monkeypatch):
    from coke.config import Settings
    from coke.infra import redis as redis_infra

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    calls = []
    fake_client = object()

    class FakeRedis:
        @staticmethod
        def from_url(url, **kwargs):
            calls.append((url, kwargs))
            return fake_client

    monkeypatch.setattr(redis_infra.redis_lib, "Redis", FakeRedis)

    assert calls == []
    client = redis_infra.create_redis_client(settings)

    assert client is fake_client
    assert calls == [(REDIS_URL, {"decode_responses": True})]


def test_outbox_event_is_immutable_and_carries_traceparent():
    from coke.infra.outbox import OutboxEvent

    event = OutboxEvent(
        id="evt_1",
        topic="turn.inbound",
        idempotency_key="inbound:provider-message-1",
        payload={
            "trigger_id": "inbound:provider-message-1",
            "nested": {
                "attempts": [1, 2],
                "status": "queued",
                "count": 2,
                "sampled": True,
                "optional": None,
            },
        },
        traceparent=TRACEPARENT,
    )

    assert event.id == "evt_1"
    assert event.topic == "turn.inbound"
    assert event.idempotency_key == "inbound:provider-message-1"
    assert event.payload["trigger_id"] == "inbound:provider-message-1"
    assert event.payload["nested"]["attempts"] == (1, 2)
    assert event.payload["nested"]["status"] == "queued"
    assert event.payload["nested"]["count"] == 2
    assert event.payload["nested"]["sampled"] is True
    assert event.payload["nested"]["optional"] is None
    assert event.traceparent == TRACEPARENT
    assert event.created_at.tzinfo is not None

    with pytest.raises(FrozenInstanceError):
        event.topic = "changed"
    with pytest.raises(TypeError):
        event.payload["new"] = "value"
    with pytest.raises(TypeError):
        event.payload["nested"]["extra"] = "value"
    with pytest.raises(TypeError):
        event.payload["nested"]["attempts"][0] = 99


def test_outbox_event_requires_mapping_payload():
    from coke.infra.outbox import OutboxEvent

    with pytest.raises(TypeError, match="payload must be a JSON object mapping"):
        OutboxEvent(
            id="evt_1",
            topic="turn.inbound",
            idempotency_key="inbound:provider-message-1",
            payload=["not", "an", "object"],
            traceparent=TRACEPARENT,
        )


def test_outbox_event_rejects_non_json_like_payload_values():
    from coke.infra.outbox import OutboxEvent

    with pytest.raises(TypeError, match="payload.unsupported must be JSON-like"):
        OutboxEvent(
            id="evt_1",
            topic="turn.inbound",
            idempotency_key="inbound:provider-message-1",
            payload={"unsupported": object()},
            traceparent=TRACEPARENT,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_outbox_event_rejects_non_finite_float_payload_values(value):
    from coke.infra.outbox import OutboxEvent

    with pytest.raises(TypeError, match="payload.value must be JSON-like"):
        OutboxEvent(
            id="evt_1",
            topic="turn.inbound",
            idempotency_key="inbound:provider-message-1",
            payload={"value": value},
            traceparent=TRACEPARENT,
        )


def test_outbox_event_requires_string_payload_keys():
    from coke.infra.outbox import OutboxEvent

    with pytest.raises(TypeError, match="payload keys must be strings"):
        OutboxEvent(
            id="evt_1",
            topic="turn.inbound",
            idempotency_key="inbound:provider-message-1",
            payload={1: "not-json-object-key"},
            traceparent=TRACEPARENT,
        )


@pytest.mark.parametrize(
    ("field_name", "kwargs", "message"),
    [
        ("topic", {"topic": " "}, "topic must not be blank"),
        (
            "idempotency_key",
            {"idempotency_key": " "},
            "idempotency_key must not be blank",
        ),
    ],
)
def test_outbox_event_rejects_blank_required_fields(field_name, kwargs, message):
    from coke.infra.outbox import OutboxEvent

    values = {
        "id": "evt_1",
        "topic": "turn.inbound",
        "idempotency_key": "inbound:provider-message-1",
        "payload": {"trigger_id": "inbound:provider-message-1"},
        "traceparent": TRACEPARENT,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        OutboxEvent(**values)


def test_traceparent_helpers_validate_extract_and_generate():
    from coke.infra import tracing

    assert tracing.is_valid_traceparent(TRACEPARENT) is True
    assert tracing.extract_trace_id(TRACEPARENT) == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert (
        tracing.is_valid_traceparent(
            "00-00000000000000000000000000000000-00f067aa0ba902b7-01"
        )
        is False
    )
    assert (
        tracing.is_valid_traceparent(
            "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"
        )
        is False
    )

    generated = tracing.generate_traceparent()

    assert tracing.is_valid_traceparent(generated) is True
    assert re.fullmatch(
        r"00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]",
        generated,
    )
    assert tracing.ensure_traceparent(TRACEPARENT) == TRACEPARENT
    assert tracing.is_valid_traceparent(tracing.ensure_traceparent(None)) is True

    with pytest.raises(ValueError, match="Invalid W3C traceparent"):
        tracing.extract_trace_id("not-a-traceparent")


def test_traceparent_generation_retries_all_zero_random_parts(monkeypatch):
    from coke.infra import tracing

    uuid_values = iter(
        [
            type("FakeUUID", (), {"hex": "0" * 32})(),
            type("FakeUUID", (), {"hex": "4bf92f3577b34da6a3ce929d0e0e4736"})(),
        ]
    )
    token_values = iter(["0" * 16, "00f067aa0ba902b7"])

    monkeypatch.setattr(tracing.uuid, "uuid4", lambda: next(uuid_values))
    monkeypatch.setattr(tracing.secrets, "token_hex", lambda length: next(token_values))

    generated = tracing.generate_traceparent()

    assert generated == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_traceparent_generation_bounds_all_zero_trace_id_retries(monkeypatch):
    from coke.infra import tracing

    calls = 0

    def always_zero_uuid():
        nonlocal calls
        calls += 1
        if calls > 20:
            raise AssertionError("trace ID generation was not bounded")
        return type("FakeUUID", (), {"hex": "0" * 32})()

    monkeypatch.setattr(tracing.uuid, "uuid4", always_zero_uuid)

    with pytest.raises(RuntimeError, match="Unable to generate non-zero trace ID"):
        tracing.generate_traceparent()


def test_traceparent_generation_bounds_all_zero_span_id_retries(monkeypatch):
    from coke.infra import tracing

    calls = 0

    def always_zero_span(length):
        nonlocal calls
        calls += 1
        if calls > 20:
            raise AssertionError("span ID generation was not bounded")
        return "0" * 16

    monkeypatch.setattr(
        tracing.uuid,
        "uuid4",
        lambda: type("FakeUUID", (), {"hex": "4bf92f3577b34da6a3ce929d0e0e4736"})(),
    )
    monkeypatch.setattr(tracing.secrets, "token_hex", always_zero_span)

    with pytest.raises(RuntimeError, match="Unable to generate non-zero span ID"):
        tracing.generate_traceparent()


@pytest.mark.parametrize(
    ("uuid_hex", "span_hex", "message"),
    [
        ("not-a-trace-id", "00f067aa0ba902b7", "trace ID producer emitted invalid hex"),
        (
            "4bf92f3577b34da6a3ce929d0e0e4736",
            "notspan",
            "span ID producer emitted invalid hex",
        ),
    ],
)
def test_traceparent_generation_rejects_invalid_random_part_shape(
    monkeypatch,
    uuid_hex,
    span_hex,
    message,
):
    from coke.infra import tracing

    monkeypatch.setattr(
        tracing.uuid,
        "uuid4",
        lambda: type("FakeUUID", (), {"hex": uuid_hex})(),
    )
    monkeypatch.setattr(tracing.secrets, "token_hex", lambda length: span_hex)

    with pytest.raises(RuntimeError, match=message):
        tracing.generate_traceparent()


def test_coke_package_does_not_import_legacy_runtime_modules(monkeypatch):
    imported_forbidden = []
    real_import = builtins.__import__

    def tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.partition(".")[0]
        if root in {"dao", "connector", "gateway"}:
            imported_forbidden.append(name)
            raise AssertionError(f"coke package imported legacy module {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", tracking_import)
    for module_name in list(sys.modules):
        if module_name == "coke" or module_name.startswith("coke."):
            del sys.modules[module_name]

    for module_name in (
        "coke",
        "coke.app",
        "coke.config",
        "coke.infra",
        "coke.infra.postgres",
        "coke.infra.redis",
        "coke.infra.outbox",
        "coke.infra.tracing",
    ):
        importlib.import_module(module_name)

    assert imported_forbidden == []
