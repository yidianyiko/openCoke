import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_DOC = ROOT / "docs" / "design-docs" / "data-retention-policy.md"
BOUNDARY_SPEC = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-19-frontend-platform-channel-boundary-design.md"
)
SCHEDULING_SPEC = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-21-user-link-scheduling-design.md"
)

POLICY_NAME_RE = re.compile(r"`([a-z][a-z_]+_retention)`")
SCHEDULING_POLICY_NAMES = {
    "scheduling_link_session_retention",
    "scheduling_service_link_retention",
    "scheduling_appointment_request_retention",
    "scheduling_shared_appointment_retention",
    "scheduling_bookable_window_retention",
    "scheduling_disabled_user_link_retention",
}


def _extract_policy_names(path: Path) -> set[str]:
    return set(POLICY_NAME_RE.findall(path.read_text(encoding="utf-8")))


def test_every_policy_in_boundary_spec_is_documented():
    spec_names = _extract_policy_names(BOUNDARY_SPEC)
    doc_names = _extract_policy_names(POLICY_DOC)
    missing = spec_names - doc_names
    assert missing == set(), (
        "Retention policies named in boundary spec are missing from policy doc: "
        f"{sorted(missing)}"
    )


def test_scheduling_spec_retention_policies_are_documented():
    spec_names = _extract_policy_names(SCHEDULING_SPEC)
    doc_names = _extract_policy_names(POLICY_DOC)
    assert SCHEDULING_POLICY_NAMES <= spec_names, (
        "Scheduling spec is missing required retention policy names: "
        f"{sorted(SCHEDULING_POLICY_NAMES - spec_names)}"
    )
    missing = spec_names - doc_names
    assert missing == set(), (
        "Retention policies named in scheduling spec are missing from policy doc: "
        f"{sorted(missing)}"
    )


def test_policy_doc_does_not_declare_unused_policies():
    spec_names = _extract_policy_names(BOUNDARY_SPEC) | _extract_policy_names(
        SCHEDULING_SPEC
    )
    doc_names = _extract_policy_names(POLICY_DOC)
    extra = doc_names - spec_names
    extra.discard("migration_retention")
    assert extra == set(), (
        f"Policy doc declares policies not used by boundary spec: {sorted(extra)}"
    )


def test_policy_doc_table_has_duration_and_owner_for_every_policy():
    text = POLICY_DOC.read_text(encoding="utf-8")
    for name in _extract_policy_names(POLICY_DOC):
        row_re = re.compile(
            rf"\|\s*`{re.escape(name)}`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
            re.MULTILINE,
        )
        match = row_re.search(text)
        assert match, f"policy {name} has no row in the policy doc table"
        duration, owner = match.group(1).strip(), match.group(2).strip()
        assert duration and "T" + "BD" not in duration, (
            f"policy {name} has empty or TBD duration"
        )
        assert owner, f"policy {name} has empty cleanup owner"
