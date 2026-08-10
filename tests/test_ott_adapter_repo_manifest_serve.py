"""OTT Repo v1 control-plane serve tests.

The adapter must serve a self-describing ``/ott-repo.json`` manifest that
satisfies both the official schema field rules and the typetype client-side
validator, so a client can subscribe to a local adapter end to end.
"""

import unittest

from .ott_adapter_test_helpers import OttAdapterTest

REQUIRED_FIELDS = ("protocol", "version", "type", "repo_id", "name")


class RepoManifestServeTest(OttAdapterTest):
    def _fetch_manifest(self, port: int) -> dict:
        return self._get_json(port, "/ott-repo.json")

    def test_manifest_is_served_with_required_fields(self) -> None:
        manifest = self._fetch_manifest(self._start_server())
        for field in REQUIRED_FIELDS:
            self.assertIn(field, manifest)
            self.assertTrue(
                isinstance(manifest[field], str) and manifest[field].strip()
            )
        self.assertEqual(manifest["protocol"], "ott-repo")
        self.assertIn(manifest["type"], ("repository", "directory"))

    def test_manifest_self_describing(self) -> None:
        manifest = self._fetch_manifest(self._start_server())
        self.assertEqual(manifest["protocol"], "ott-repo")
        self.assertEqual(manifest["type"], "repository")
        self.assertEqual(manifest["repo_id"], "local")
        self.assertIn("name", manifest)
        self.assertTrue(manifest["mirrors"])
        self.assertTrue(manifest["mirrors"][0]["url"].endswith("/ott-repo.json"))
        self.assertEqual(len(manifest["sources"]), 1)
        src = manifest["sources"][0]
        self.assertEqual(src["type"], "ott-instance")
        self.assertEqual(src["authority"], "local")
        self.assertTrue(src["endpoints"])
        profiles = {ep["profile"] for ep in src["endpoints"]}
        self.assertIn("service", profiles)
        self.assertIn("static", profiles)

    def test_manifest_reflects_content_count(self) -> None:
        self._write_content(
            "s1", [{"title": "a", "content": "hello", "fetched_at": "2024-01-01"}]
        )
        self._write_content(
            "s2", [{"title": "b", "content": "world", "fetched_at": "2024-01-01"}]
        )
        self._rebuild_index()
        manifest = self._fetch_manifest(self._start_server())
        self.assertIn("2", manifest["description"])

    def test_manifest_source_matches_client_semantics(self) -> None:
        """typetype validate_repo_manifest 的 source 归一化要求。"""
        manifest = self._fetch_manifest(self._start_server())
        src = manifest["sources"][0]
        self.assertIn(src["type"], ("ott-instance", "ott-rule", "ott-bridge"))
        self.assertTrue(src.get("authority"))
        for ep in src.get("endpoints", []):
            self.assertTrue(ep.get("url"))
            self.assertIn(ep.get("profile"), ("static", "service"))
            self.assertGreaterEqual(int(ep.get("priority", 1)), 1)


if __name__ == "__main__":
    unittest.main()

