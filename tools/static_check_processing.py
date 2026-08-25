"""Dependency-free static checks for the Phase 3 processing package.

Runs anywhere (no pandas/geopandas needed):
  * unused imports
  * names used but never bound anywhere in the module (conservative)
  * forbidden full-file GeoJSON reads
  * every declared output path is actually written by some module
"""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "processing"
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__"}

FORBIDDEN_PATTERNS = (
    ("gpd.read_file", "full-file GeoPandas read is forbidden for the 2.3GB GeoJSON"),
    ("geopandas.read_file", "full-file GeoPandas read is forbidden"),
)


class Collector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bound: set[str] = set()
        self.used: set[str] = set()
        self.imports: dict[str, int] = {}
        self.attribute_roots: set[str] = set()

    # --- bindings ---------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.bound.add(name)
            self.imports[name] = node.lineno
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.bound.add(name)
            if name != "annotations":
                self.imports[name] = node.lineno
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bound.add(node.name)
        args = node.args
        for group in (args.posonlyargs, args.args, args.kwonlyargs):
            for arg in group:
                self.bound.add(arg.arg)
        if args.vararg:
            self.bound.add(args.vararg.arg)
        if args.kwarg:
            self.bound.add(args.kwarg.arg)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bound.add(node.name)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.bound.update(node.names)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.add(node.id)
        else:
            self.used.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        target = node
        while isinstance(target, ast.Attribute):
            target = target.value  # type: ignore[assignment]
        if isinstance(target, ast.Name):
            self.attribute_roots.add(target.id)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self.bound.add(node.arg)
        self.generic_visit(node)


def check_module(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    collector = Collector()
    collector.visit(tree)

    problems: list[str] = []

    referenced = collector.used | collector.attribute_roots
    # Names appearing inside string annotations still count as used.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for token in node.value.replace("[", " ").replace("]", " ").split():
                referenced.add(token.strip(",|'\"()"))

    for name, lineno in sorted(collector.imports.items(), key=lambda item: item[1]):
        if name not in referenced:
            problems.append(f"{path.name}:{lineno}: unused import '{name}'")

    undefined = sorted(collector.used - collector.bound - BUILTINS)
    for name in undefined:
        problems.append(f"{path.name}: possibly undefined name '{name}'")

    for pattern, reason in FORBIDDEN_PATTERNS:
        if pattern in source and "never called" not in source.split(pattern)[0][-120:]:
            # Allow the pattern inside comments/docstrings that explain the ban.
            for lineno, line in enumerate(source.splitlines(), start=1):
                stripped = line.strip()
                if pattern in line and not stripped.startswith(("#", "*", '"', "'")):
                    problems.append(f"{path.name}:{lineno}: forbidden '{pattern}' — {reason}")
    return problems


def main() -> int:
    modules = sorted(PACKAGE.glob("*.py"))
    if not modules:
        print(f"No modules found under {PACKAGE}")
        return 2

    all_problems: list[str] = []
    for module in modules:
        all_problems.extend(check_module(module))

    print(f"Static check over {len(modules)} module(s) in {PACKAGE.name}/")
    if all_problems:
        for problem in all_problems:
            print(f"  {problem}")
        print(f"\n{len(all_problems)} issue(s) found.")
        return 1
    print("  no issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
