from __future__ import annotations

APSCHEDULER_TABLES = frozenset({"apscheduler_jobs"})
APSCHEDULER_INDEXES = frozenset({"ix_apscheduler_jobs_next_run_time"})


def include_name(name: str | None, type_: str, parent_names) -> bool:
    if type_ == "table" and name in APSCHEDULER_TABLES:
        return False
    if type_ == "index" and name in APSCHEDULER_INDEXES:
        return False
    return True


def include_object(
    obj, name: str | None, type_: str, reflected: bool, compare_to
) -> bool:
    return include_name(name, type_, {})
