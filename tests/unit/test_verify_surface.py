from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def expected_pytest_cmd() -> str:
    if (ROOT / ".venv" / "bin" / "python").exists():
        return ".venv/bin/python -m pytest"
    return "python -m pytest"


def run_verify_surface(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["zsh", "scripts/verify-surface", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_verify_surface_dry_run_prints_repo_os_and_bridge_commands():
    result = run_verify_surface("--dry-run", "repo-os", "bridge")
    pytest_cmd = expected_pytest_cmd()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "== repo-os ==" in result.stdout
    assert f"{pytest_cmd} tests/unit/test_repo_os_structure.py -v" in result.stdout
    assert f"{pytest_cmd} tests/unit/test_guardrail_scripts.py -v" in result.stdout
    assert "zsh scripts/check" in result.stdout
    assert "== bridge ==" in result.stdout
    assert (
        f"{pytest_cmd} tests/unit/connector/clawscale_bridge/ -v"
        in result.stdout
    )
    assert (
        f"{pytest_cmd} "
        "tests/unit/agent/test_message_util_clawscale_routing.py -v"
        in result.stdout
    )


def test_verify_surface_dry_run_prints_gateway_and_deploy_commands():
    result = run_verify_surface("--dry-run", "gateway-api", "gateway-web", "deploy")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "pnpm --dir gateway/packages/api test" in result.stdout
    assert "pnpm --dir gateway/packages/web test" in result.stdout
    assert "bash scripts/test-deploy-compose-to-gcp.sh" in result.stdout


def test_verify_surface_rejects_unknown_surface():
    result = run_verify_surface("--dry-run", "made-up-surface")

    assert result.returncode != 0
    assert "unknown_surface:made-up-surface" in result.stderr


def test_verify_surface_dry_run_prints_product_surface_commands():
    result = run_verify_surface(
        "--dry-run",
        "product-reminder",
        "product-calendar-import",
        "product-timezone",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/unit/agent/test_reminder" in result.stdout
    assert "calendar_import" in result.stdout
    assert "timezone" in result.stdout


def test_verify_surface_dry_run_prints_clean_rebuild_commands():
    result = run_verify_surface(
        "--dry-run",
        "clean-rebuild-docs",
        "clean-rebuild-backend",
        "clean-rebuild-web",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "== clean-rebuild-docs ==" in result.stdout
    assert "bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh" in result.stdout
    assert "zsh scripts/check" in result.stdout
    assert "== clean-rebuild-backend ==" in result.stdout
    assert f"{expected_pytest_cmd()} tests/unit/coke -v" in result.stdout.splitlines()
    assert "== clean-rebuild-web ==" in result.stdout
    assert "cd gateway && pnpm --filter @coke/web test" in result.stdout
    assert "cd gateway && pnpm --filter @coke/web build" in result.stdout
