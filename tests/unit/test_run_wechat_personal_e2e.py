from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "run_wechat_personal_e2e.py"
)
SPEC = spec_from_file_location("run_wechat_personal_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wait_until_retries_after_transient_predicate_error(monkeypatch):
    attempts = {"count": 0}

    def predicate():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient_startup_error")
        return {"ok": True}

    monkeypatch.setattr(MODULE.time, "sleep", lambda _: None)
    result = MODULE.wait_until(
        "fake_provider_healthz",
        predicate,
        timeout_seconds=1.0,
        interval_seconds=0.0,
    )

    assert result == {"ok": True}
    assert attempts["count"] == 3
