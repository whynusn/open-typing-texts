from __future__ import annotations

import json
from pathlib import Path

from .validation_types import JsonMap, JsonValue, ValidationIssue


def read_json_map(path: Path) -> tuple[JsonMap | None, list[ValidationIssue]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [ValidationIssue("missing_file", str(path), "file does not exist")]
    except json.JSONDecodeError as error:
        return None, [ValidationIssue("invalid_json", str(path), str(error))]
    except OSError as error:
        return None, [ValidationIssue("read_error", str(path), str(error))]
    if not isinstance(data, dict):
        return None, [
            ValidationIssue(
                "invalid_json_object",
                str(path),
                "top-level JSON value must be an object",
            )
        ]
    return data, []


def prefix_issues(
    issues: tuple[ValidationIssue, ...] | list[ValidationIssue],
    prefix: str,
) -> list[ValidationIssue]:
    return [
        ValidationIssue(issue.code, f"{prefix}:{issue.path}", issue.message)
        for issue in issues
    ]


def string_value(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def int_value(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else -1
