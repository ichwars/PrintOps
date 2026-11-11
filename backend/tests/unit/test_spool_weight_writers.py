"""Track production paths that write used spool weight."""

import ast
import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "app"
_WRITE_SQL = re.compile(r'\bUPDATE\s+"?spool"?\s+SET\s+[^;]*\bweight_used\s*=', re.IGNORECASE | re.DOTALL)
_FIELD = "weight_used"


class WeightWrites(ast.NodeVisitor):
    def __init__(self):
        self.function = "<module>"
        self.writes: dict[str, int] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        outer = self.function
        self.function = node.name
        self.generic_visit(node)
        self.function = outer

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr == _FIELD and isinstance(node.ctx, ast.Store):
            self.writes[self.function] = node.lineno
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        keyword = any(k.arg == _FIELD or (name == "Spool" and k.arg is None) for k in node.keywords)
        literal_setattr = (
            name == "setattr"
            and len(node.args) >= 3
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == _FIELD
        )
        if (name in ("Spool", "values") and keyword) or literal_setattr:
            self.writes[self.function] = node.lineno
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str) and _WRITE_SQL.search(node.value):
            self.writes[self.function] = node.lineno


def find_writes():
    writes = {}
    for path in sorted(_APP.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if _FIELD not in source and "Spool(" not in source:
            continue
        visitor = WeightWrites()
        visitor.visit(ast.parse(source, filename=str(path)))
        writes.update({(path.relative_to(_APP).as_posix(), name): line for name, line in visitor.writes.items()})
    return writes


_WRITERS = {
    ("api/routes/inventory.py", "import_spools_csv"): "initialize consumption from CSV",
    ("api/routes/inventory.py", "create_spool"): "initialize from the inventory form",
    ("api/routes/inventory.py", "bulk_create_spools"): "initialize from the bulk inventory form",
    ("api/routes/inventory.py", "refill_spool"): "record consumption before refilling",
    ("api/routes/inventory.py", "merge_spools"): "retain the highest known consumption when merging",
    ("api/routes/spoolbuddy.py", "update_spool_weight"): "derive consumption from a scale reading",
    ("core/rfid_core_weight_migration.py", "repair_rfid_core_weights"): "repair legacy RFID weights",
    ("services/ams_weight_sync.py", "sync_builtin_weights"): "manual AMS weight sync",
    ("services/ams_weight_sync.py", "sync_automatic_weight"): "automatic AMS weight sync",
    ("services/github_restore.py", "_restore_spools"): "restore saved stock, including existing rows",
    ("services/spool_tag_matcher.py", "create_spool_from_tray"): "initialize a spool discovered by RFID",
    ("services/stock_reservations.py", "reconcile_filament"): "apply a production stock posting",
    ("services/usage_tracker.py", "_charge_spool"): "atomically charge a print",
}

# The update routes take the field through a schema-driven setattr loop.
_DYNAMIC = {"update_spool", "bulk_update_spools"}


def test_spool_weight_writers_are_accounted_for():
    writes = find_writes()
    extra = writes.keys() - _WRITERS.keys()
    missing = _WRITERS.keys() - writes.keys()
    assert not extra, [(path, writes[path, name], name) for path, name in sorted(extra)]
    assert not missing, sorted(missing)

    inventory = ast.parse((_APP / "api/routes/inventory.py").read_text(encoding="utf-8"))
    functions = {node.name for node in inventory.body if isinstance(node, ast.AsyncFunctionDef)}
    assert functions >= _DYNAMIC
