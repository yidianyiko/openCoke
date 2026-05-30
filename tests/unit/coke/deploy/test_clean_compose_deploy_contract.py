from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
COMPOSE_CLEAN = ROOT / "docker-compose.clean.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-compose-to-gcp.sh"
DOCKERIGNORE = ROOT / ".dockerignore"


def _clean_compose() -> dict:
    return yaml.safe_load(COMPOSE_CLEAN.read_text())


def _service_env(service: dict) -> dict:
    environment = service.get("environment", {})
    if isinstance(environment, list):
        return dict(item.split("=", 1) for item in environment)
    return environment


def test_clean_compose_binds_only_non_disruptive_localhost_ports() -> None:
    services = _clean_compose()["services"]

    assert services["postgres"]["ports"] == [
        "127.0.0.1:${COKE_CLEAN_POSTGRES_PORT:-55432}:5432"
    ]
    assert services["redis"]["ports"] == [
        "127.0.0.1:${COKE_CLEAN_REDIS_PORT:-56379}:6379"
    ]
    assert services["coke-api"]["ports"] == [
        "127.0.0.1:${COKE_CLEAN_API_PORT:-8000}:8000"
    ]
    assert services["coke-web"]["ports"] == [
        "127.0.0.1:${COKE_CLEAN_WEB_PORT:-4042}:4040"
    ]


def test_clean_compose_uses_distinct_clean_volume_names() -> None:
    volumes = _clean_compose()["volumes"]

    assert volumes["postgres_data"]["name"] == "coke_clean_postgres_data"
    assert volumes["redis_data"]["name"] == "coke_clean_redis_data"


def test_clean_runtime_services_use_internal_postgres_redis_and_real_llm_env() -> None:
    services = _clean_compose()["services"]
    runtime_services = (
        "coke-api",
        "coke-worker",
        "coke-scheduler",
        "coke-outbox-relay",
    )

    for service_name in runtime_services:
        environment = _service_env(services[service_name])
        assert (
            environment["DATABASE_URL"]
            == "postgresql+psycopg://coke:coke@postgres:5432/coke"
        )
        assert environment["REDIS_URL"] == "redis://redis:6379/0"
        assert environment["APP_ENV"] == "production"
        assert environment["AGNO_TELEMETRY"] == "false"
        assert environment["COKE_AGNO_CREATE_SCHEMA"] == "1"
        assert "COKE_LLM_FAKE" not in environment


def test_clean_api_and_worker_can_reach_host_evolution_instance() -> None:
    services = _clean_compose()["services"]

    assert services["coke-api"]["extra_hosts"] == [
        "host.docker.internal:host-gateway"
    ]
    assert services["coke-worker"]["extra_hosts"] == [
        "host.docker.internal:host-gateway"
    ]


def test_clean_web_is_optional_for_stage1_default_deploy() -> None:
    services = _clean_compose()["services"]
    script = DEPLOY_SCRIPT.read_text()

    assert services["coke-web"]["profiles"] == ["web"]
    assert '--profile web rm -sf coke-web' in script


def test_deploy_script_targets_clean_project_without_legacy_gateway_logic() -> None:
    script = DEPLOY_SCRIPT.read_text()

    assert 'REMOTE_ROOT="${REMOTE_ROOT:-/home/whoami/coke-clean}"' in script
    assert 'PROJECT_NAME="${PROJECT_NAME:-coke-clean}"' in script
    assert 'COKE_CLEAN_API_PORT="${COKE_CLEAN_API_PORT:-8000}"' in script
    assert 'COKE_CLEAN_WEB_PORT="${COKE_CLEAN_WEB_PORT:-4042}"' in script
    assert 'COKE_CLEAN_POSTGRES_PORT="${COKE_CLEAN_POSTGRES_PORT:-55432}"' in script
    assert 'COKE_CLEAN_REDIS_PORT="${COKE_CLEAN_REDIS_PORT:-56379}"' in script
    assert "--dry-run" in script
    assert "rsync" in script
    for included in (
        "coke/",
        "web/",
        "migrations/",
        "docker-compose.prod.yml",
        "docker-compose.clean.yml",
        "Dockerfile",
        ".dockerignore",
        "requirements.txt",
        "alembic.ini",
        "deploy/",
        "scripts/",
    ):
        assert included in script
    for excluded in (
        ".git",
        ".venv",
        ".worktrees",
        ".env",
        "__pycache__",
        "node_modules",
        ".pnpm-store",
    ):
        assert f"--exclude={excluded}" in script
    assert (
        'docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml '
        "-f docker-compose.clean.yml up -d --build"
    ) in script
    assert "alembic upgrade head" in script
    assert 'curl -fsS "http://127.0.0.1:${COKE_CLEAN_API_PORT}/healthz"' in script
    lowered = script.lower()
    for legacy_term in (
        "verify_gateway_submodule_match",
        "sync_gateway_submodule",
        "git submodule",
        "pymongo",
        "memo_runtime",
    ):
        assert legacy_term not in lowered


def test_docker_build_context_excludes_clean_web_package_caches() -> None:
    dockerignore = DOCKERIGNORE.read_text()
    script = DEPLOY_SCRIPT.read_text()

    assert '".dockerignore"' in script
    assert "web/node_modules" in dockerignore
    assert "web/.pnpm-store" in dockerignore
