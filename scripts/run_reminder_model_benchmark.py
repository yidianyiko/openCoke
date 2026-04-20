#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent.agno_agent.evals.reminder_benchmark import (
    format_markdown_summary,
    load_cases,
    run_cli,
)


def main() -> int:
    data = load_cases()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    models = args.models or data["models"]
    result = run_cli(models, args.output)
    print(format_markdown_summary(result["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
