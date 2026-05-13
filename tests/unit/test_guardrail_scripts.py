from pathlib import Path
import subprocess
from types import SimpleNamespace


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
    assert "changed_surfaces: repo-os-docs gateway-web" in result.stdout
    assert "zsh scripts/verify-surface repo-os-docs gateway-web" in result.stdout


def test_suggest_verification_maps_agent_runtime_core_to_worker_surface():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "agent/agno_agent/runtime/team_runtime.py",
        "--files",
        "agent/agno_agent/model_factory.py",
        "--files",
        "agent/agno_agent/capabilities/reminder_intent.py",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed_surfaces: worker-runtime" in result.stdout
    assert "zsh scripts/verify-surface worker-runtime" in result.stdout


def test_suggest_verification_maps_superpowers_history_to_repo_os_surface():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "docs/superpowers/specs/2026-05-08-single-agent-native-toolcalling-design.md",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed_surfaces: repo-os-docs" in result.stdout
    assert "zsh scripts/verify-surface repo-os-docs" in result.stdout


def test_suggest_verification_maps_routa_style_doc_surfaces_to_repo_os():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "docs/ARCHITECTURE.md",
        "--files",
        "docs/issues/2026-05-09-example.md",
        "--files",
        "docs/product-specs/FEATURE_TREE.md",
        "--files",
        "docs/release-guide.md",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed_surfaces: repo-os-docs" in result.stdout
    assert "zsh scripts/verify-surface repo-os-docs" in result.stdout


def test_suggest_verification_maps_guardrail_tooling_to_full_repo_os_surface():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "docs/fitness/surfaces.yaml",
        "--files",
        "scripts/guardrails.py",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed_surfaces: repo-os" in result.stdout
    assert "zsh scripts/verify-surface repo-os" in result.stdout


def test_collect_changed_files_includes_deleted_files(monkeypatch):
    from scripts import guardrails

    def fake_run(command, **_kwargs):
        if command[:4] == [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRD",
        ]:
            return SimpleNamespace(stdout="artifacts/evidence/deleted.json\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(guardrails.subprocess, "run", fake_run)

    assert guardrails.collect_changed_files("HEAD") == [
        "artifacts/evidence/deleted.json"
    ]


def test_review_trigger_flags_cross_boundary_and_missing_evidence():
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
    assert "evidence_gap" in result.stdout


def test_review_trigger_accepts_evidence_for_nontrivial_changes():
    result = run_script(
        "scripts/review-trigger",
        "--files",
        "agent/runner/message_processor.py",
        "--files",
        "artifacts/evidence/2026-04-29-coke-native-guardrails.md",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "human_review_required: no" in result.stdout


def test_review_trigger_does_not_require_artifact_for_gateway_gitlink_doc_change():
    result = run_script(
        "scripts/review-trigger",
        "--files",
        "gateway",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "human_review_required: no" in result.stdout
    assert "evidence_gap" not in result.stdout
