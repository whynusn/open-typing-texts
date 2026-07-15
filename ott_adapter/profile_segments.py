from __future__ import annotations

from pathlib import Path

from .ott_core import sha256_text, valid_identifier
from .validation_helpers import int_value, string_value
from .validation_types import JsonMap, ValidationIssue


def validate_static_segments(
    data_dir: Path,
    detail: JsonMap,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    revision_id = string_value(detail.get("current_revision_id"))
    segment_count = int_value(detail.get("segment_count"))
    segment_size = int_value(detail.get("segment_size_hint"))
    expected_char_count = int_value(detail.get("char_count"))
    if not valid_identifier(revision_id):
        return issues
    segment_dir = contained_path(data_dir / "segments", revision_id)
    if segment_dir is None:
        issues.append(
            ValidationIssue(
                "unsafe_segment_path",
                "$.current_revision_id",
                "segment path must stay under segments/",
            )
        )
        return issues
    if segment_count < 1 or segment_size < 1 or expected_char_count < 0:
        return issues

    chunks: list[str] = []
    for index in range(1, segment_count + 1):
        segment_path = segment_dir / f"{index}.txt"
        if not segment_path.exists():
            issues.append(
                ValidationIssue(
                    "missing_segment_file",
                    str(segment_path),
                    "segment file is missing",
                )
            )
            continue
        try:
            content = segment_path.read_text(encoding="utf-8")
        except OSError as error:
            issues.append(ValidationIssue("read_error", str(segment_path), str(error)))
            continue
        expected_start = (index - 1) * segment_size
        expected_len = max(0, min(segment_size, expected_char_count - expected_start))
        if len(content) != expected_len:
            issues.append(
                ValidationIssue(
                    "static_segment_char_count_mismatch",
                    str(segment_path),
                    "segment length must match detail char_count and segment_size_hint",
                )
            )
        chunks.append(content)

    issues.extend(_unexpected_segment_issues(segment_dir, segment_count))
    content = "".join(chunks)
    if len(content) != expected_char_count:
        issues.append(
            ValidationIssue(
                "static_segment_total_char_count_mismatch",
                str(segment_dir),
                "combined segment length must match detail char_count",
            )
        )
    if string_value(detail.get("content_hash")) != sha256_text(content):
        issues.append(
            ValidationIssue(
                "static_segment_hash_mismatch",
                str(segment_dir),
                "combined segment content_hash must match detail content_hash",
            )
        )
    return issues


def contained_path(root: Path, *parts: str) -> Path | None:
    try:
        resolved_root = root.resolve()
        candidate = resolved_root.joinpath(*parts).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return candidate


def _unexpected_segment_issues(
    segment_dir: Path,
    segment_count: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not segment_dir.exists():
        return issues
    for segment_path in sorted(segment_dir.glob("*.txt")):
        if not _segment_file_in_declared_range(segment_path, segment_count):
            issues.append(
                ValidationIssue(
                    "unexpected_segment_file",
                    str(segment_path),
                    "segment file index exceeds declared segment_count",
                )
            )
    return issues


def _segment_file_in_declared_range(path: Path, segment_count: int) -> bool:
    try:
        index = int(path.stem)
    except ValueError:
        return False
    return 1 <= index <= segment_count
