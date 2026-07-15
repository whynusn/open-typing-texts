import unittest

from .ott_adapter_test_helpers import OttAdapterTest


class OttCoreV1ServiceTest(OttAdapterTest):
    def test_capabilities_declares_ott_v1_service(self):
        data = self._get_json(self._start_server(), "/ott/v1/capabilities")

        self.assertEqual(data["protocol"], "ott")
        self.assertEqual(data["version"], "1.0")
        self.assertIn("adapter_version", data)
        self.assertIn("service", data["profiles"])
        self.assertTrue(data["features"]["entry_summary"])

    def test_entries_are_summary_only(self):
        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello world",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()

        entry = self._get_json(self._start_server(), "/ott/v1/entries?limit=10")[
            "entries"
        ][0]

        self.assertIn("entry_id", entry)
        self.assertIn("current_revision_id", entry)
        self.assertEqual(entry["content_mode"], "inline")
        self.assertNotIn("content", entry)

    def test_entry_detail_returns_inline_content(self):
        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello world",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        port = self._start_server()
        entry = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]
        detail = self._get_json(port, f"/ott/v1/entries/{entry['entry_id']}")

        self.assertEqual(detail["content"], "hello world")
        self.assertEqual(detail["content_mode"], "inline")
        self.assertTrue(detail["content_hash"].startswith("sha256:"))

    def test_segmented_entry_returns_segment(self):
        content = "甲" * 4500
        self._write_content(
            "long",
            [
                {
                    "title": "long",
                    "content": content,
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        port = self._start_server()
        entry = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]
        detail = self._get_json(port, f"/ott/v1/entries/{entry['entry_id']}")
        segment = self._get_json(
            port,
            f"/ott/v1/entries/{entry['entry_id']}/revisions/{entry['current_revision_id']}/segments/2",
        )

        self.assertEqual(entry["content_mode"], "segmented")
        self.assertEqual(detail["segment_count"], 5)
        self.assertNotIn("content", detail)
        self.assertEqual(segment["index"], 2)
        self.assertEqual(segment["content"], "甲" * 1000)

    def test_entry_id_is_stable_when_fetched_at_changes(self):
        self._write_content(
            "stable",
            [
                {
                    "title": "same",
                    "content": "v1",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        port = self._start_server()
        first = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]
        self._write_content(
            "stable",
            [
                {
                    "title": "same",
                    "content": "v2",
                    "fetched_at": "2024-02-01T00:00:00+08:00",
                }
            ],
        )
        from ott_adapter.server import _rebuild_and_invalidate

        _rebuild_and_invalidate(self.data_dir)
        second = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]

        self.assertEqual(first["entry_id"], second["entry_id"])
        self.assertNotEqual(first["current_revision_id"], second["current_revision_id"])

    def test_entries_support_pagination_filtering_and_empty_results(self):
        self._write_content(
            "src1",
            [
                {
                    "title": "alpha",
                    "content": "one",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                },
                {
                    "title": "beta",
                    "content": "two",
                    "fetched_at": "2024-01-02T00:00:00+08:00",
                },
            ],
        )
        self._write_content(
            "src2",
            [
                {
                    "title": "gamma",
                    "content": "three",
                    "fetched_at": "2024-01-03T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        port = self._start_server()

        page = self._get_json(port, "/ott/v1/entries?page=1&limit=2")
        filtered = self._get_json(port, "/ott/v1/entries?source_key=src1&limit=10")
        searched = self._get_json(port, "/ott/v1/entries?q=gamma&limit=10")
        empty = self._get_json(port, "/ott/v1/entries?q=missing&limit=10")

        self.assertEqual(page["total"], 3)
        self.assertEqual(page["pages"], 2)
        self.assertEqual(len(filtered["entries"]), 2)
        self.assertEqual(searched["entries"][0]["title"], "gamma")
        self.assertEqual(empty["entries"], [])

    def test_ott_errors_have_stable_envelope(self):
        self._write_content(
            "long",
            [
                {
                    "title": "long",
                    "content": "甲" * 4500,
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        port = self._start_server()
        entry = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]

        status, bad_page = self._request_json(port, "/ott/v1/entries?page=bad")
        status_missing, missing = self._request_json(
            port, "/ott/v1/entries/ent_missing"
        )
        status_segment, missing_segment = self._request_json(
            port,
            f"/ott/v1/entries/{entry['entry_id']}/revisions/{entry['current_revision_id']}/segments/99",
        )

        self.assertEqual(status, 400)
        self.assertEqual(bad_page["error"]["code"], "invalid_page")
        self.assertEqual(status_missing, 404)
        self.assertEqual(missing["error"]["code"], "entry_not_found")
        self.assertEqual(status_segment, 404)
        self.assertEqual(missing_segment["error"]["code"], "segment_out_of_range")

    def test_sources_use_ott_entry_statistics(self):
        self._write_content(
            "src",
            [
                {
                    "title": "one",
                    "content": "abc",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                },
                {
                    "title": "two",
                    "content": "甲乙",
                    "fetched_at": "2024-01-02T00:00:00+08:00",
                },
            ],
        )
        self._rebuild_index()

        source = self._get_json(self._start_server(), "/ott/v1/sources")["sources"][0]

        self.assertEqual(source["entry_count"], 2)
        self.assertEqual(source["char_count"], 5)


if __name__ == "__main__":
    unittest.main()
