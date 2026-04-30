# -*- coding: utf-8 -*-
"""ReminderDetect few-shot fixture loader."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_FIXTURE_PATH = Path(__file__).with_name("reminder_few_shot.json")


@lru_cache(maxsize=1)
def load_reminder_few_shots() -> list[dict[str, Any]]:
    with _FIXTURE_PATH.open("r", encoding="utf-8") as fixture:
        data = json.load(fixture)
    if not isinstance(data, list):
        raise ValueError("reminder_few_shot.json must contain a list")
    return data


def format_reminder_few_shots_for_prompt() -> str:
    return json.dumps(load_reminder_few_shots(), ensure_ascii=False, indent=2)
