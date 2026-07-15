from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonMap: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()
    normalized_entries: int = 0
    char_count: int = 0

    @property
    def valid(self) -> bool:
        return not self.issues

    def to_dict(self) -> JsonMap:
        return {
            "valid": self.valid,
            "normalized_entries": self.normalized_entries,
            "char_count": self.char_count,
            "issues": [
                {"code": issue.code, "path": issue.path, "message": issue.message}
                for issue in self.issues
            ],
        }


def format_report(label: str, report: ValidationReport) -> str:
    lines = [f"{'PASS' if report.valid else 'FAIL'} {label}"]
    for issue in report.issues:
        lines.append(f"{issue.code} {issue.path}: {issue.message}")
    return "\n".join(lines)
