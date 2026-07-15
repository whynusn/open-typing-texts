import json
import unittest
import urllib.request

from .ott_adapter_test_helpers import OttAdapterTest


class OttCompatAndStaticProfileTest(OttAdapterTest):
    def test_legacy_routes_remain_compatible(self):
        self._write_content(
            "legacy",
            [
                {
                    "title": "old",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        port = self._start_server()

        index = self._get_json(port, "/registry_index.json")
        content = self._get_json(port, "/content/legacy.json")
        api_entries = self._get_json(port, "/api/entries?limit=10")

        self.assertIn("sources", index)
        self.assertEqual(content["source_key"], "legacy")
        self.assertEqual(api_entries["total"], 1)
        self.assertEqual(api_entries["entries"][0]["content"], "hello")

    def test_admin_profile_routes_share_the_legacy_implementation(self):
        self._write_content(
            "admin",
            [
                {
                    "title": "managed",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        port = self._start_server()

        status = self._get_json(port, "/ott-admin/v1/status")
        legacy_status = self._get_json(port, "/api/status")
        sources = self._get_json(port, "/ott-admin/v1/sources")
        entries = self._get_json(port, "/ott-admin/v1/entries?limit=10")
        refreshed = self._post_json(port, "/ott-admin/v1/refresh")

        self.assertEqual(status["admin_api_version"], "1.0")
        self.assertEqual(status["adapter_version"], legacy_status["adapter_version"])
        self.assertEqual(sources["sources"][0]["source_key"], "admin")
        self.assertEqual(entries["entries"][0]["content"], "hello")
        self.assertTrue(refreshed["ok"])

    def test_static_profile_files_are_generated_and_served(self):
        content = "甲" * 2500
        self._write_content(
            "static",
            [
                {
                    "title": "long",
                    "content": content,
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        entries = json.loads(
            (self.data_dir / "entries.json").read_text(encoding="utf-8")
        )["entries"]
        entry = entries[0]
        port = self._start_server()
        manifest = self._get_json(port, "/ott.json")
        served_entries = self._get_json(port, "/entries.json")
        served_detail = self._get_json(port, f"/entries/{entry['entry_id']}.json")

        self.assertTrue((self.data_dir / "ott.json").exists())
        self.assertTrue((self.data_dir / "sources.json").exists())
        self.assertEqual(entry["content_mode"], "inline")
        self.assertEqual(manifest["protocol"], "ott")
        self.assertEqual(served_entries["total"], 1)
        self.assertEqual(served_detail["content"], content)

    def test_static_profile_generates_segment_files_for_long_text(self):
        content = "乙" * 4500
        self._write_content(
            "static_long",
            [
                {
                    "title": "long",
                    "content": content,
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        entry = json.loads(
            (self.data_dir / "entries.json").read_text(encoding="utf-8")
        )["entries"][0]
        detail = json.loads(
            (self.data_dir / "entries" / f"{entry['entry_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        segment_path = (
            self.data_dir / "segments" / entry["current_revision_id"] / "2.txt"
        )

        self.assertEqual(entry["content_mode"], "segmented")
        self.assertNotIn("content", detail)
        self.assertEqual(segment_path.read_text(encoding="utf-8"), "乙" * 1000)

        port = self._start_server()
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/segments/{entry['current_revision_id']}/2.txt",
            timeout=5,
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read().decode("utf-8"), "乙" * 1000)


if __name__ == "__main__":
    unittest.main()
