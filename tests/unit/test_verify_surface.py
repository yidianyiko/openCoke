from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


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

    assert result.returncode == 0, result.stdout + result.stderr
    assert "== repo-os ==" in result.stdout
    assert (
        ".venv/bin/python -m pytest tests/unit/test_repo_os_structure.py -v"
        in result.stdout
    )
    assert "zsh scripts/check" in result.stdout
    assert "== bridge ==" in result.stdout
    assert (
        ".venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/ -v"
        in result.stdout
    )
    assert (
        ".venv/bin/python -m pytest "
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
