from __future__ import annotations

import json
from types import SimpleNamespace

from scripts import simulate_user_path


def test_default_evidence_path_uses_user_path_directory():
    assert simulate_user_path.default_evidence_path(run_id="run/id:1").as_posix() == (
        "artifacts/evidence/user-path/run-id-1.json"
    )


def test_message_mode_runs_one_business_clawscale_case(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    class FakeClient:
        admin = SimpleNamespace(command=lambda _command: None)

        def __getitem__(self, _name):
            return object()

    captured = {}

    def fake_run_batch(_db, cases, **kwargs):
        captured["cases"] = cases
        captured["kwargs"] = kwargs
        return {
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "batch_id": kwargs["batch_id"],
            "platform": kwargs["platform"],
            "character_id": "char-1",
            "user_ids": ["user-1"],
            "serial": kwargs["serial"],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "pass_rate": 1,
                "by_error": {},
                "failures": [],
            },
            "results": [
                {
                    "index": 0,
                    "input": cases[0].input,
                    "user_id": "user-1",
                    "original_from_user": "",
                    "input_message_id": "input-1",
                    "input_status": "handled",
                    "passed": True,
                    "errors": [],
                    "outputs": [{"message": "已创建提醒：喝水"}],
                    "reminders": [{"title": "喝水"}],
                    "elapsed_seconds": 0.1,
                }
            ],
        }

    monkeypatch.setattr(
        simulate_user_path.normal_eval, "mongo_client", lambda: FakeClient()
    )
    monkeypatch.setattr(simulate_user_path.normal_eval, "run_batch", fake_run_batch)

    exit_code = simulate_user_path.main(
        [
            "--message",
            "18:00提醒我喝水",
            "--expect",
            "reminder_created",
            "--batch-id",
            "unit message",
        ]
    )

    assert exit_code == 0
    case = captured["cases"][0]
    assert case.input == "18:00提醒我喝水"
    assert case.metadata["evaluation_expectation"] == "crud"
    assert case.metadata["expected_operation"] == "create"
    assert captured["kwargs"]["transport"] == "business-clawscale"
    assert captured["kwargs"]["platform"] == "business"
    assert captured["kwargs"]["serial"] is True

    evidence_path = tmp_path / "artifacts/evidence/user-path/unit-message.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["input"]["mode"] == "message"
    assert evidence["input"]["runtime"] == "local"
    assert evidence["input"]["transport"] == "business-clawscale"
    assert evidence["observed"]["user_visible_replies"] == ["已创建提醒：喝水"]
    assert evidence["observed"]["created_reminders"] == [{"title": "喝水"}]
    assert evidence["verdict"]["passed"] is True
