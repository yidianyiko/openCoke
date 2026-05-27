import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_DOC = ROOT / "docs" / "design-docs" / "data-retention-policy.md"
SCHEDULING_SPEC = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-28-direct-friendship-shared-reminders-design.md"
)

POLICY_NAME_RE = re.compile(r"`([a-z][a-z_]+_retention)`")
SCHEDULING_POLICY_NAMES = {
    "friend_link_session_retention",
    "disabled_user_link_retention",
    "friendship_retention",
    "product_notification_retention",
}
RETIRED_SCHEDULING_POLICY_NAMES = {
    "friend_request_retention",
    "account_block_retention",
    "shared_reminder_request_retention",
}


def _extract_policy_names(path: Path) -> set[str]:
    return set(POLICY_NAME_RE.findall(path.read_text(encoding="utf-8")))


def test_every_policy_in_boundary_spec_is_documented():
    spec_names = _extract_policy_names(SCHEDULING_SPEC)
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
        "Scheduling retention policy names are missing from scheduling spec: "
        f"{sorted(SCHEDULING_POLICY_NAMES - spec_names)}"
    )
    missing = spec_names - doc_names
    assert missing == set(), (
        "Retention policies named in scheduling spec are missing from policy doc: "
        f"{sorted(missing)}"
    )


def test_policy_doc_does_not_declare_retired_scheduling_policies():
    doc_names = _extract_policy_names(POLICY_DOC)
    retired = doc_names & RETIRED_SCHEDULING_POLICY_NAMES
    assert retired == set(), (
        "Policy doc declares retired scheduling policies: " f"{sorted(retired)}"
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
        assert (
            duration and "T" + "BD" not in duration
        ), f"policy {name} has empty or TBD duration"
        assert owner, f"policy {name} has empty cleanup owner"
