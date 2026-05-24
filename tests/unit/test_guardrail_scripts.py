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


def test_check_import_boundaries_rejects_backend_path_import():
    from scripts import guardrails

    files = {
        "gateway/packages/web/lib/bad.ts": (
            "import { CHANNEL_CONFIG_SCHEMA } "
            "from '../../api/src/channel/provider-config-schema';\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert any("imports backend-only channel internals" in e for e in errors)


def test_check_import_boundaries_rejects_multiline_backend_path_import():
    from scripts import guardrails

    files = {
        "gateway/packages/web/lib/bad-multiline.ts": (
            "import {\n"
            "  buildPublicLinqConfig,\n"
            "} from '../../api/src/channel/linq-config';\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert any("imports backend-only channel internals" in e for e in errors)


def test_check_import_boundaries_rejects_dynamic_backend_path_import():
    from scripts import guardrails

    files = {
        "gateway/packages/web/lib/bad-dynamic.ts": (
            "export async function load() {\n"
            "  return import('../../api/src/channel/provider-config-schema');\n"
            "}\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert any("imports backend-only channel internals" in e for e in errors)


def test_check_import_boundaries_rejects_named_import_via_alias():
    from scripts import guardrails

    files = {
        "gateway/packages/web/lib/bad-alias.ts": (
            "import { CHANNEL_CONFIG_SCHEMA } from '@coke/api-channel';\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert any("CHANNEL_CONFIG_SCHEMA" in e for e in errors)


def test_check_import_boundaries_rejects_namespace_and_default_alias_imports():
    from scripts import guardrails

    files = {
        "gateway/packages/web/lib/bad-namespace.ts": (
            "import * as ChannelApi from '@coke/api-channel';\n"
        ),
        "gateway/packages/web/lib/bad-default.ts": (
            "import ChannelApi from '@coke/api-channel';\n"
        ),
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert any("bad-namespace.ts imports backend-only channel alias" in e for e in errors)
    assert any("bad-default.ts imports backend-only channel alias" in e for e in errors)


def test_check_import_boundaries_allows_user_visible_copy():
    from scripts import guardrails

    files = {
        "gateway/packages/web/app/help.tsx": (
            "export function Help() {\n"
            "  // Explanation of CHANNEL_CONFIG_SCHEMA appears in admin help text.\n"
            "  return <p>Configure your channel under settings.</p>;\n"
            "}\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert errors == []


def test_check_import_boundaries_ignores_non_web_files():
    from scripts import guardrails

    files = {
        "gateway/packages/api/src/routes/x.ts": (
            "import { CHANNEL_CONFIG_SCHEMA } "
            "from '../channel/provider-config-schema';\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert errors == []


def test_check_import_boundaries_ignores_deleted_web_files():
    from scripts import guardrails

    def read_deleted(_path):
        raise FileNotFoundError("deleted")

    errors = guardrails.check_import_boundaries(
        ["gateway/packages/web/app/u/[code]/claim-handoff.tsx"],
        read_text=read_deleted,
    )

    assert errors == []


def test_collect_tracked_web_files_reads_nested_gateway_repo(monkeypatch):
    from scripts import guardrails

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("cwd")))
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "packages/web/app/page.tsx\n"
                "packages/web/lib/admin-api.ts\n"
                "packages/api/src/index.ts\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(guardrails.subprocess, "run", fake_run)

    assert guardrails.collect_tracked_web_files() == [
        "gateway/packages/web/app/page.tsx",
        "gateway/packages/web/lib/admin-api.ts",
    ]
    assert calls == [
        (["git", "ls-files", "packages/web"], ROOT / "gateway")
    ]


def test_collect_tracked_web_files_reports_nested_gateway_git_failure(monkeypatch):
    from scripts import guardrails

    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=128, stdout="", stderr="not a git repo\n")

    monkeypatch.setattr(guardrails.subprocess, "run", fake_run)

    try:
        guardrails.collect_tracked_web_files()
    except RuntimeError as error:
        assert "failed to list nested gateway web files" in str(error)
        assert "not a git repo" in str(error)
    else:
        raise AssertionError("expected nested gateway git failure to be reported")


def test_check_import_boundaries_fails_when_nested_web_file_list_is_empty(monkeypatch, capsys):
    from scripts import guardrails

    monkeypatch.setattr(guardrails, "collect_tracked_web_files", lambda: [])

    result = guardrails.cmd_check_import_boundaries(SimpleNamespace(files=[], base="HEAD"))

    captured = capsys.readouterr()
    assert result == 1
    assert "no tracked gateway web files found" in captured.out


def test_check_import_boundaries_reports_nested_gateway_collector_failure(
    monkeypatch, capsys
):
    from scripts import guardrails

    monkeypatch.setattr(
        guardrails,
        "collect_tracked_web_files",
        lambda: (_ for _ in ()).throw(RuntimeError("failed to list nested gateway web files: boom")),
    )

    result = guardrails.cmd_check_import_boundaries(SimpleNamespace(files=[], base="HEAD"))

    captured = capsys.readouterr()
    assert result == 1
    assert "failed to list nested gateway web files: boom" in captured.out


def test_validate_ownership_registry_reports_invalid_missing_and_omitted_route(
    monkeypatch,
):
    from scripts import guardrails

    monkeypatch.setattr(
        guardrails,
        "expected_route_registry_paths",
        lambda: {
            "gateway/packages/api/src/routes/customer-auth-routes.ts",
            "gateway/packages/api/src/routes/customer-subscription-routes.ts",
        },
    )

    registry = {
        "systems": ["platform"],
        "routes": [
            {
                "path": "gateway/packages/api/src/routes/customer-auth-routes.ts",
                "owner": "made-up",
            },
            {
                "path": "gateway/packages/api/src/routes/missing.ts",
                "owner": "platform",
            },
        ],
        "contracts": [],
    }

    errors = guardrails.validate_ownership_registry(registry)

    assert (
        "ownership registry missing route entry: "
        "gateway/packages/api/src/routes/customer-subscription-routes.ts"
    ) in errors
    assert (
        "ownership registry route missing file: "
        "gateway/packages/api/src/routes/missing.ts"
    ) in errors
    assert (
        "ownership registry invalid owner made-up for "
        "gateway/packages/api/src/routes/customer-auth-routes.ts"
    ) in errors


def test_check_ownership_registry_reports_clean_registry(capsys):
    from scripts import guardrails

    result = guardrails.cmd_check_ownership_registry(
        SimpleNamespace(registry="", base="HEAD", files=[])
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "OK ownership registry" in captured.out


def test_suggest_verification_includes_product_surfaces():
    result = run_script(
        "scripts/suggest-verification",
        "--files",
        "agent/reminder/runtime_contract.py",
        "--files",
        "agent/timezone_service.py",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "product-reminder" in result.stdout
    assert "product-timezone" in result.stdout
