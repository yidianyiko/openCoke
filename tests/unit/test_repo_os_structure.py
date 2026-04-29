from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_repo_os_required_files_exist():
    required = [
        ROOT / "docs" / "design-docs" / "index.md",
        ROOT / "docs" / "design-docs" / "core-beliefs.md",
        ROOT / "docs" / "design-docs" / "golden-rules.md",
        ROOT / "docs" / "design-docs" / "coke-working-contract.md",
        ROOT / "docs" / "adr" / "README.md",
        ROOT / "docs" / "adr" / "_template.md",
        ROOT / "docs" / "adr" / "0001-canonical-repo-os-structure.md",
        ROOT / "docs" / "exec-plans" / "README.md",
        ROOT / "docs" / "exec-plans" / "_template.md",
        ROOT / "docs" / "fitness" / "README.md",
        ROOT / "docs" / "fitness" / "verification-checklist.md",
        ROOT / "docs" / "fitness" / "coke-verification-matrix.md",
        ROOT / "docs" / "fitness" / "surfaces.yaml",
        ROOT / "tasks" / "README.md",
        ROOT / "tasks" / "_template.md",
        ROOT / "scripts" / "check",
        ROOT / "scripts" / "verify-surface",
        ROOT / "scripts" / "suggest-verification",
        ROOT / "scripts" / "review-trigger",
        ROOT / "scripts" / "guardrails.py",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert missing == []


def test_claude_md_is_agents_md_symlink():
    claude_path = ROOT / "CLAUDE.md"

    assert claude_path.is_symlink()
    assert claude_path.resolve() == ROOT / "AGENTS.md"


def test_root_docs_reference_repo_os_map():
    agents_text = (ROOT / "AGENTS.md").read_text()
    claude_text = (ROOT / "CLAUDE.md").read_text()
    readme_text = (ROOT / "README.md").read_text()

    for needle in [
        "docs/design-docs/index.md",
        "docs/fitness/README.md",
        "docs/fitness/coke-verification-matrix.md",
        "docs/fitness/surfaces.yaml",
        "docs/exec-plans/",
        "tasks/",
    ]:
        assert needle in agents_text
        assert needle in claude_text
        assert needle in readme_text


def test_project_specific_docs_capture_coke_surfaces():
    working_contract = (
        ROOT / "docs" / "design-docs" / "coke-working-contract.md"
    ).read_text()
    verification_matrix = (
        ROOT / "docs" / "fitness" / "coke-verification-matrix.md"
    ).read_text()

    for needle in [
        "agent/runner/agent_runner.py",
        "connector/clawscale_bridge/app.py",
        "connector/clawscale_bridge/output_dispatcher.py",
        "gateway/packages/api",
        "gateway/packages/web",
        "scripts/test-deploy-compose-to-gcp.sh",
    ]:
        assert needle in working_contract
        assert needle in verification_matrix


def test_scripts_check_passes():
    result = subprocess.run(
        ["zsh", "scripts/check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "check passed" in result.stdout
