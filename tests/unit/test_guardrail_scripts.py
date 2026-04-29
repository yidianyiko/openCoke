from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def run_script(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["zsh", script, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_suggest_verification_maps_changed_files_to_existing_surface_commands():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "agent/runner/agent_runner.py",
        "--files",
        "connector/clawscale_bridge/app.py",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed_surfaces: worker-runtime bridge" in result.stdout
    assert "zsh scripts/verify-surface worker-runtime bridge" in result.stdout
    assert "pytest tests/unit/runner/ -v" in result.stdout
    assert "pytest tests/unit/connector/clawscale_bridge/ -v" in result.stdout


def test_suggest_verification_deduplicates_and_orders_surfaces_by_config():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "gateway/packages/web/app/page.tsx",
        "--files",
        "docs/fitness/README.md",
        "--files",
        "gateway/packages/web/components/button.tsx",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed_surfaces: gateway-web repo-os" in result.stdout
    assert "zsh scripts/verify-surface gateway-web repo-os" in result.stdout


def test_review_trigger_flags_cross_boundary_and_missing_task_evidence():
    result = run_script(
        "scripts/review-trigger",
        "--files",
        "connector/clawscale_bridge/app.py",
        "--files",
        "gateway/packages/api/src/routes/outbound.ts",
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "human_review_required: yes" in result.stdout
    assert "cross_boundary_bridge_gateway" in result.stdout
    assert "task_evidence_gap" in result.stdout


def test_review_trigger_accepts_task_evidence_for_nontrivial_changes():
    result = run_script(
        "scripts/review-trigger",
        "--files",
        "agent/runner/message_processor.py",
        "--files",
        "tasks/2026-04-29-coke-native-guardrails.md",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "human_review_required: no" in result.stdout
