from __future__ import annotations

from types import SimpleNamespace

from coke.scheduler.__main__ import run_scheduler


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
