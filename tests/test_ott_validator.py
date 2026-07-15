from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "ott"


class OttValidatorTest(unittest.TestCase):
    def test_content_file_passes_when_normalizable(self) -> None:
        from ott_adapter.validator import validate_content_file

        report = validate_content_file(FIXTURES / "valid-inline-content.json")

        self.assertTrue(report.valid, report.to_dict())
        self.assertEqual(report.normalized_entries, 1)

    def test_content_file_fails_when_source_key_invalid(self) -> None:
        from ott_adapter.validator import validate_content_file

        report = validate_content_file(FIXTURES / "invalid-source-key-content.json")

        self.assertFalse(report.valid)
        self.assertIn("invalid_source_key", {issue.code for issue in report.issues})

    def test_content_file_fails_when_content_is_empty(self) -> None:
        from ott_adapter.validator import validate_content_file

        report = validate_content_file(FIXTURES / "invalid-empty-content.json")

        self.assertFalse(report.valid)
        self.assertIn("missing_content", {issue.code for issue in report.issues})

    def test_summary_fails_when_it_contains_content(self) -> None:
        from ott_adapter.validator import validate_entry_summary

        data = json.loads(
            (FIXTURES / "invalid-summary-with-content.json").read_text(encoding="utf-8")
        )
        report = validate_entry_summary(data)

        self.assertFalse(report.valid)
        self.assertIn(
            "summary_contains_content", {issue.code for issue in report.issues}
        )

    def test_segmented_detail_fails_when_it_contains_content(self) -> None:
        from ott_adapter.validator import validate_entry_detail

        data = json.loads(
            (FIXTURES / "invalid-segmented-detail-with-content.json").read_text(
                encoding="utf-8"
            )
        )
        report = validate_entry_detail(data)

        self.assertFalse(report.valid)
        self.assertIn(
            "segmented_detail_contains_content",
            {issue.code for issue in report.issues},
        )

    def test_segment_fails_when_offsets_do_not_match_content(self) -> None:
        from ott_adapter.validator import validate_segment

        data = json.loads(
            (FIXTURES / "invalid-segment-bad-count.json").read_text(encoding="utf-8")
        )
        report = validate_segment(data)

        self.assertFalse(report.valid)
        self.assertIn("segment_char_count_mismatch", {i.code for i in report.issues})

    def test_segment_passes_when_hash_and_offsets_match(self) -> None:
        from ott_adapter.validator import validate_segment

        data = json.loads((FIXTURES / "valid-segment.json").read_text(encoding="utf-8"))

        report = validate_segment(data)

        self.assertTrue(report.valid, report.to_dict())

    def test_static_profile_passes_for_generated_profile(self) -> None:
        from ott_adapter.scheduler import rebuild_index
        from ott_adapter.validator import validate_static_profile

        with tempfile.TemporaryDirectory(prefix="ott_validator_") as raw_dir:
            data_dir = Path(raw_dir)
            content_dir = data_dir / "content"
            content_dir.mkdir()
            content = {
                "source_key": "long",
                "title": "Long",
                "content": "甲" * 4500,
            }
            (content_dir / "long.json").write_text(
                json.dumps(content, ensure_ascii=False),
                encoding="utf-8",
            )
            rebuild_index(data_dir)

            report = validate_static_profile(data_dir)

            self.assertTrue(report.valid, report.to_dict())
            self.assertEqual(report.normalized_entries, 1)

    def test_static_profile_fails_when_segment_content_hash_drifts(self) -> None:
        from ott_adapter.scheduler import rebuild_index
        from ott_adapter.validator import validate_static_profile

        with tempfile.TemporaryDirectory(prefix="ott_validator_") as raw_dir:
            data_dir = Path(raw_dir)
            content_dir = data_dir / "content"
            content_dir.mkdir()
            content = {
                "source_key": "long",
                "title": "Long",
                "content": "甲" * 4500,
            }
            (content_dir / "long.json").write_text(
                json.dumps(content, ensure_ascii=False),
                encoding="utf-8",
            )
            rebuild_index(data_dir)
            detail_path = next((data_dir / "entries").glob("*.json"))
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            segment_path = (
                data_dir / "segments" / detail["current_revision_id"] / "1.txt"
            )
            segment_path.write_text("乙" * 1000, encoding="utf-8")

            report = validate_static_profile(data_dir)

        self.assertFalse(report.valid)
        self.assertIn(
            "static_segment_hash_mismatch",
            {issue.code for issue in report.issues},
        )

    def test_static_profile_fails_when_sources_manifest_is_missing(self) -> None:
        from ott_adapter.scheduler import rebuild_index
        from ott_adapter.validator import validate_static_profile

        with tempfile.TemporaryDirectory(prefix="ott_validator_") as raw_dir:
            data_dir = Path(raw_dir)
            content_dir = data_dir / "content"
            content_dir.mkdir()
            (content_dir / "short.json").write_text(
                json.dumps(
                    {
                        "source_key": "short",
                        "title": "Short",
                        "content": "正文",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rebuild_index(data_dir)
            (data_dir / "sources.json").unlink()

            report = validate_static_profile(data_dir)

        self.assertFalse(report.valid)
        self.assertIn("missing_file", {issue.code for issue in report.issues})

    def test_static_profile_does_not_read_traversal_entry_id(self) -> None:
        from ott_adapter.validator import validate_static_profile

        with tempfile.TemporaryDirectory(prefix="ott_validator_") as raw_dir:
            data_dir = Path(raw_dir)
            (data_dir / "entries").mkdir()
            (data_dir / "ott.json").write_text(
                json.dumps(
                    {"protocol": "ott", "version": "1.0", "profiles": ["static"]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (data_dir / "sources.json").write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "source_key": "safe",
                                "label": "safe",
                                "entry_count": 1,
                                "char_count": 1,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (data_dir / "entries.json").write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "entry_id": "../escape",
                                "source_key": "safe",
                                "title": "Escape",
                                "preview": "x",
                                "char_count": 1,
                                "content_mode": "inline",
                                "current_revision_id": "rev_escape",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (data_dir / "escape.json").write_text(
                json.dumps(
                    {
                        "entry_id": "../escape",
                        "source_key": "safe",
                        "title": "Escape",
                        "char_count": 1,
                        "content_mode": "inline",
                        "current_revision_id": "rev_escape",
                        "content_hash": "sha256:bad",
                        "content": "x",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = validate_static_profile(data_dir)

        self.assertFalse(report.valid)
        self.assertEqual(report.normalized_entries, 0)
        self.assertIn("invalid_entry_id", {issue.code for issue in report.issues})

    def test_cli_validate_file_reports_success(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ott_adapter",
                "validate",
                str(FIXTURES / "valid-inline-content.json"),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PASS", result.stdout)

    def test_server_json_validation_uses_core_validator(self) -> None:
        from ott_adapter.server import _validate_ott_json

        valid_data = json.loads(
            (FIXTURES / "valid-entries-content.json").read_text(encoding="utf-8")
        )
        invalid_data = json.loads(
            (FIXTURES / "invalid-source-key-content.json").read_text(encoding="utf-8")
        )

        self.assertTrue(_validate_ott_json(valid_data)["valid"])
        self.assertFalse(_validate_ott_json(invalid_data)["valid"])


if __name__ == "__main__":
    unittest.main()
