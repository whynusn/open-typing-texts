from __future__ import annotations

import ast
from pathlib import Path

from .script_call_safety import (
    CallTarget,
    collect_import_aliases,
    resolve_call_target,
)
from .script_path_safety import call_opens_for_write, expression_is_content_path
from .validation_types import ValidationIssue, ValidationReport

BANNED_IMPORTS = frozenset({"ctypes", "pty", "socket", "subprocess"})
BANNED_BUILTIN_CALLS = frozenset({"eval", "exec"})
BANNED_ATTRIBUTE_CALLS = frozenset({("os", "system")})
BANNED_FROM_IMPORTS = frozenset({("os", "system")})
BANNED_DYNAMIC_IMPORTS = BANNED_IMPORTS
WRITE_METHODS = frozenset({"write_text", "write_bytes"})
OPEN_METHODS = frozenset({"open"})
MOVE_METHODS = frozenset({"replace", "rename"})
OS_MOVE_METHODS = frozenset({"replace", "rename", "renames"})
SHUTIL_COPY_METHODS = frozenset({"copy", "copy2", "copyfile", "copytree"})
SHUTIL_MOVE_METHODS = frozenset({"move"})


def validate_script_file(path: Path) -> ValidationReport:
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ValidationReport(
            (ValidationIssue("missing_file", str(path), "file does not exist"),)
        )
    except OSError as error:
        return ValidationReport((ValidationIssue("read_error", str(path), str(error)),))
    return validate_script_source(source, str(path))


def validate_script_source(
    source: str, display_path: str = "<source>"
) -> ValidationReport:
    try:
        tree = ast.parse(source, filename=display_path)
    except SyntaxError as error:
        return ValidationReport(
            (ValidationIssue("invalid_python", display_path, str(error)),)
        )
    issues: list[ValidationIssue] = []
    assignments = _collect_assignments(tree)
    import_aliases = collect_import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                issues.extend(_validate_import(alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            issues.extend(_validate_import(node.module or "", node.lineno))
            issues.extend(_validate_from_import(node))
        elif isinstance(node, ast.Call):
            target = resolve_call_target(node.func, import_aliases, assignments)
            issue = _validate_call(node, target)
            if issue is not None:
                issues.append(issue)
            dynamic_issue = _validate_dynamic_import(node, target)
            if dynamic_issue is not None:
                issues.append(dynamic_issue)
            write_issue = _validate_write_call(node, assignments, target)
            if write_issue is not None:
                issues.append(write_issue)
    return ValidationReport(tuple(issues))


def _validate_import(module: str, lineno: int) -> list[ValidationIssue]:
    root = module.split(".", maxsplit=1)[0]
    if root not in BANNED_IMPORTS:
        return []
    return [
        ValidationIssue(
            "banned_import",
            f"line {lineno}",
            f"script imports high-risk module {root}",
        )
    ]


def _validate_from_import(node: ast.ImportFrom) -> list[ValidationIssue]:
    module = node.module or ""
    issues: list[ValidationIssue] = []
    for alias in node.names:
        if (module, alias.name) in BANNED_FROM_IMPORTS:
            issues.append(
                ValidationIssue(
                    "banned_import",
                    f"line {node.lineno}",
                    f"script imports high-risk function {module}.{alias.name}",
                )
            )
    return issues


def _validate_call(node: ast.Call, target: CallTarget) -> ValidationIssue | None:
    if target.module == "builtins" and target.attr in BANNED_BUILTIN_CALLS:
        return ValidationIssue(
            "banned_call",
            f"line {node.lineno}",
            f"script calls high-risk function {target.attr}",
        )
    if (target.module, target.attr) in BANNED_ATTRIBUTE_CALLS:
        return ValidationIssue(
            "banned_call",
            f"line {node.lineno}",
            f"script calls high-risk function {target.module}.{target.attr}",
        )
    return None


def _validate_dynamic_import(
    node: ast.Call,
    target: CallTarget,
) -> ValidationIssue | None:
    if not node.args:
        return None
    if not (
        (target.module, target.attr) == ("importlib", "import_module")
        or (target.module, target.attr) == ("builtins", "__import__")
    ):
        return None
    module = _literal_str(node.args[0])
    if module is None:
        return ValidationIssue(
            "banned_dynamic_import",
            f"line {node.lineno}",
            "script dynamically imports a non-literal module",
        )
    root = module.split(".", maxsplit=1)[0]
    if root not in BANNED_DYNAMIC_IMPORTS:
        return None
    return ValidationIssue(
        "banned_dynamic_import",
        f"line {node.lineno}",
        f"script dynamically imports high-risk module {root}",
    )


def _validate_write_call(
    node: ast.Call,
    assignments: dict[str, ast.AST],
    target: CallTarget,
) -> ValidationIssue | None:
    if target.receiver is not None and target.attr in WRITE_METHODS:
        if expression_is_content_path(target.receiver, assignments):
            return None
        return ValidationIssue(
            "unsafe_write_path",
            f"line {node.lineno}",
            "script write target must resolve under content/",
        )
    if (
        target.receiver is not None
        and target.attr in MOVE_METHODS
        and len(node.args) == 1
    ):
        move_target = node.args[0] if node.args else None
        if (
            expression_is_content_path(target.receiver, assignments)
            and move_target is not None
            and expression_is_content_path(move_target, assignments)
        ):
            return None
        return ValidationIssue(
            "unsafe_write_path",
            f"line {node.lineno}",
            "script move target must resolve under content/",
        )
    if target.module == "os" and target.attr in OS_MOVE_METHODS:
        if len(node.args) >= 2 and all(
            expression_is_content_path(arg, assignments) for arg in node.args[:2]
        ):
            return None
        return ValidationIssue(
            "unsafe_write_path",
            f"line {node.lineno}",
            "script move target must resolve under content/",
        )
    if target.module == "shutil" and target.attr in SHUTIL_COPY_METHODS:
        copy_target = node.args[1] if len(node.args) >= 2 else None
        if copy_target is not None and expression_is_content_path(
            copy_target, assignments
        ):
            return None
        return ValidationIssue(
            "unsafe_write_path",
            f"line {node.lineno}",
            "script copy target must resolve under content/",
        )
    if target.module == "shutil" and target.attr in SHUTIL_MOVE_METHODS:
        if len(node.args) >= 2 and all(
            expression_is_content_path(arg, assignments) for arg in node.args[:2]
        ):
            return None
        return ValidationIssue(
            "unsafe_write_path",
            f"line {node.lineno}",
            "script move target must resolve under content/",
        )
    if target.receiver is not None and target.attr in OPEN_METHODS:
        if not call_opens_for_write(node, mode_arg_index=0):
            return None
        if expression_is_content_path(target.receiver, assignments):
            return None
        return ValidationIssue(
            "unsafe_write_path",
            f"line {node.lineno}",
            "script open target must resolve under content/ when writing",
        )
    if (
        target.module == "builtins"
        and target.attr == "open"
        and call_opens_for_write(node, mode_arg_index=1)
    ):
        if node.args and expression_is_content_path(node.args[0], assignments):
            return None
        return ValidationIssue(
            "unsafe_write_path",
            f"line {node.lineno}",
            "script open target must resolve under content/ when writing",
        )
    return None


def _collect_assignments(tree: ast.AST) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            assignments[node.target.id] = node.value
    return assignments


def _literal_str(node: ast.AST) -> str | None:
    return (
        node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        else None
    )
