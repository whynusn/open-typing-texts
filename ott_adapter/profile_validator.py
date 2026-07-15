from __future__ import annotations

from pathlib import Path

from .content_validator import validate_content_data
from .core_validator import (
    validate_entry_detail,
    validate_entry_summary,
    validate_source,
)
from .ott_core import entries_from_content_file, entry_detail, valid_identifier
from .profile_segments import contained_path, validate_static_segments
from .validation_helpers import (
    prefix_issues,
    read_json_map,
    string_value,
)
from .validation_types import ValidationIssue, ValidationReport


def validate_content_file(path: Path) -> ValidationReport:
    data, issues = read_json_map(path)
    if data is None:
        return ValidationReport(tuple(issues))
    expected_key = path.stem if path.parent.name == "content" else ""
    raw_report = validate_content_data(data, expected_source_key=expected_key)
    if not raw_report.valid:
        return raw_report

    entries = entries_from_content_file(path, include_content=True)
    issues = []
    char_count = 0
    for index, entry in enumerate(entries):
        detail_report = validate_entry_detail(entry_detail(entry))
        issues.extend(prefix_issues(detail_report.issues, f"entries[{index}]"))
        char_count += int(entry.get("char_count", 0) or 0)
    if not entries:
        issues.append(
            ValidationIssue(
                "no_normalized_entries",
                "$",
                "content file cannot be normalized into any OTT entry",
            )
        )
    return ValidationReport(tuple(issues), len(entries), char_count)


def validate_static_profile(data_dir: Path) -> ValidationReport:
    issues: list[ValidationIssue] = []
    manifest, manifest_issues = read_json_map(data_dir / "ott.json")
    issues.extend(manifest_issues)
    if manifest is not None:
        if manifest.get("protocol") != "ott":
            issues.append(
                ValidationIssue(
                    "invalid_manifest_protocol",
                    "$.protocol",
                    "protocol must be ott",
                )
            )
        if manifest.get("version") != "1.0":
            issues.append(
                ValidationIssue(
                    "invalid_manifest_version",
                    "$.version",
                    "version must be 1.0",
                )
            )
        profiles = manifest.get("profiles")
        if not isinstance(profiles, list) or "static" not in profiles:
            issues.append(
                ValidationIssue(
                    "missing_static_profile",
                    "$.profiles",
                    "profiles must include static",
                )
            )

    sources_data, sources_issues = read_json_map(data_dir / "sources.json")
    issues.extend(sources_issues)
    sources = sources_data.get("sources") if sources_data is not None else None
    if not isinstance(sources, list):
        issues.append(
            ValidationIssue(
                "invalid_sources_manifest",
                "$.sources",
                "sources must be a list",
            )
        )
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                issues.append(
                    ValidationIssue(
                        "invalid_source",
                        f"$.sources[{index}]",
                        "source must be an object",
                    )
                )
                continue
            source_report = validate_source(source)
            issues.extend(prefix_issues(source_report.issues, f"sources[{index}]"))

    entries_data, entries_issues = read_json_map(data_dir / "entries.json")
    issues.extend(entries_issues)
    entries = entries_data.get("entries") if entries_data is not None else None
    normalized_entries = 0
    if not isinstance(entries, list):
        issues.append(
            ValidationIssue(
                "invalid_entries_manifest",
                "$.entries",
                "entries must be a list",
            )
        )
        entries = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(
                ValidationIssue(
                    "invalid_entry_summary",
                    f"$.entries[{index}]",
                    "summary must be an object",
                )
            )
            continue
        summary_report = validate_entry_summary(entry)
        issues.extend(prefix_issues(summary_report.issues, f"entries[{index}]"))
        entry_id = string_value(entry.get("entry_id"))
        if not valid_identifier(entry_id):
            continue
        detail_path = contained_path(data_dir / "entries", f"{entry_id}.json")
        if detail_path is None:
            issues.append(
                ValidationIssue(
                    "unsafe_entry_detail_path",
                    f"entries[{index}].entry_id",
                    "entry detail path must stay under entries/",
                )
            )
            continue
        detail, detail_issues = read_json_map(detail_path)
        issues.extend(detail_issues)
        if detail is None:
            continue
        if string_value(detail.get("entry_id")) != entry_id:
            issues.append(
                ValidationIssue(
                    "entry_detail_identity_mismatch",
                    f"entries/{entry_id}.json:$.entry_id",
                    "detail entry_id must match summary entry_id",
                )
            )
        detail_report = validate_entry_detail(detail)
        issues.extend(prefix_issues(detail_report.issues, f"entries/{entry_id}.json"))
        normalized_entries += 1
        if string_value(detail.get("content_mode")) == "segmented":
            issues.extend(validate_static_segments(data_dir, detail))
    return ValidationReport(tuple(issues), normalized_entries)


def validate_data_dir(data_dir: Path) -> ValidationReport:
    issues: list[ValidationIssue] = []
    normalized_entries = 0
    char_count = 0
    for path in sorted((data_dir / "content").glob("*.json")):
        report = validate_content_file(path)
        issues.extend(prefix_issues(report.issues, str(path.relative_to(data_dir))))
        normalized_entries += report.normalized_entries
        char_count += report.char_count
    if (data_dir / "ott.json").exists() or (data_dir / "entries.json").exists():
        static_report = validate_static_profile(data_dir)
        issues.extend(prefix_issues(static_report.issues, "static"))
    return ValidationReport(tuple(issues), normalized_entries, char_count)
