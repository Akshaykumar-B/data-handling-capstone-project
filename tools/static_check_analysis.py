"""Static guardrails for the Phase 4 EDA package (no data required).

Fails (exit 1) if any analysis module violates the Phase 4 constraints:
  * no GeoJSON/geometry parsing (gpd.read_file / geopandas.read_file /
    pyogrio.read_info / fiona.open) - the 2.3 GB routes file must never be read;
  * Parquet reads (pd.read_parquet) are confined to io_utils.py;
  * figures.py pins the headless Agg backend before importing pyplot;
  * every module byte-compiles.

Run:
    python -m tools.static_check_analysis
"""

from __future__ import annotations

import ast
import py_compile
import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).resolve().parents[1] / "src" / "analysis"

_BANNED_ATTR_CALLS = {
    ("gpd", "read_file"),
    ("geopandas", "read_file"),
    ("pyogrio", "read_info"),
    ("pyogrio", "read_dataframe"),
    ("fiona", "open"),
}


def _attr_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return tuple(reversed(parts))


def check_module(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        return [f"{path.name}: does not compile: {exc}"]

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            chain = _attr_chain(node.func)
            if len(chain) >= 2 and (chain[-2], chain[-1]) in _BANNED_ATTR_CALLS:
                problems.append(f"{path.name}: banned geometry read '{'.'.join(chain)}'")
            if chain[-1] == "read_parquet" and path.name != "io_utils.py":
                problems.append(
                    f"{path.name}: pd.read_parquet must be confined to io_utils.py"
                )
    return problems


def check_figures_backend() -> list[str]:
    path = ANALYSIS_DIR / "figures.py"
    source = path.read_text(encoding="utf-8")
    use_idx = source.find('matplotlib.use("Agg")')
    pyplot_idx = source.find("import matplotlib.pyplot")
    if use_idx == -1:
        return ["figures.py: must call matplotlib.use(\"Agg\") for headless determinism"]
    if pyplot_idx != -1 and use_idx > pyplot_idx:
        return ["figures.py: matplotlib.use(\"Agg\") must precede importing pyplot"]
    return []


def main() -> int:
    problems: list[str] = []
    modules = sorted(ANALYSIS_DIR.glob("*.py"))
    if not modules:
        print(f"no analysis modules found under {ANALYSIS_DIR}")
        return 1
    for module in modules:
        problems.extend(check_module(module))
    problems.extend(check_figures_backend())

    print(f"static-checked {len(modules)} analysis modules")
    if problems:
        print("FAIL:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("PASS: no banned geometry reads, parquet reads confined to io_utils, Agg backend pinned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
