from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ALLOWED_CAPABILITIES = {
    "reminder_intent",
    "url_context",
    "timezone",
    "calendar_import",
}


@dataclass(frozen=True)
class CapabilityRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamPlan:
    response_text: str
    capability_requests: tuple[CapabilityRequest, ...]
    rejected_requests: tuple[str, ...] = ()


def parse_team_plan(content: str) -> TeamPlan:
    text = str(content or "").strip()
    if not text:
        return TeamPlan(response_text="", capability_requests=())

    response_lines: list[str] = []
    accepted: list[CapabilityRequest] = []
    rejected: list[str] = []
    in_response = False
    saw_structured_marker = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line in {"RESPONSE:", "RESPONSE"}:
            saw_structured_marker = True
            in_response = True
            continue
        if line.startswith("RESPONSE "):
            saw_structured_marker = True
            in_response = True
            response_lines.append(raw_line.strip()[len("RESPONSE ") :].rstrip())
            continue
        if "REQUEST " in line and not line.startswith("REQUEST "):
            before_request, _, inline_request = raw_line.partition("REQUEST ")
            if in_response and before_request.strip():
                response_lines.append(before_request.rstrip())
            line = f"REQUEST {inline_request.strip()}"
        if line.startswith("REQUEST "):
            saw_structured_marker = True
            in_response = False
            request = _parse_request_line(line)
            if request is None:
                continue
            name, args = request
            if name in ALLOWED_CAPABILITIES:
                accepted.append(CapabilityRequest(name=name, args=args))
            elif name:
                rejected.append(name)
            continue
        if in_response:
            response_lines.append(raw_line)

    if not saw_structured_marker:
        return TeamPlan(response_text=text, capability_requests=())

    return TeamPlan(
        response_text="\n".join(response_lines).strip(),
        capability_requests=tuple(accepted),
        rejected_requests=tuple(rejected),
    )


def _parse_request_line(line: str) -> tuple[str, dict[str, Any]] | None:
    remainder = line.removeprefix("REQUEST ").strip()
    name, _, raw_args = remainder.partition(" ")
    args: dict[str, Any] = {}
    if raw_args.strip():
        try:
            parsed_args = json.loads(raw_args)
        except json.JSONDecodeError:
            return (name, {}) if name else None
        if not isinstance(parsed_args, dict):
            return (name, {}) if name else None
        args = parsed_args
    return (name, args) if name else None
