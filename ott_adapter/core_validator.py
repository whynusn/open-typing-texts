from __future__ import annotations

from .ott_core import sha256_text, valid_identifier
from .validation_helpers import int_value, string_value
from .validation_types import JsonMap, ValidationIssue, ValidationReport


def validate_source(data: JsonMap) -> ValidationReport:
    issues: list[ValidationIssue] = []
    if not valid_identifier(string_value(data.get("source_key"))):
        issues.append(
            ValidationIssue(
                "invalid_source_key",
                "$.source_key",
                "source_key must be an identifier",
            )
        )
    if not string_value(data.get("label")):
        issues.append(
            ValidationIssue(
                "missing_source_label",
                "$.label",
                "source label is required",
            )
        )
    for key in ("entry_count", "char_count"):
        value = data.get(key)
        if value is not None and int_value(value) < 0:
            issues.append(
                ValidationIssue(
                    f"invalid_{key}",
                    f"$.{key}",
                    f"{key} must be non-negative",
                )
            )
    return ValidationReport(tuple(issues))


def validate_entry_summary(data: JsonMap) -> ValidationReport:
    issues = _validate_entry_common(data, require_hash=False)
    if "content" in data:
        issues.append(
            ValidationIssue(
                "summary_contains_content",
                "$.content",
                "EntrySummary must not include full content",
            )
        )
    return ValidationReport(tuple(issues))


def validate_entry_detail(data: JsonMap) -> ValidationReport:
    issues = _validate_entry_common(data, require_hash=True)
    mode = string_value(data.get("content_mode"))
    content = string_value(data.get("content"))
    if mode == "inline":
        if not content:
            issues.append(
                ValidationIssue(
                    "missing_inline_content",
                    "$.content",
                    "inline detail requires content",
                )
            )
        if int_value(data.get("char_count")) != len(content):
            issues.append(
                ValidationIssue(
                    "char_count_mismatch",
                    "$.char_count",
                    "char_count must equal content length",
                )
            )
        if string_value(data.get("content_hash")) != sha256_text(content):
            issues.append(
                ValidationIssue(
                    "content_hash_mismatch",
                    "$.content_hash",
                    "content_hash must match content",
                )
            )
    elif mode == "segmented":
        issues.extend(_validate_segmented_detail(data))
    return ValidationReport(tuple(issues))


def validate_segment(data: JsonMap) -> ValidationReport:
    issues: list[ValidationIssue] = []
    for key in ("entry_id", "revision_id"):
        if not valid_identifier(string_value(data.get(key))):
            issues.append(
                ValidationIssue(
                    f"invalid_{key}",
                    f"$.{key}",
                    f"{key} must be an identifier",
                )
            )
    index = int_value(data.get("index"))
    start = int_value(data.get("start_char"))
    end = int_value(data.get("end_char"))
    char_count = int_value(data.get("char_count"))
    content = string_value(data.get("content"))
    if index < 1:
        issues.append(
            ValidationIssue(
                "invalid_segment_index",
                "$.index",
                "index must be positive",
            )
        )
    if char_count != len(content) or end - start != len(content):
        issues.append(
            ValidationIssue(
                "segment_char_count_mismatch",
                "$.char_count",
                "segment offsets and char_count must match content length",
            )
        )
    if string_value(data.get("content_hash")) != sha256_text(content):
        issues.append(
            ValidationIssue(
                "segment_hash_mismatch",
                "$.content_hash",
                "content_hash must match content",
            )
        )
    return ValidationReport(tuple(issues), 0, len(content))


def _validate_entry_common(
    data: JsonMap,
    require_hash: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for key in ("entry_id", "source_key", "current_revision_id"):
        if not valid_identifier(string_value(data.get(key))):
            issues.append(
                ValidationIssue(
                    f"invalid_{key}",
                    f"$.{key}",
                    f"{key} must be an identifier",
                )
            )
    if string_value(data.get("content_mode")) not in {"inline", "segmented"}:
        issues.append(
            ValidationIssue(
                "invalid_content_mode",
                "$.content_mode",
                "content_mode must be inline or segmented",
            )
        )
    if int_value(data.get("char_count")) < 0:
        issues.append(
            ValidationIssue(
                "invalid_char_count",
                "$.char_count",
                "char_count must be non-negative",
            )
        )
    content_hash = string_value(data.get("content_hash"))
    if require_hash and not content_hash.startswith("sha256:"):
        issues.append(
            ValidationIssue(
                "invalid_content_hash",
                "$.content_hash",
                "content_hash must start with sha256:",
            )
        )
    return issues


def _validate_segmented_detail(data: JsonMap) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if "content" in data:
        issues.append(
            ValidationIssue(
                "segmented_detail_contains_content",
                "$.content",
                "segmented detail must not include full content",
            )
        )
    segment_count = int_value(data.get("segment_count"))
    segment_size = int_value(data.get("segment_size_hint"))
    char_count = int_value(data.get("char_count"))
    if segment_count < 1:
        issues.append(
            ValidationIssue(
                "invalid_segment_count",
                "$.segment_count",
                "segment_count must be positive",
            )
        )
    if segment_size < 1:
        issues.append(
            ValidationIssue(
                "invalid_segment_size_hint",
                "$.segment_size_hint",
                "segment_size_hint must be positive",
            )
        )
    expected_segments = (
        (char_count + segment_size - 1) // segment_size
        if char_count >= 0 and segment_size > 0
        else -1
    )
    if expected_segments >= 0 and segment_count != expected_segments:
        issues.append(
            ValidationIssue(
                "segment_count_mismatch",
                "$.segment_count",
                "segment_count must match char_count",
            )
        )
    return issues
