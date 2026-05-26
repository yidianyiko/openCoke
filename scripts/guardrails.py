#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "docs" / "fitness" / "surfaces.yaml"
OWNERSHIP_REGISTRY_PATH = ROOT / "docs" / "fitness" / "ownership-registry.yaml"

_STATIC_IMPORT_RE = re.compile(
    r"""
    ^[ \t]*
    import\b
    (?P<body>[\s\S]*?)
    ['"]([^'"\n]+)['"]
    """,
    re.MULTILINE | re.VERBOSE,
)
_STATIC_EXPORT_RE = re.compile(
    r"""
    ^[ \t]*
    export\s+(?:\*|\{[\s\S]*?\})\s+from\s*
    ['"]([^'"\n]+)['"]
    """,
    re.MULTILINE | re.VERBOSE,
)
_DYNAMIC_IMPORT_RE = re.compile(
    r"""
    ^[ \t]*
    (?:(?:return|await)\s+|(?:const|let|var)\s+\w+\s*=\s*(?:await\s*)?)?
    import\s*\(\s*['"]([^'"\n]+)['"]
    """,
    re.MULTILINE | re.VERBOSE,
)
_REQUIRE_RE = re.compile(
    r"""
    ^[ \t]*
    (?:(?:const|let|var)\s+[\w{}\s,*]+\s*=\s*)?
    require\s*\(\s*['"]([^'"\n]+)['"]
    """,
    re.MULTILINE | re.VERBOSE,
)


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
            surfaces.append(
                Surface(name=name, paths=tuple(str(path) for path in paths))
            )
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
        ["git", "diff", "--name-only", "--diff-filter=ACMRD", base],
        ["git", "diff", "--name-only", "--diff-filter=ACMRD"],
        ["git", "diff", "--name-only", "--diff-filter=ACMRD", "--cached"],
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
        files.extend(
            line.strip() for line in result.stdout.splitlines() if line.strip()
        )

    deduped: list[str] = []
    seen: set[str] = set()
    for file_path in files:
        if file_path not in seen:
            seen.add(file_path)
            deduped.append(file_path)
    return deduped


def collect_tracked_web_files() -> list[str]:
    gateway_root = ROOT / "gateway"
    result = subprocess.run(
        ["git", "ls-files", "packages/web"],
        cwd=gateway_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"failed to list nested gateway web files: {detail}")
    files: list[str] = []
    for line in result.stdout.splitlines():
        normalized = line.strip().lstrip("./")
        if normalized.startswith("packages/web/"):
            files.append(f"gateway/{normalized}")
    return files


def is_forbidden_backend_channel_target(target: str) -> bool:
    normalized = target.replace("\\", "/")
    forbidden_path_fragments = (
        "api/src/channel",
        "gateway/packages/api/src/channel",
    )
    forbidden_aliases = ("@coke/api-channel",)
    return (
        any(fragment in normalized for fragment in forbidden_path_fragments)
        or normalized in forbidden_aliases
    )


def check_import_boundaries(
    files: list[str],
    read_text=lambda path: (ROOT / path).read_text(encoding="utf-8"),
) -> list[str]:
    errors: list[str] = []
    forbidden_named_symbols = ("CHANNEL_CONFIG_SCHEMA", "ChannelConfigField")
    for file_path in files:
        normalized = file_path.strip().lstrip("./")
        if not normalized.startswith("gateway/packages/web/"):
            continue
        if not normalized.endswith((".ts", ".tsx", ".mts")):
            continue
        try:
            text = read_text(normalized)
        except FileNotFoundError:
            continue
        # Backend-only paths are forbidden in frontend import statements.
        for match in _STATIC_IMPORT_RE.finditer(text):
            target = match.group(2)
            if is_forbidden_backend_channel_target(target):
                if target == "@coke/api-channel":
                    errors.append(
                        f"{normalized} imports backend-only channel alias: {target}"
                    )
                else:
                    errors.append(
                        f"{normalized} imports backend-only channel internals: {target}"
                    )
            for symbol in forbidden_named_symbols:
                if re.search(rf"\b{re.escape(symbol)}\b", match.group("body")):
                    errors.append(
                        f"{normalized} imports backend-only channel symbol: {symbol}"
                    )
        for pattern in (_STATIC_EXPORT_RE, _DYNAMIC_IMPORT_RE, _REQUIRE_RE):
            for match in pattern.finditer(text):
                target = match.group(1)
                if not is_forbidden_backend_channel_target(target):
                    continue
                if target == "@coke/api-channel":
                    errors.append(
                        f"{normalized} imports backend-only channel alias: {target}"
                    )
                    continue
                errors.append(
                    f"{normalized} imports backend-only channel internals: {target}"
                )
    return errors


def load_ownership_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or OWNERSHIP_REGISTRY_PATH
    return yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}


def expected_route_registry_paths() -> set[str]:
    routes_root = ROOT / "gateway" / "packages" / "api" / "src" / "routes"
    return {
        str(path.relative_to(ROOT))
        for path in routes_root.glob("*.ts")
        if not path.name.endswith(".test.ts")
    }


def validate_ownership_registry(
    registry: dict[str, Any] | None = None,
) -> list[str]:
    data = registry or load_ownership_registry()
    systems = {str(system) for system in data.get("systems", [])}
    errors: list[str] = []
    registered_route_paths: set[str] = set()

    for section in ("routes", "contracts"):
        for item in data.get(section, []):
            path = str(item.get("path", ""))
            owner = str(item.get("owner", ""))
            if section == "routes" and path:
                registered_route_paths.add(path)
            if path and not (ROOT / path).exists():
                errors.append(f"ownership registry {section[:-1]} missing file: {path}")
            if owner not in systems:
                errors.append(f"ownership registry invalid owner {owner} for {path}")
            secondary = item.get("secondary_owner")
            if secondary is not None and str(secondary) not in systems:
                errors.append(
                    f"ownership registry invalid secondary_owner {secondary} for {path}"
                )

    for path in sorted(expected_route_registry_paths() - registered_route_paths):
        errors.append(f"ownership registry missing route entry: {path}")
    return errors


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


def collect_diff_stats(
    base: str, files: list[str] | None = None
) -> tuple[int, int, int]:
    command = ["git", "diff", "--numstat", "--diff-filter=ACMRD", base]
    if files:
        command.extend(["--", *files])
    result = subprocess.run(
        command,
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
    diff_stats = collect_diff_stats(base, files)

    for raw in triggers:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "unknown"))
        severity = str(raw.get("severity", "medium"))
        trigger_type = raw.get("type")

        if trigger_type == "changed_paths":
            paths = [str(path) for path in raw.get("paths", [])]
            reasons = tuple(
                f"changed path: {file_path}"
                for file_path in files
                if path_matches(file_path, paths)
            )
            if reasons:
                matches.append(
                    ReviewMatch(name=name, severity=severity, reasons=reasons)
                )

        elif trigger_type == "evidence_gap":
            paths = [str(path) for path in raw.get("paths", [])]
            evidence_paths = [str(path) for path in raw.get("evidence_paths", [])]
            monitored = [
                file_path for file_path in files if path_matches(file_path, paths)
            ]
            evidence_present = any(
                path_matches(file_path, evidence_paths) for file_path in files
            )
            if monitored and not evidence_present:
                reasons = tuple(
                    [f"changed path without evidence: {path}" for path in monitored]
                    + [f"expected evidence path patterns: {', '.join(evidence_paths)}"]
                )
                matches.append(
                    ReviewMatch(name=name, severity=severity, reasons=reasons)
                )

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
                        if path_matches(
                            file_path, [str(pattern) for pattern in patterns]
                        )
                    ]
                    if boundary_files:
                        boundary_hits[str(boundary_name)] = boundary_files
            if len(boundary_hits) >= min_boundaries:
                reasons = tuple(
                    f"changed boundary {boundary}: {', '.join(boundary_files)}"
                    for boundary, boundary_files in boundary_hits.items()
                )
                matches.append(
                    ReviewMatch(name=name, severity=severity, reasons=reasons)
                )

        elif trigger_type == "diff_size":
            file_count, added_lines, deleted_lines = diff_stats
            reasons: list[str] = []
            max_files = raw.get("max_files")
            max_added = raw.get("max_added_lines")
            max_deleted = raw.get("max_deleted_lines")
            if isinstance(max_files, int) and file_count > max_files:
                reasons.append(
                    f"diff touched {file_count} files (threshold: {max_files})"
                )
            if isinstance(max_added, int) and added_lines > max_added:
                reasons.append(
                    f"diff added {added_lines} lines (threshold: {max_added})"
                )
            if isinstance(max_deleted, int) and deleted_lines > max_deleted:
                reasons.append(
                    f"diff deleted {deleted_lines} lines (threshold: {max_deleted})"
                )
            if reasons:
                matches.append(
                    ReviewMatch(name=name, severity=severity, reasons=tuple(reasons))
                )

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
        print("risk_triggers: no")
        return 0

    print("human_review_required: no")
    print("risk_triggers: yes")
    for match in matches:
        print(f"- {match.name} [{match.severity}]")
        for reason in match.reasons:
            print(f"  reason: {reason}")
    return 0


def cmd_check_ownership_registry(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry) if args.registry else None
    errors = validate_ownership_registry(load_ownership_registry(registry_path))
    if not errors:
        print("OK ownership registry")
        return 0
    for error in errors:
        print(error)
    return 1


def cmd_check_import_boundaries(args: argparse.Namespace) -> int:
    try:
        files = resolve_files(args) if args.files else collect_tracked_web_files()
    except RuntimeError as error:
        print(error)
        return 1
    if not files:
        print("MISS no tracked gateway web files found for import-boundary check")
        return 1
    errors = check_import_boundaries(files)
    if not errors:
        print("OK import boundaries")
        return 0
    for error in errors:
        print(error)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coke-native guardrail helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in (
        "suggest-verification",
        "review-trigger",
        "check-import-boundaries",
        "check-ownership-registry",
    ):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--base", default="HEAD")
        subparser.add_argument("--files", action="append", default=[])
        if name == "check-ownership-registry":
            subparser.add_argument("--registry", default="")
        if name == "suggest-verification":
            subparser.set_defaults(func=cmd_suggest_verification)
        elif name == "review-trigger":
            subparser.set_defaults(func=cmd_review_trigger)
        elif name == "check-import-boundaries":
            subparser.set_defaults(func=cmd_check_import_boundaries)
        else:
            subparser.set_defaults(func=cmd_check_ownership_registry)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
