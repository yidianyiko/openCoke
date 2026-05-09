from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_repo_os_required_files_exist():
    required = [
        ROOT / "docs" / "design-docs" / "index.md",
        ROOT / "docs" / "design-docs" / "core-beliefs.md",
        ROOT / "docs" / "design-docs" / "golden-rules.md",
        ROOT / "docs" / "design-docs" / "human-ai-working-contract.md",
        ROOT / "docs" / "design-docs" / "coke-working-contract.md",
        ROOT / "docs" / "adr" / "README.md",
        ROOT / "docs" / "adr" / "_template.md",
        ROOT / "docs" / "adr" / "0001-canonical-repo-os-structure.md",
        ROOT / "docs" / "adr" / "0002-retire-tasks-directory.md",
        ROOT / "docs" / "adr" / "0003-consolidate-plans-to-superpowers.md",
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "superpowers" / "plans" / "README.md",
        ROOT / "docs" / "superpowers" / "plans" / "_template.md",
        ROOT / "docs" / "issues" / "README.md",
        ROOT / "docs" / "issues" / "_template.md",
        ROOT / "docs" / "issues" / "issue-gc-state.yaml",
        ROOT / "docs" / "product-specs" / "FEATURE_TREE.md",
        ROOT / "docs" / "release-guide.md",
        ROOT / "docs" / "RELEASE_CHECKLIST.md",
        ROOT / "docs" / "fitness" / "README.md",
        ROOT / "docs" / "fitness" / "coke-verification-matrix.md",
        ROOT / "docs" / "fitness" / "surfaces.yaml",
        ROOT / "scripts" / "check",
        ROOT / "scripts" / "verify-surface",
        ROOT / "scripts" / "suggest-verification",
        ROOT / "scripts" / "review-trigger",
        ROOT / "scripts" / "guardrails.py",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert missing == []


def test_retired_exec_plans_directory_stays_absent():
    assert not (ROOT / "docs" / "exec-plans").exists()


def test_architecture_has_routa_style_canonical_entrypoint():
    architecture_alias = ROOT / "docs" / "architecture.md"

    assert (ROOT / "docs" / "ARCHITECTURE.md").is_file()
    assert architecture_alias.is_symlink()
    assert architecture_alias.resolve() == ROOT / "docs" / "ARCHITECTURE.md"


def test_superpowers_root_has_no_loose_historical_docs():
    loose_files = [
        path.name
        for path in (ROOT / "docs" / "superpowers").iterdir()
        if path.is_file()
    ]

    assert loose_files == []


def test_docs_root_markdown_files_are_allowlisted():
    allowed = {
        "ARCHITECTURE.md",
        "architecture.md",
        "clawscale_bridge.md",
        "deploy.md",
        "roadmap.md",
        "release-guide.md",
        "RELEASE_CHECKLIST.md",
    }
    actual = {
        path.name
        for path in (ROOT / "docs").iterdir()
        if path.suffix == ".md" and (path.is_file() or path.is_symlink())
    }

    assert actual == allowed


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
        "docs/design-docs/human-ai-working-contract.md",
        "docs/ARCHITECTURE.md",
        "docs/issues/",
        "docs/product-specs/FEATURE_TREE.md",
        "docs/release-guide.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/superpowers/plans/",
        "docs/superpowers/specs/",
        "artifacts/evidence/",
    ]:
        assert needle in agents_text
        assert needle in claude_text
        assert needle in readme_text


def test_agents_md_requires_diff_aware_routing_before_manual_test_selection():
    agents_text = (ROOT / "AGENTS.md").read_text()

    guardrail_section = (
        "For non-trivial changes, run diff-aware routing before hand-picking"
    )
    suggest_command = "zsh scripts/suggest-verification --base HEAD~1"
    review_command = "zsh scripts/review-trigger --base HEAD~1"

    assert guardrail_section in agents_text
    assert agents_text.index(guardrail_section) < agents_text.index(suggest_command)
    assert agents_text.index(suggest_command) < agents_text.index(review_command)
    assert agents_text.index(review_command) < agents_text.index(
        "Use `docs/fitness/coke-verification-matrix.md`"
    )


def test_agents_md_uses_venv_python_for_pytest_commands():
    agents_text = (ROOT / "AGENTS.md").read_text()

    assert (
        "Unit tests: `.venv/bin/python -m pytest tests/unit/ -v`" in agents_text
    )
    assert "E2E tests: `.venv/bin/python -m pytest tests/e2e/ -v`" in agents_text
    assert "Unit tests: `pytest tests/unit/ -v`" not in agents_text
    assert "E2E tests: `pytest tests/e2e/ -v`" not in agents_text


def test_agents_md_locates_specs_and_plans_under_superpowers():
    agents_text = (ROOT / "AGENTS.md").read_text()

    assert "docs/superpowers/specs/" in agents_text
    assert "docs/superpowers/plans/" in agents_text
    assert "Put new execution plans in `docs/superpowers/plans/" in agents_text
    assert "Put new design specs in `docs/superpowers/specs/" in agents_text
    # Freshness must still be verified per file, even if location is canonical.
    assert "verify a spec or plan against current `main`" in agents_text


def test_agents_md_defines_issue_product_and_release_loops():
    agents_text = (ROOT / "AGENTS.md").read_text()

    for needle in [
        "## Issue Feedback Loop",
        "docs/issues/YYYY-MM-DD-short-description.md",
        "Use one canonical active local tracker per problem",
        "docs/product-specs/FEATURE_TREE.md",
        "docs/release-guide.md",
        "docs/RELEASE_CHECKLIST.md",
    ]:
        assert needle in agents_text


def test_docs_require_code_migrations_to_update_canonical_docs():
    agents_text = (ROOT / "AGENTS.md").read_text()
    golden_rules_text = (
        ROOT / "docs" / "design-docs" / "golden-rules.md"
    ).read_text()

    for text in [agents_text, golden_rules_text]:
        assert "If a code migration changes runtime behavior" in text
        assert "architecture boundaries" in text
        assert "protocol shape" in text
        assert "deployment flow" in text
        assert "surface ownership" in text
        assert "Do not leave stale docs" in text


def test_agents_md_summarizes_verification_trust_levels():
    agents_text = (ROOT / "AGENTS.md").read_text()

    for needle in [
        "Structure checks do not prove runtime behavior.",
        "Unit tests with mocks do not prove user-visible paths.",
        "Runtime, eval, or deployment claims need user-path, corpus, or smoke evidence.",
    ]:
        assert needle in agents_text


def test_project_specific_docs_capture_coke_surfaces():
    working_contract = (
        ROOT / "docs" / "design-docs" / "coke-working-contract.md"
    ).read_text()
    verification_matrix = (
        ROOT / "docs" / "fitness" / "coke-verification-matrix.md"
    ).read_text()

    for needle in [
        "human-ai-working-contract.md",
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
