from __future__ import annotations

import json
from datetime import UTC, datetime

from coke.turn.v2.staging import json_safe


def test_json_safe_serializes_datetimes_in_nested_payload() -> None:
    when = datetime(2026, 6, 11, 9, 0, tzinfo=UTC)
    payload = {
        "operation": "create",
        "trigger_time": when,
        "nested": {"at": when},
        "items": [{"trigger_time": when}],
    }
    safe = json_safe(payload)
    # The whole tree must now be JSON serializable (no datetime objects left).
    dumped = json.dumps(safe)
    assert when.isoformat() in dumped
    assert safe["trigger_time"] == when.isoformat()
    assert safe["items"][0]["trigger_time"] == when.isoformat()
