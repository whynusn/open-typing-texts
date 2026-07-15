from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ott"


class CompatibilityPackTest(unittest.TestCase):
    def test_expected_normalized_entries_match_core_output(self) -> None:
        from ott_adapter.ott_core import (
            entries_from_content_file,
            entry_detail,
            entry_summary,
        )

        expected = json.loads(
            (FIXTURES / "expected-normalized-entries.json").read_text(encoding="utf-8")
        )

        entries = entries_from_content_file(
            FIXTURES / expected["source_fixture"],
            include_content=True,
        )

        self.assertEqual(
            [entry_summary(entry) for entry in entries], expected["summaries"]
        )
        self.assertEqual(
            [entry_detail(entry) for entry in entries], expected["details"]
        )

    def test_expected_segmented_entry_matches_core_output(self) -> None:
        from ott_adapter.ott_core import (
            entries_from_content_file,
            entry_detail,
            entry_summary,
            sha256_text,
        )

        expected = json.loads(
            (FIXTURES / "expected-segmented-entry.json").read_text(encoding="utf-8")
        )
        source = expected["source"]
        content = source["content_char"] * source["content_repeat"]
        with tempfile.TemporaryDirectory(prefix="ott_compat_") as raw_dir:
            path = Path(raw_dir) / "long_fixture.json"
            path.write_text(
                json.dumps(
                    {
                        "source_key": source["source_key"],
                        "entries": [
                            {
                                "entry_id": source["entry_id"],
                                "revision_id": source["revision_id"],
                                "title": source["title"],
                                "content": content,
                                "fetched_at": source["fetched_at"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            entry = entries_from_content_file(path, include_content=True)[0]

        summary = entry_summary(entry)
        detail = entry_detail(entry)
        for key, value in expected["summary"].items():
            self.assertEqual(summary[key], value)
        self.assertNotIn("content", detail)
        segment = expected["segment"]
        segment_content = content[segment["start_char"] : segment["end_char"]]
        self.assertEqual(len(segment_content), segment["char_count"])
        self.assertEqual(sha256_text(segment_content), segment["content_hash"])

    def test_duplicate_titles_with_different_content_have_distinct_identity(
        self,
    ) -> None:
        from ott_adapter.ott_core import entries_from_content_file

        entries = entries_from_content_file(
            FIXTURES / "valid-duplicate-title-content.json",
            include_content=True,
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual({entry["title"] for entry in entries}, {"Same Title"})
        self.assertEqual(len({entry["entry_id"] for entry in entries}), 2)
        self.assertEqual(len({entry["current_revision_id"] for entry in entries}), 2)


if __name__ == "__main__":
    unittest.main()
