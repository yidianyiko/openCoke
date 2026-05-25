"""Append-only conversation log + final JSON dump for evidence."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Turn:
    turn: int
    speaker: str
    coke_account_id: str
    input_text: str
    inbound_event_id: str
    reply_text: str
    output_id: str | None
    elapsed_ms: int
    note: str | None = None
    placeholder_received: bool = False
    late_reply_landed: bool = False
    polling_seconds_used: float = 0.0
    placeholder_reply: str | None = None
    placeholder_output_id: str | None = None


@dataclass
class Transcript:
    batch_id: str
    accounts: list[dict] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    verdict: dict = field(default_factory=lambda: {"passed": False, "problems": []})

    def add_account(self, account_obj) -> None:
        self.accounts.append(
            {
                "coke_account_id": account_obj.coke_account_id,
                "display_name": account_obj.display_name,
                "label": account_obj.label,
                "tenant_id": account_obj.tenant_id,
                "clawscale_user_id": account_obj.clawscale_user_id,
            }
        )

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)

    def add_finding(self, *, severity: str, summary: str, detail: str | None = None) -> None:
        self.findings.append(
            {
                "severity": severity,
                "summary": summary,
                "detail": detail,
                "logged_at": int(time.time()),
            }
        )

    def set_verdict(self, *, passed: bool, problems: list[str] | None = None) -> None:
        self.verdict = {"passed": passed, "problems": problems or []}

    def save(self, output_dir: str | Path) -> Path:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"shared-reminder-agent-smoke-{self.batch_id}.json"
        payload = {
            "batch_id": self.batch_id,
            "accounts": self.accounts,
            "turns": [asdict(turn) for turn in self.turns],
            "findings": self.findings,
            "verdict": self.verdict,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return path
