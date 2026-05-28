from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "agent_trace_analysis.v1"
POSITIVE_LOOP = "observe -> analyze -> choose -> change -> verify -> compare -> record"


def discover_trace_files(paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".jsonl":
            files.append(path)
        elif path.is_dir():
            files.extend(
                sorted(item for item in path.rglob("*.jsonl") if item.is_file())
            )
    return sorted(files, key=lambda item: item.as_posix())


def analyze_trace_records(paths: Sequence[Path]) -> dict[str, Any]:
    files = discover_trace_files(paths)
    route_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    output_source_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    tool_exposure_counts: Counter[str] = Counter()
    selected_tool_counts: Counter[str] = Counter()
    record_count = 0
    invalid_record_count = 0

    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    invalid_record_count += 1
                    continue

                trace = record.get("trace") if isinstance(record, Mapping) else None
                if not isinstance(trace, Mapping):
                    invalid_record_count += 1
                    continue

                record_count += 1
                _count_trace(
                    trace,
                    route_counts=route_counts,
                    status_counts=status_counts,
                    output_source_counts=output_source_counts,
                    error_counts=error_counts,
                    tool_exposure_counts=tool_exposure_counts,
                    selected_tool_counts=selected_tool_counts,
                )

    unused_exposed_tool_counts = Counter(
        {
            tool_name: count
            for tool_name, count in tool_exposure_counts.items()
            if selected_tool_counts.get(tool_name, 0) == 0
        }
    )
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_files": [path.as_posix() for path in files],
        "record_count": record_count,
        "invalid_record_count": invalid_record_count,
        "route_counts": _sorted_counter(route_counts),
        "status_counts": _sorted_counter(status_counts),
        "output_source_counts": _sorted_counter(output_source_counts),
        "error_counts": _sorted_counter(error_counts),
        "tool_exposure_counts": _sorted_counter(tool_exposure_counts),
        "selected_tool_counts": _sorted_counter(selected_tool_counts),
        "unused_exposed_tool_counts": _sorted_counter(unused_exposed_tool_counts),
        "findings": _build_findings(
            status_counts=status_counts,
            output_source_counts=output_source_counts,
            error_counts=error_counts,
            unused_exposed_tool_counts=unused_exposed_tool_counts,
        ),
        "positive_loop": {
            "summary": POSITIVE_LOOP,
            "steps": [
                "observe trace evidence",
                "analyze aggregate patterns",
                "choose the smallest high-impact finding",
                "change the matching layer only",
                "verify with the same eval or smoke surface",
                "compare trace deltas",
                "record the decision and evidence",
            ],
        },
    }
    return summary


def analysis_to_json(summary: Mapping[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _count_trace(
    trace: Mapping[str, Any],
    *,
    route_counts: Counter[str],
    status_counts: Counter[str],
    output_source_counts: Counter[str],
    error_counts: Counter[str],
    tool_exposure_counts: Counter[str],
    selected_tool_counts: Counter[str],
) -> None:
    routing = _mapping(trace.get("routing"))
    runtime = _mapping(trace.get("runtime"))
    output = _mapping(trace.get("output"))
    error = _mapping(trace.get("error"))

    route_counts[_text(routing.get("route"), "unknown")] += 1
    status_counts[_text(runtime.get("status"), "unknown")] += 1
    output_source_counts[_text(output.get("output_source"), "unknown")] += 1

    error_code = error.get("code")
    if error_code:
        error_counts[str(error_code)] += 1

    for agent_call in _sequence(trace.get("agent_calls")):
        call = _mapping(agent_call)
        for tool_name in _sequence(call.get("tool_names")):
            tool_exposure_counts[str(tool_name)] += 1
        for tool_name in _sequence(call.get("selected_tool_names")):
            selected_tool_counts[str(tool_name)] += 1


def _build_findings(
    *,
    status_counts: Counter[str],
    output_source_counts: Counter[str],
    error_counts: Counter[str],
    unused_exposed_tool_counts: Counter[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    non_ok_count = sum(
        count for status, count in status_counts.items() if status not in {"ok"}
    )
    if non_ok_count:
        findings.append(
            {
                "severity": "high",
                "code": "runtime_non_ok",
                "summary": f"{non_ok_count} trace records ended without ok status.",
                "recommended_next_step": (
                    "Inspect error_counts and failure stages before changing prompts."
                ),
            }
        )

    empty_output_count = sum(
        count for source, count in output_source_counts.items() if source == "empty"
    )
    if empty_output_count:
        findings.append(
            {
                "severity": "medium",
                "code": "empty_output",
                "summary": f"{empty_output_count} trace records produced empty output.",
                "recommended_next_step": (
                    "Check route handling and output synthesis before adding examples."
                ),
            }
        )

    if error_counts:
        findings.append(
            {
                "severity": "high",
                "code": "runtime_error_cluster",
                "summary": "Runtime error codes were observed.",
                "evidence": _sorted_counter(error_counts),
                "recommended_next_step": (
                    "Classify each error as runtime bug, test/eval bug, environment issue, or plan gap."
                ),
            }
        )

    if unused_exposed_tool_counts:
        findings.append(
            {
                "severity": "medium",
                "code": "unused_exposed_tools",
                "summary": "Some exposed tools were never selected in this trace set.",
                "evidence": _sorted_counter(unused_exposed_tool_counts),
                "recommended_next_step": (
                    "Review tool names, descriptions, argument shapes, and routing clarity."
                ),
            }
        )
    return findings


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, list | tuple):
        return value
    return ()


def _text(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}
