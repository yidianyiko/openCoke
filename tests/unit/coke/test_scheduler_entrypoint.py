from __future__ import annotations

from types import SimpleNamespace

from coke.scheduler.__main__ import run_scheduler


def test_apscheduler_substrate_tables_are_excluded_from_alembic_check():
    from coke.alembic_filters import include_name, include_object

    assert include_name("apscheduler_jobs", "table", {}) is False
    assert include_name("ix_apscheduler_jobs_next_run_time", "index", {}) is False
    assert (
        include_object(
            object(),
            "ix_apscheduler_jobs_next_run_time",
            "index",
            True,
            None,
        )
        is False
    )
    assert include_name("account", "table", {}) is True
    assert include_name("uq_account_access_account", "unique_constraint", {}) is True


def test_scheduler_registers_picklable_importable_job_callable():
    scheduler = run_scheduler(
        settings=SimpleNamespace(
            database_url="sqlite:///:memory:",
            scheduler_interval_s=60,
        ),
        runtime=SimpleNamespace(),
        run_forever=False,
    )

    jobs = scheduler.get_jobs()

    assert len(jobs) == 1
    for job in jobs:
        assert job.func.__name__ != "<lambda>"
        assert "<locals>" not in job.func.__qualname__
        assert job.func_ref == "coke.scheduler.__main__:scheduler_scan_job"
        assert job.args == ()
        assert job.kwargs == {}
