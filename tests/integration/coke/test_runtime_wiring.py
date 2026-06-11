from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import fakeredis
import pytest
import yaml

from coke.config import Settings

TEST_DATABASE_URL = "postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql"


def _database_url() -> str:
    return os.environ.get("COKE_TEST_DATABASE_URL") or TEST_DATABASE_URL


def _settings() -> Settings:
    return Settings(
        database_url=_database_url(),
        redis_url="redis://localhost:6379/15",
        app_env="test",
        llm_fake=True,
        work_stream_name="coke.work.test",
        work_group_name="workers-test",
        work_consumer_name="worker-test",
    )


def test_build_runtime_from_settings_wires_postgres_redis_providers_and_app():
    from coke.app import create_app
    from coke.composition import build_runtime_from_settings
    from coke.domains.conversation_runtime.repository import (
        PostgresConversationRuntimeRepository,
    )

    redis_client = fakeredis.FakeRedis(decode_responses=True)

    runtime = build_runtime_from_settings(_settings(), redis_client=redis_client)
    app = create_app(_settings(), composed_runtime=runtime)

    assert isinstance(
        runtime.repositories.conversation_runtime,
        PostgresConversationRuntimeRepository,
    )
    assert runtime.turn_runner is not None
    assert "whatsapp_evolution" in runtime.provider_adapters
    assert runtime.work_stream.stream_name == "coke.work.test"
    assert app.test_client().get("/healthz").get_json() == {"ok": True}
    assert "/webhooks/whatsapp/evolution" in {
        rule.rule for rule in app.url_map.iter_rules()
    }


def test_runtime_wires_media_text_resolver_when_media_models_are_configured(
    monkeypatch,
):
    from coke.composition import build_runtime_from_settings

    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        zai_api_key="zai-key",
        siliconflow_api_key="sf-key",
        llm_fake=False,
        asr_model="sensevoice-candidate",
        vision_text_model="qwen-vl-candidate",
    )

    runtime = build_runtime_from_settings(
        settings, redis_client=fakeredis.FakeRedis(decode_responses=True)
    )

    assert runtime.media_text_resolver is not None
    assert runtime.turn_runner.interaction_agent.model.api_key == "zai-key"
    assert runtime.turn_pipeline._planner.client.model.api_key == "zai-key"
    assert runtime.reminder_service.detector.client.model.api_key == "zai-key"
    assert runtime.media_text_resolver.asr_client.api_key == "sf-key"
    assert runtime.media_text_resolver.vision_text_client.api_key == "sf-key"


def test_wsgi_import_builds_app_with_fake_llm_without_live_model(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _database_url())
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("COKE_LLM_FAKE", "1")
    monkeypatch.setenv("COKE_WORK_STREAM", "coke.work.test")
    monkeypatch.setenv("COKE_WORK_GROUP", "workers-test")
    monkeypatch.setenv("COKE_WORK_CONSUMER", "worker-test")
    sys.modules.pop("coke.api.wsgi", None)

    module = importlib.import_module("coke.api.wsgi")

    assert module.app.test_client().get("/healthz").status_code == 200
    assert module.runtime.turn_runner is not None


def test_entrypoint_modules_import_and_construct_loops_without_running(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _database_url())
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("COKE_LLM_FAKE", "1")

    worker_main = importlib.import_module("coke.worker.__main__")
    scheduler_main = importlib.import_module("coke.scheduler.__main__")
    outbox_main = importlib.import_module("coke.worker.outbox_relay")

    assert callable(worker_main.run_worker_loop)
    assert callable(scheduler_main.run_scheduler)
    assert callable(outbox_main.run_outbox_relay_loop)


def test_production_compose_uses_real_entrypoint_commands_and_migration_gate():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text())
    services = compose["services"]

    assert services["coke-migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["coke-api"]["command"] == [
        "gunicorn",
        "coke.api.wsgi:app",
        "-b",
        "0.0.0.0:8000",
        "-w",
        "2",
    ]
    assert services["coke-worker"]["command"] == ["python", "-m", "coke.worker"]
    assert services["coke-scheduler"]["command"] == ["python", "-m", "coke.scheduler"]
    assert services["coke-outbox-relay"]["command"] == [
        "python",
        "-m",
        "coke.worker.outbox_relay",
    ]
    for service_name in (
        "coke-api",
        "coke-worker",
        "coke-scheduler",
        "coke-outbox-relay",
    ):
        assert services[service_name]["depends_on"]["coke-migrate"] == {
            "condition": "service_completed_successfully"
        }
    dockerfile = Path("Dockerfile").read_text()
    assert "gunicorn" in dockerfile
    assert "coke.api.wsgi:app" in dockerfile
    assert "COPY . ." in dockerfile
