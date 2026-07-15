from __future__ import annotations

import ast

PATH_CONTENT = "content"
PATH_FILE = "file"
PATH_REPO = "repo"
PATH_SCRIPT_DIR = "script_dir"
PATH_UNSAFE = "unsafe"
PATH_UNKNOWN = "unknown"


def call_opens_for_write(node: ast.Call, mode_arg_index: int) -> bool:
    mode_node = node.args[mode_arg_index] if len(node.args) > mode_arg_index else None
    for keyword in node.keywords:
        if keyword.arg == "mode":
            mode_node = keyword.value
    if mode_node is None:
        return False
    mode = _literal_str(mode_node)
    if mode is None:
        return True
    return any(token in mode for token in ("w", "a", "x", "+"))


def expression_is_content_path(
    expr: ast.AST,
    assignments: dict[str, ast.AST],
    seen: frozenset[str] = frozenset(),
) -> bool:
    return _path_state(expr, assignments, seen) == PATH_CONTENT


def _path_state(
    expr: ast.AST,
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> str:
    if isinstance(expr, ast.Name):
        if expr.id == "__file__":
            return PATH_FILE
        if expr.id in seen:
            return PATH_UNKNOWN
        assigned = assignments.get(expr.id)
        if assigned is None:
            return PATH_UNKNOWN
        return _path_state(assigned, assignments, seen | {expr.id})
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return _state_from_relative_path(expr.value)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        left = _path_state(expr.left, assignments, seen)
        right = _literal_path_parts(expr.right, assignments, seen)
        if right is None:
            return PATH_UNKNOWN
        return _join_path_state(left, right)
    if isinstance(expr, ast.Call):
        return _call_path_state(expr, assignments, seen)
    if isinstance(expr, ast.Attribute):
        return _attribute_path_state(expr, assignments, seen)
    return PATH_UNKNOWN


def _call_path_state(
    expr: ast.Call,
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> str:
    func = expr.func
    if isinstance(func, ast.Name) and func.id == "Path":
        if not expr.args:
            return PATH_UNKNOWN
        base = _path_state(expr.args[0], assignments, seen)
        if len(expr.args) == 1:
            return base
        rest = _literal_path_args(expr.args[1:], assignments, seen)
        if rest is None:
            return PATH_UNKNOWN
        return _join_path_state(base, rest)
    if isinstance(func, ast.Attribute):
        base = _path_state(func.value, assignments, seen)
        if func.attr in {"resolve", "absolute", "expanduser"}:
            return base
        if func.attr in {"with_suffix", "with_name"}:
            return base if base == PATH_CONTENT else PATH_UNKNOWN
    return PATH_UNKNOWN


def _attribute_path_state(
    expr: ast.Attribute,
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> str:
    base = _path_state(expr.value, assignments, seen)
    if expr.attr != "parent":
        return PATH_UNKNOWN
    if base == PATH_FILE:
        return PATH_SCRIPT_DIR
    if base == PATH_SCRIPT_DIR:
        return PATH_REPO
    if base == PATH_REPO or base == PATH_CONTENT:
        return PATH_UNSAFE
    return PATH_UNKNOWN


def _literal_path_parts(
    expr: ast.AST,
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> tuple[str, ...] | None:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return _split_path(expr.value)
    if isinstance(expr, ast.Name):
        if expr.id in seen:
            return None
        assigned = assignments.get(expr.id)
        if assigned is None:
            return None
        return _literal_path_parts(assigned, assignments, seen | {expr.id})
    return None


def _literal_path_args(
    exprs: list[ast.expr],
    assignments: dict[str, ast.AST],
    seen: frozenset[str],
) -> tuple[str, ...] | None:
    result: list[str] = []
    for expr in exprs:
        parts = _literal_path_parts(expr, assignments, seen)
        if parts is None:
            return None
        result.extend(parts)
    return tuple(result)


def _join_path_state(left: str, right: tuple[str, ...]) -> str:
    if left == PATH_UNSAFE or _parts_escape(right):
        return PATH_UNSAFE
    if left == PATH_CONTENT:
        return PATH_CONTENT
    if left == PATH_REPO and right[:1] == ("content",):
        return PATH_CONTENT
    return PATH_UNKNOWN


def _state_from_relative_path(text: str) -> str:
    parts = _split_path(text)
    if not parts or _parts_escape(parts):
        return PATH_UNSAFE
    return PATH_CONTENT if parts[0] == "content" else PATH_UNKNOWN


def _split_path(text: str) -> tuple[str, ...]:
    if text.startswith("/"):
        return ("..",)
    return tuple(
        part for part in text.replace("\\", "/").split("/") if part not in {"", "."}
    )


def _parts_escape(parts: tuple[str, ...]) -> bool:
    return any(part == ".." for part in parts)


def _literal_str(node: ast.AST) -> str | None:
    return (
        node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        else None
    )
