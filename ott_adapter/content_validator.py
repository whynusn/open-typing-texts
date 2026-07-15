from __future__ import annotations

from .ott_core import valid_identifier
from .validation_helpers import string_value
from .validation_types import JsonMap, ValidationIssue, ValidationReport


def validate_content_data(
    data: JsonMap,
    expected_source_key: str = "",
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    source_key = string_value(data.get("source_key"))
    if not valid_identifier(source_key):
        issues.append(
            ValidationIssue(
                "invalid_source_key",
                "$.source_key",
                "source_key must match ^[A-Za-z0-9_]+$",
            )
        )
    if expected_source_key and source_key != expected_source_key:
        issues.append(
            ValidationIssue(
                "source_key_filename_mismatch",
                "$.source_key",
                "source_key must match the content filename",
            )
        )
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        issues.append(
            ValidationIssue(
                "invalid_metadata",
                "$.metadata",
                "metadata must be an object",
            )
        )

    entries = data.get("entries")
    top_content = string_value(data.get("content"))
    normalized_entries = 0
    char_count = 0
    if isinstance(entries, list) and entries:
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                issues.append(
                    ValidationIssue(
                        "invalid_entry",
                        f"$.entries[{index}]",
                        "entry must be an object",
                    )
                )
                continue
            issues.extend(_validate_legacy_entry(entry, index))
            content = string_value(entry.get("content"))
            if content:
                normalized_entries += 1
                char_count += len(content)
    elif not top_content:
        issues.append(
            ValidationIssue(
                "missing_content",
                "$.content",
                "content must be a non-empty string when entries are absent",
            )
        )
    else:
        normalized_entries = 1
        char_count = len(top_content)
    return ValidationReport(
        tuple(issues),
        0 if issues else normalized_entries,
        char_count,
    )


def _validate_legacy_entry(data: JsonMap, index: int) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not string_value(data.get("title")):
        issues.append(
            ValidationIssue(
                "missing_entry_title",
                f"$.entries[{index}].title",
                "entry title is required",
            )
        )
    if not string_value(data.get("content")):
        issues.append(
            ValidationIssue(
                "missing_entry_content",
                f"$.entries[{index}].content",
                "entry content is required",
            )
        )
    for key in ("entry_id", "revision_id"):
        value = data.get(key)
        if value is not None and not valid_identifier(string_value(value)):
            issues.append(
                ValidationIssue(
                    f"invalid_{key}",
                    f"$.entries[{index}].{key}",
                    f"{key} must be an identifier",
                )
            )
    return issues
