from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CallTarget:
    module: str
    attr: str
    receiver: ast.AST | None = None


def collect_import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {
        "__import__": "builtins.__import__",
        "eval": "builtins.eval",
        "exec": "builtins.exec",
        "getattr": "builtins.getattr",
        "open": "builtins.open",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", maxsplit=1)[0]
                aliases[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", maxsplit=1)[0]
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
    return aliases


def resolve_call_target(
    func: ast.expr,
    import_aliases: dict[str, str],
    assignments: dict[str, ast.AST],
    seen: frozenset[str] = frozenset(),
) -> CallTarget:
    if isinstance(func, ast.Name):
        return _resolve_name(func.id, import_aliases, assignments, seen)
    if isinstance(func, ast.Attribute):
        return _resolve_attribute(func, import_aliases, assignments, seen)
    if isinstance(func, ast.Call):
        return _resolve_getattr_call(func, import_aliases, assignments, seen)
    return CallTarget("", "")


def _resolve_name(
    name: str,
    import_aliases: dict[str, str],
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> CallTarget:
    if name in seen:
        return CallTarget("", "")
    assigned = assignments.get(name)
    if assigned is not None:
        return _resolve_assigned_callable(
            assigned,
            import_aliases,
            assignments,
            seen | {name},
        )
    qualified = import_aliases.get(name, f"builtins.{name}")
    return _target_from_qualified(qualified)


def _resolve_assigned_callable(
    expr: ast.AST,
    import_aliases: dict[str, str],
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> CallTarget:
    if isinstance(expr, ast.Name):
        return _resolve_name(expr.id, import_aliases, assignments, seen)
    if isinstance(expr, ast.Attribute):
        return _resolve_attribute(expr, import_aliases, assignments, seen)
    if isinstance(expr, ast.Call):
        return _resolve_getattr_call(expr, import_aliases, assignments, seen)
    return CallTarget("", "")


def _resolve_attribute(
    expr: ast.Attribute,
    import_aliases: dict[str, str],
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> CallTarget:
    if isinstance(expr.value, ast.Name):
        qualified_base = import_aliases.get(expr.value.id)
        if qualified_base is not None:
            return CallTarget(qualified_base, expr.attr)
        assigned = assignments.get(expr.value.id)
        if assigned is not None:
            imported_module = _imported_module_name(
                assigned,
                import_aliases,
                assignments,
                seen | {expr.value.id},
            )
            if imported_module is not None:
                return CallTarget(imported_module, expr.attr)
    if isinstance(expr.value, ast.Call):
        imported_module = _imported_module_name(
            expr.value,
            import_aliases,
            assignments,
            seen,
        )
        if imported_module is not None:
            return CallTarget(imported_module, expr.attr)
    return CallTarget("", expr.attr, expr.value)


def _resolve_getattr_call(
    expr: ast.Call,
    import_aliases: dict[str, str],
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> CallTarget:
    call_target = resolve_call_target(expr.func, import_aliases, assignments, seen)
    if (call_target.module, call_target.attr) != ("builtins", "getattr"):
        return CallTarget("", "")
    if len(expr.args) < 2:
        return CallTarget("", "")
    attr = _literal_str(expr.args[1])
    if attr is None:
        return CallTarget("", "")
    receiver = expr.args[0]
    if isinstance(receiver, ast.Name):
        qualified_base = import_aliases.get(receiver.id)
        if qualified_base is not None:
            return CallTarget(qualified_base, attr)
        assigned = assignments.get(receiver.id)
        if assigned is not None:
            imported_module = _imported_module_name(
                assigned,
                import_aliases,
                assignments,
                seen | {receiver.id},
            )
            if imported_module is not None:
                return CallTarget(imported_module, attr)
    if isinstance(receiver, ast.Call):
        imported_module = _imported_module_name(
            receiver,
            import_aliases,
            assignments,
            seen,
        )
        if imported_module is not None:
            return CallTarget(imported_module, attr)
    return CallTarget("", attr, receiver)


def _imported_module_name(
    expr: ast.AST,
    import_aliases: dict[str, str],
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> str | None:
    if not isinstance(expr, ast.Call):
        return None
    target = resolve_call_target(expr.func, import_aliases, assignments, seen)
    if not (
        (target.module, target.attr) == ("importlib", "import_module")
        or (target.module, target.attr) == ("builtins", "__import__")
    ):
        return None
    if not expr.args:
        return None
    module = _literal_str(expr.args[0])
    return module.split(".", maxsplit=1)[0] if module else None


def _target_from_qualified(qualified: str) -> CallTarget:
    if "." in qualified:
        module, attr = qualified.rsplit(".", maxsplit=1)
        return CallTarget(module, attr)
    return CallTarget(qualified, "")


def _literal_str(node: ast.AST) -> str | None:
    return (
        node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        else None
    )
