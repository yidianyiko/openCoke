from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.agent_turn_trace_analyzer import (
    analysis_to_json,
    analyze_trace_records,
    discover_trace_files,
)

ROOT = Path(__file__).resolve().parents[2]


def _write_jsonl(path: Path, records: list[dict[str, Any] | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            if isinstance(record, str):
                handle.write(record + "\n")
            else:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _record(
    *,
    trace_id: str,
    route: str = "reminder_domain",
    status: str = "ok",
    output_source: str = "model",
    exposed_tools: list[str] | None = None,
    selected_tools: list[str] | None = None,
    error_code: str | None = None,
    failed_guardrail: str | None = None,
    content_text: str | None = None,
) -> dict[str, Any]:
    if exposed_tools is None:
        exposed_tools = ["create_reminder", "update_reminder"]
    if selected_tools is None:
        selected_tools = ["create_reminder"]
    guardrails = [
        {
            "name": "durable_write_summary",
            "status": (
                "failed" if failed_guardrail == "durable_write_summary" else "passed"
            ),
            "error_code": (
                error_code if failed_guardrail == "durable_write_summary" else None
            ),
        },
        {
            "name": "visible_identifier_leak",
            "status": (
                "failed" if failed_guardrail == "visible_identifier_leak" else "passed"
            ),
            "error_code": (
                error_code if failed_guardrail == "visible_identifier_leak" else None
            ),
        },
    ]
    record: dict[str, Any] = {
        "schema_version": "agent_turn_trace.v1",
        "record_type": "agent_turn_trace",
        "record_id": trace_id,
        "trace": {
            "trace_id": trace_id,
            "runtime": {"status": status},
            "routing": {"route": route},
            "output": {"output_source": output_source},
            "error": {"code": error_code} if error_code else None,
            "agent_calls": [
                {
                    "tool_names": exposed_tools,
                    "selected_tool_names": selected_tools,
                }
            ],
            "guardrails": guardrails,
        },
    }
    if content_text:
        record["content_evidence"] = {
            "input_text": content_text,
            "visible_output_text": f"assistant saw {content_text}",
        }
    return record


def test_discover_trace_files_accepts_files_and_directories(tmp_path: Path):
    direct = tmp_path / "direct.jsonl"
    nested = tmp_path / "suite" / "run.jsonl"
    ignored = tmp_path / "suite" / "ignored.txt"
    _write_jsonl(direct, [])
    _write_jsonl(nested, [])
    ignored.write_text("not jsonl", encoding="utf-8")

    assert discover_trace_files([direct, tmp_path / "suite"]) == [direct, nested]


def test_analyze_trace_records_counts_routes_tools_errors_and_findings(tmp_path: Path):
    trace_file = tmp_path / "trace.jsonl"
    _write_jsonl(
        trace_file,
        [
            _record(
                trace_id="one", exposed_tools=["create_reminder", "cancel_reminder"]
            ),
            _record(
                trace_id="two",
                route="fallback",
                status="exception",
                output_source="fallback",
                exposed_tools=["create_reminder", "cancel_reminder"],
                selected_tools=[],
                error_code="agent_runtime_exception",
                failed_guardrail="visible_identifier_leak",
                content_text="PRIVATE USER SENTENCE",
            ),
            "{not json",
        ],
    )

    summary = analyze_trace_records([trace_file])

    assert summary["schema_version"] == "agent_trace_analysis.v1"
    assert summary["record_count"] == 2
    assert summary["invalid_record_count"] == 1
    assert summary["route_counts"] == {"fallback": 1, "reminder_domain": 1}
    assert summary["status_counts"] == {"exception": 1, "ok": 1}
    assert summary["output_source_counts"] == {"fallback": 1, "model": 1}
    assert summary["error_counts"] == {"agent_runtime_exception": 1}
    assert summary["guardrail_failure_counts"] == {"visible_identifier_leak": 1}
    assert summary["tool_exposure_counts"] == {
        "cancel_reminder": 2,
        "create_reminder": 2,
    }
    assert summary["selected_tool_counts"] == {"create_reminder": 1}
    assert summary["unused_exposed_tool_counts"] == {"cancel_reminder": 2}
    finding_codes = {finding["code"] for finding in summary["findings"]}
    assert "runtime_non_ok" in finding_codes
    assert "fallback_or_empty_output" in finding_codes
    assert "guardrail_failure" in finding_codes
    assert "unused_exposed_tools" in finding_codes

    payload = analysis_to_json(summary)
    assert "PRIVATE USER SENTENCE" not in payload
    assert (
        "observe -> analyze -> choose -> change -> verify -> compare -> record"
        in payload
    )


def test_cli_writes_summary_json(tmp_path: Path):
    trace_file = tmp_path / "trace.jsonl"
    output_file = tmp_path / "summary.json"
    _write_jsonl(trace_file, [_record(trace_id="one")])

    result = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/analyze_agent_turn_traces.py",
            str(trace_file),
            "--output",
            str(output_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(output_file.read_text(encoding="utf-8"))
    assert summary["schema_version"] == "agent_trace_analysis.v1"
    assert summary["record_count"] == 1
