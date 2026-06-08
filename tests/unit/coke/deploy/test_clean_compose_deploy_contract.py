from __future__ import annotations

import re
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


def _script_array(script: str, name: str) -> str:
    match = re.search(rf"{name}=\(\n(?P<body>.*?)\n\)", script, re.DOTALL)
    assert match is not None, f"missing {name} array"
    return match.group("body")


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
        assert (
            environment["COKE_PUBLIC_BASE_URL"]
            == "${COKE_PUBLIC_BASE_URL:-https://coke.keep4oforever.com}"
        )
        assert "COKE_LLM_FAKE" not in environment


def test_clean_api_and_worker_can_reach_host_evolution_instance() -> None:
    services = _clean_compose()["services"]

    assert services["coke-api"]["extra_hosts"] == ["host.docker.internal:host-gateway"]
    assert services["coke-worker"]["extra_hosts"] == [
        "host.docker.internal:host-gateway"
    ]


def test_clean_web_is_part_of_default_compose_stack() -> None:
    services = _clean_compose()["services"]
    script = DEPLOY_SCRIPT.read_text()

    assert "profiles" not in services["coke-web"]
    assert "coke-web" in services
    assert "--profile web rm -sf coke-web" not in script
    assert 'curl -fsS "http://127.0.0.1:${COKE_CLEAN_WEB_PORT}/auth/login"' in script


def test_deploy_script_tracks_last_deployed_sha_for_differential_plan() -> None:
    script = DEPLOY_SCRIPT.read_text()

    assert 'DEPLOYED_SHA_FILE="${REMOTE_ROOT}/.deployed-sha"' in script
    assert 'LOCAL_SHA="$(git -C "$LOCAL_ROOT" rev-parse HEAD)"' in script
    assert 'git -C "$LOCAL_ROOT" diff --name-only' in script
    assert 'printf \'%s\\n\' "$LOCAL_SHA" > "$DEPLOYED_SHA_FILE"' in script
    assert "record_deployed_sha()" in script
    assert script.count("record_deployed_sha") >= 3
    assert "write_remote_deployed_sha()" in script
    assert script.count("write_remote_deployed_sha") >= 2


def test_deploy_script_backend_only_plan_skips_coke_web_recreate() -> None:
    script = DEPLOY_SCRIPT.read_text()

    backend_services = _script_array(script, "BACKEND_DEPLOY_SERVICES")

    for service in ("coke-api", "coke-worker", "coke-scheduler", "coke-outbox-relay"):
        assert f'"{service}"' in backend_services
    assert "coke-web" not in backend_services
    assert "DEPLOY_TIER=backend" in script
    assert 'recreate_services "${BACKEND_DEPLOY_SERVICES[@]}"' in script


def test_deploy_script_recreates_coke_web_only_for_web_or_full_plan() -> None:
    script = DEPLOY_SCRIPT.read_text()

    web_services = _script_array(script, "WEB_DEPLOY_SERVICES")

    assert web_services.strip() == '"coke-web"'
    assert "DEPLOY_TIER=web" in script
    assert "DEPLOY_TIER=full" in script
    assert 'recreate_services "${WEB_DEPLOY_SERVICES[@]}"' in script
    assert "force-recreate coke-web" not in script


def test_deploy_script_fails_if_selected_service_list_is_empty() -> None:
    script = DEPLOY_SCRIPT.read_text()

    assert "require_services()" in script
    assert 'require_services "backend" "${BACKEND_DEPLOY_SERVICES[@]}"' in script
    assert 'require_services "web" "${WEB_DEPLOY_SERVICES[@]}"' in script
    assert "would skip a required recreate" in script


def test_deploy_script_noops_when_no_relevant_paths_changed() -> None:
    script = DEPLOY_SCRIPT.read_text()

    assert "DEPLOY_TIER=none" in script
    assert "no relevant deploy changes detected" in script
    assert "exit 0" in script


def test_deploy_script_has_no_rollback_snapshot_commands() -> None:
    script = DEPLOY_SCRIPT.read_text().lower()

    for forbidden in (
        "pg_dump",
        "tar -",
        "tar czf",
        "tar -czf",
        "snapshot",
        "rollback",
    ):
        assert forbidden not in script


def test_backend_only_deploy_preserves_next_build_output_without_web_rebuild() -> None:
    script = DEPLOY_SCRIPT.read_text()

    assert "--exclude=.next" in script
    assert '"web/"' not in _script_array(script, "BACKEND_RSYNC_SOURCES")
    assert '"web/"' in _script_array(script, "WEB_RSYNC_SOURCES")


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
        ".next",
    ):
        assert f"--exclude={excluded}" in script
    assert "compose up -d postgres redis" in script
    assert "compose up -d --build --no-deps --force-recreate" in script
    assert "alembic upgrade head" in script
    assert "alembic check" in script
    assert script.index("alembic upgrade head") < script.index("alembic check")
    assert 'curl -fsS "http://127.0.0.1:${COKE_CLEAN_API_PORT}/healthz"' in script
    assert 'curl -fsS "http://127.0.0.1:${COKE_CLEAN_WEB_PORT}/auth/login"' in script
    assert "COKE_PUBLIC_BASE_URL=https://coke.keep4oforever.com" in script
    assert script.index(
        "COKE_PUBLIC_BASE_URL=https://coke.keep4oforever.com"
    ) < script.index("NEXT_PUBLIC_API_BASE_URL=https://coke.keep4oforever.com")
    lowered = script.lower()
    for legacy_term in (
        "verify_gateway_submodule_match",
        "sync_gateway_submodule",
        "git submodule",
        "pymongo",
        "memo_runtime",
    ):
        assert legacy_term not in lowered


def test_deploy_script_writes_zai_key_for_official_text_glm_provider() -> None:
    script = DEPLOY_SCRIPT.read_text()

    assert 'zai_api_key="$(read_env ZAI_API_KEY)"' in script
    assert '[[ -n "$zai_api_key" ]] || missing+=("ZAI_API_KEY")' in script
    assert "ZAI_API_KEY=${zai_api_key}" in script
    assert "SiliconFlow_API_KEY=${siliconflow_api_key}" in script
    assert 'missing+=("SiliconFlow_API_KEY")' not in script


def test_docker_build_context_excludes_clean_web_package_caches() -> None:
    dockerignore = DOCKERIGNORE.read_text()
    script = DEPLOY_SCRIPT.read_text()

    assert '".dockerignore"' in script
    assert "web/node_modules" in dockerignore
    assert "web/.pnpm-store" in dockerignore
