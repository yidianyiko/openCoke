#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze repository to find Python modules/classes/functions that:
- are referenced only by tests, or
- appear to be unused anywhere.

Heuristic, static-only:
- Scans Python files under likely production folders:
  ('agent', 'dao', 'connector', 'util', 'entity', 'framework', 'conf')
- Excludes: 'tests', 'scripts', 'doc', 'venv-like' folders.
- Builds a symbol index (module -> top-level classes/functions)
- Builds a usage index by parsing AST Name/Attribute/Import usage.
- Classifies each symbol and module as:
   * only_used_in_tests
   * unused_everywhere
   * used_in_prod

Limitations:
- Dynamic imports/indirection won't be fully captured.
- Name-based matching can yield false positives/negatives when names collide.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# Folders we consider as production code
PROD_DIRS = ("agent", "dao", "connector", "util", "entity", "framework", "conf")
# Folders to skip globally
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "doc",
    "scripts",  # not part of runtime
    "tests",
}


def is_python_file(p: Path) -> bool:
    return p.suffix == ".py"


def to_module_name(py_path: Path) -> str:
    rel = py_path.relative_to(REPO_ROOT)
    # drop .py and convert path separators to dots
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def should_scan_file(p: Path) -> bool:
    try:
        rel = p.relative_to(REPO_ROOT)
    except Exception:
        return False
    parts = rel.parts
    if not parts:
        return False
    if parts[0] in SKIP_DIRS:
        return False
    if parts[0] not in PROD_DIRS and len(parts) > 1 and parts[1] in SKIP_DIRS:
        return False
    # Only scan files that belong to PROD_DIRS roots
    return parts[0] in PROD_DIRS


def iter_python_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune directories early
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                p = Path(dirpath) / fn
                if should_scan_file(p):
                    yield p


@dataclass
class ModuleSymbols:
    module: str
    filepath: Path
    classes: Set[str] = field(default_factory=set)
    functions: Set[str] = field(default_factory=set)


@dataclass
class UsageIndex:
    # symbol name -> set of module names where used
    prod_symbol_usage: Dict[str, Set[str]] = field(default_factory=dict)
    test_symbol_usage: Dict[str, Set[str]] = field(default_factory=dict)
    # module name -> set of module names that import it (prod-only and tests)
    prod_module_imported_by: Dict[str, Set[str]] = field(default_factory=dict)
    test_module_imported_by: Dict[str, Set[str]] = field(default_factory=dict)

    def note_symbol(self, symbol: str, user_module: str, is_test: bool) -> None:
        target = self.test_symbol_usage if is_test else self.prod_symbol_usage
        target.setdefault(symbol, set()).add(user_module)

    def note_module_import(
        self, imported_mod: str, user_module: str, is_test: bool
    ) -> None:
        target = (
            self.test_module_imported_by if is_test else self.prod_module_imported_by
        )
        target.setdefault(imported_mod, set()).add(user_module)


def collect_symbols(py_path: Path) -> Optional[ModuleSymbols]:
    try:
        code = py_path.read_text(encoding="utf-8")
        tree = ast.parse(code)
    except Exception:
        return None
    mod_name = to_module_name(py_path)
    classes: Set[str] = set()
    functions: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, ast.FunctionDef):
            functions.add(node.name)
    return ModuleSymbols(
        module=mod_name, filepath=py_path, classes=classes, functions=functions
    )


def is_test_path(p: Path) -> bool:
    try:
        rel = p.relative_to(REPO_ROOT)
    except Exception:
        return False
    return rel.parts and rel.parts[0] == "tests"


def collect_usage(py_path: Path, usage: UsageIndex) -> None:
    try:
        code = py_path.read_text(encoding="utf-8")
        tree = ast.parse(code)
    except Exception:
        return
    user_mod = to_module_name(py_path)
    in_tests = is_test_path(py_path)

    # Collect names/attributes used
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            usage.note_symbol(node.id, user_mod, in_tests)
        elif isinstance(node, ast.Attribute):
            # include attribute name as a usage token (e.g., Foo.bar)
            usage.note_symbol(node.attr, user_mod, in_tests)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    usage.note_module_import(alias.name, user_mod, in_tests)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                usage.note_module_import(node.module, user_mod, in_tests)
            for alias in node.names:
                if alias.name:
                    usage.note_symbol(alias.name, user_mod, in_tests)


def analyze() -> dict:
    # 1) Index symbols in prod modules
    prod_files = list(iter_python_files(REPO_ROOT))
    symbol_index: Dict[str, ModuleSymbols] = {}
    for p in prod_files:
        ms = collect_symbols(p)
        if ms:
            symbol_index[ms.module] = ms

    # 2) Collect usage across entire repo (prod + tests)
    usage = UsageIndex()
    all_py_files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [
            d
            for d in dirnames
            if d
            not in {
                ".git",
                ".hg",
                ".svn",
                ".venv",
                "venv",
                "env",
                "__pycache__",
                "node_modules",
            }
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                all_py_files.append(Path(dirpath) / fn)
    for p in all_py_files:
        collect_usage(p, usage)

    # 3) Classify
    only_in_tests_symbols: List[Tuple[str, str, str]] = []  # (module, kind, name)
    unused_symbols: List[Tuple[str, str, str]] = []
    used_in_prod_symbols: List[Tuple[str, str, str]] = []

    for mod, ms in symbol_index.items():
        for func in sorted(ms.functions):
            prod_used = func in usage.prod_symbol_usage and bool(
                usage.prod_symbol_usage[func]
            )
            test_used = func in usage.test_symbol_usage and bool(
                usage.test_symbol_usage[func]
            )
            if prod_used:
                used_in_prod_symbols.append((mod, "function", func))
            elif test_used:
                only_in_tests_symbols.append((mod, "function", func))
            else:
                unused_symbols.append((mod, "function", func))
        for cls in sorted(ms.classes):
            prod_used = cls in usage.prod_symbol_usage and bool(
                usage.prod_symbol_usage[cls]
            )
            test_used = cls in usage.test_symbol_usage and bool(
                usage.test_symbol_usage[cls]
            )
            if prod_used:
                used_in_prod_symbols.append((mod, "class", cls))
            elif test_used:
                only_in_tests_symbols.append((mod, "class", cls))
            else:
                unused_symbols.append((mod, "class", cls))

    # Module-level import usage (to flag entire files likely unused)
    only_in_tests_modules: List[str] = []
    unused_modules: List[str] = []
    used_in_prod_modules: List[str] = []

    prod_modules_set = set(symbol_index.keys())
    for mod in sorted(prod_modules_set):
        imported_by_prod = usage.prod_module_imported_by.get(mod, set())
        imported_by_test = usage.test_module_imported_by.get(mod, set())
        # Entry modules might not be imported by others; treat them as used if they define main runtimes
        is_entry_like = mod.startswith("agent.runner.")
        if imported_by_prod or is_entry_like:
            used_in_prod_modules.append(mod)
        elif imported_by_test:
            only_in_tests_modules.append(mod)
        else:
            # No one imports it; if it defines no symbols and isn't entry-like, likely unused
            ms = symbol_index.get(mod)
            if ms and (ms.classes or ms.functions):
                unused_modules.append(mod)
            elif not ms:
                unused_modules.append(mod)

    result = {
        "summary": {
            "prod_modules_scanned": len(prod_modules_set),
            "symbols_total": sum(
                len(ms.functions) + len(ms.classes) for ms in symbol_index.values()
            ),
            "symbols_used_in_prod": len(used_in_prod_symbols),
            "symbols_only_in_tests": len(only_in_tests_symbols),
            "symbols_unused": len(unused_symbols),
            "modules_used_in_prod": len(used_in_prod_modules),
            "modules_only_in_tests": len(only_in_tests_modules),
            "modules_unused": len(unused_modules),
        },
        "modules": {
            "used_in_prod": used_in_prod_modules,
            "only_in_tests": only_in_tests_modules,
            "unused": unused_modules,
        },
        "symbols": {
            "used_in_prod": used_in_prod_symbols,
            "only_in_tests": only_in_tests_symbols,
            "unused": unused_symbols,
        },
    }
    return result


def main() -> None:
    res = analyze()
    # Pretty print a concise report
    print("# Unused/Tests-only Analysis Report")
    print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
    print("\n## Modules only used by tests")
    for m in res["modules"]["only_in_tests"]:
        print(f"- {m}")
    print("\n## Modules likely unused")
    for m in res["modules"]["unused"]:
        print(f"- {m}")
    print("\n## Symbols only used by tests (module :: kind :: name)")
    for mod, kind, name in res["symbols"]["only_in_tests"]:
        print(f"- {mod} :: {kind} :: {name}")
    print("\n## Symbols likely unused (module :: kind :: name)")
    for mod, kind, name in res["symbols"]["unused"]:
        print(f"- {mod} :: {kind} :: {name}")


if __name__ == "__main__":
    main()
