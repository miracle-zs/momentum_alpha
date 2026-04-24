from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "momentum_alpha"

CORE_MODULES = (
    "models.py",
    "strategy.py",
    "runtime.py",
    "execution.py",
    "orders.py",
    "sizing.py",
    "binance_filters.py",
    "exchange_info.py",
    "config.py",
)

FORBIDDEN_CORE_IMPORT_PREFIXES = (
    "momentum_alpha.dashboard",
    "momentum_alpha.dashboard_",
    "momentum_alpha.runtime_store",
    "momentum_alpha.runtime_reads",
    "momentum_alpha.runtime_writes",
    "momentum_alpha.runtime_schema",
    "momentum_alpha.runtime_analytics",
    "momentum_alpha.binance_client",
    "momentum_alpha.broker",
    "momentum_alpha.user_stream",
    "momentum_alpha.poll_worker",
    "momentum_alpha.stream_worker",
)

FORBIDDEN_STANDARD_IMPORTS = {
    "http.server",
    "sqlite3",
    "websocket",
}


def _imports_for(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return imports


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_core_modules_do_not_import_infrastructure_or_presentation(self) -> None:
        violations: list[str] = []
        for module_name in CORE_MODULES:
            path = SRC_ROOT / module_name
            for imported in _imports_for(path):
                if imported in FORBIDDEN_STANDARD_IMPORTS:
                    violations.append(f"{module_name} imports {imported}")
                    continue
                if any(
                    imported == prefix or imported.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_CORE_IMPORT_PREFIXES
                ):
                    violations.append(f"{module_name} imports {imported}")

        self.assertEqual([], violations)
