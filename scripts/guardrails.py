#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "docs" / "fitness" / "surfaces.yaml"


@dataclass(frozen=True)
class Surface:
    name: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class ReviewMatch:
    name: str
    severity: str
    reasons: tuple[str, ...]


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def load_surfaces(config: dict[str, Any]) -> list[Surface]:
    surfaces: list[Surface] = []
    for raw in config.get("surfaces", []):
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        paths = raw.get("paths", [])
        if isinstance(name, str) and isinstance(paths, list):
            surfaces.append(Surface(name=name, paths=tuple(str(path) for path in paths)))
    return surfaces


def path_matches(file_path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    normalized = file_path.strip().lstrip("./")
    for pattern in patterns:
        clean_pattern = str(pattern).strip().lstrip("./")
        if fnmatch.fnmatch(normalized, clean_pattern):
            return True
        if clean_pattern.endswith("/**"):
            prefix = clean_pattern[:-3]
            if normalized == prefix or normalized.startswith(f"{prefix}/"):
                return True
    return False


def collect_changed_files(base: str) -> list[str]:
    commands = [
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base],
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    files: list[str] = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        files.extend(line.strip() for line in result.stdout.splitlines() if line.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for file_path in files:
        if file_path not in seen:
            seen.add(file_path)
            deduped.append(file_path)
    return deduped


def resolve_files(args: argparse.Namespace) -> list[str]:
    explicit = getattr(args, "files", None) or []
    if explicit:
        return explicit
    return collect_changed_files(args.base)


def surfaces_for_files(files: list[str], surfaces: list[Surface]) -> list[str]:
    matched: list[str] = []
    for surface in surfaces:
        if any(path_matches(file_path, surface.paths) for file_path in files):
            matched.append(surface.name)
    return matched


def dry_run_verify_surface(surfaces: list[str]) -> str:
    if not surfaces:
        return ""
    result = subprocess.run(
        ["zsh", "scripts/verify-surface", "--dry-run", *surfaces],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.rstrip()


def collect_diff_stats(base: str) -> tuple[int, int, int]:
    result = subprocess.run(
        ["git", "diff", "--numstat", "--diff-filter=ACMR", base],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    file_count = 0
    added_lines = 0
    deleted_lines = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-" or parts[1] == "-":
            continue
        file_count += 1
        added_lines += int(parts[0])
        deleted_lines += int(parts[1])
    return file_count, added_lines, deleted_lines


def evaluate_review_triggers(
    files: list[str],
    config: dict[str, Any],
    base: str,
) -> list[ReviewMatch]:
    matches: list[ReviewMatch] = []
    triggers = config.get("review_triggers", [])
    diff_stats = collect_diff_stats(base)

    for raw in triggers:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "unknown"))
        severity = str(raw.get("severity", "medium"))
        trigger_type = raw.get("type")

        if trigger_type == "changed_paths":
            paths = [str(path) for path in raw.get("paths", [])]
            reasons = tuple(
                f"changed path: {file_path}" for file_path in files if path_matches(file_path, paths)
            )
            if reasons:
                matches.append(ReviewMatch(name=name, severity=severity, reasons=reasons))

        elif trigger_type == "evidence_gap":
            paths = [str(path) for path in raw.get("paths", [])]
            evidence_paths = [str(path) for path in raw.get("evidence_paths", [])]
            monitored = [file_path for file_path in files if path_matches(file_path, paths)]
            evidence_present = any(path_matches(file_path, evidence_paths) for file_path in files)
            if monitored and not evidence_present:
                reasons = tuple(
                    [f"changed path without evidence: {path}" for path in monitored]
                    + [f"expected evidence path patterns: {', '.join(evidence_paths)}"]
                )
                matches.append(ReviewMatch(name=name, severity=severity, reasons=reasons))

        elif trigger_type == "cross_boundary_change":
            raw_boundaries = raw.get("boundaries", {})
            min_boundaries = int(raw.get("min_boundaries", 2))
            boundary_hits: dict[str, list[str]] = {}
            if isinstance(raw_boundaries, dict):
                for boundary_name, patterns in raw_boundaries.items():
                    if not isinstance(patterns, list):
                        continue
                    boundary_files = [
                        file_path
                        for file_path in files
                        if path_matches(file_path, [str(pattern) for pattern in patterns])
                    ]
                    if boundary_files:
                        boundary_hits[str(boundary_name)] = boundary_files
            if len(boundary_hits) >= min_boundaries:
                reasons = tuple(
                    f"changed boundary {boundary}: {', '.join(boundary_files)}"
                    for boundary, boundary_files in boundary_hits.items()
                )
                matches.append(ReviewMatch(name=name, severity=severity, reasons=reasons))

        elif trigger_type == "diff_size":
            file_count, added_lines, deleted_lines = diff_stats
            reasons: list[str] = []
            max_files = raw.get("max_files")
            max_added = raw.get("max_added_lines")
            max_deleted = raw.get("max_deleted_lines")
            if isinstance(max_files, int) and file_count > max_files:
                reasons.append(f"diff touched {file_count} files (threshold: {max_files})")
            if isinstance(max_added, int) and added_lines > max_added:
                reasons.append(f"diff added {added_lines} lines (threshold: {max_added})")
            if isinstance(max_deleted, int) and deleted_lines > max_deleted:
                reasons.append(f"diff deleted {deleted_lines} lines (threshold: {max_deleted})")
            if reasons:
                matches.append(ReviewMatch(name=name, severity=severity, reasons=tuple(reasons)))

    return matches


def cmd_suggest_verification(args: argparse.Namespace) -> int:
    files = resolve_files(args)
    config = load_config()
    surfaces = surfaces_for_files(files, load_surfaces(config))

    print(f"base: {args.base}")
    print(f"changed_files: {len(files)}")
    if files:
        for file_path in files:
            print(f"- {file_path}")

    if not surfaces:
        print("changed_surfaces: none")
        print("suggested_command: none")
        return 0

    print(f"changed_surfaces: {' '.join(surfaces)}")
    print(f"suggested_command: zsh scripts/verify-surface {' '.join(surfaces)}")
    print("")
    print(dry_run_verify_surface(surfaces))
    return 0


def cmd_review_trigger(args: argparse.Namespace) -> int:
    files = resolve_files(args)
    config = load_config()
    matches = evaluate_review_triggers(files, config, args.base)

    print(f"base: {args.base}")
    print(f"changed_files: {len(files)}")
    if files:
        for file_path in files:
            print(f"- {file_path}")

    if not matches:
        print("human_review_required: no")
        return 0

    print("human_review_required: yes")
    for match in matches:
        print(f"- {match.name} [{match.severity}]")
        for reason in match.reasons:
            print(f"  reason: {reason}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coke-native guardrail helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("suggest-verification", "review-trigger"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--base", default="HEAD")
        subparser.add_argument("--files", action="append", default=[])
        if name == "suggest-verification":
            subparser.set_defaults(func=cmd_suggest_verification)
        else:
            subparser.set_defaults(func=cmd_review_trigger)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
