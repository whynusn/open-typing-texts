"""OTT Adapter 架构优化测试 — stdlib unittest。"""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path


class OttAdapterTest(unittest.TestCase):
    """测试基类：自动管理临时数据目录。"""

    sources: list[dict]
    data_dir: Path

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="ott_test_")
        self.data_dir = Path(self._tmp)
        (self.data_dir / "content").mkdir()
        (self.data_dir / "scripts").mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_content(self, source_key: str, entries: list[dict], title: str = ""):
        """写入一个 content/{source_key}.json 文件。"""
        d = {
            "source_key": source_key,
            "title": title or source_key,
            "content": entries[-1]["content"] if entries else "",
            "entries": entries,
        }
        p = self.data_dir / "content" / f"{source_key}.json"
        p.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return p

    def _read_content(self, source_key: str) -> dict:
        return json.loads((self.data_dir / "content" / f"{source_key}.json").read_text(encoding="utf-8"))

    def _make_registry_index(self):
        from ott_adapter.scheduler import build_index
        return build_index(self.data_dir)

    def _rebuild_index(self):
        from ott_adapter.scheduler import rebuild_index
        return rebuild_index(self.data_dir)


# ── T9: Compact JSON ──────────────────────────────────────

class T9CompactJsonTest(OttAdapterTest):
    def test_content_file_is_compact(self):
        self._write_content("test1", [{"title": "a", "content": "hello", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        raw = (self.data_dir / "content" / "test1.json").read_text(encoding="utf-8")
        # No newlines inside the JSON object (compact = single line)
        self.assertNotIn('\n', raw.strip())
        self.assertIn('"content":"hello"', raw)  # compact: no space after colon

    def test_index_file_is_compact(self):
        self._write_content("test1", [{"title": "a", "content": "hello", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        self._rebuild_index()
        raw = (self.data_dir / "registry_index.json").read_text(encoding="utf-8")
        self.assertNotIn('\n', raw.strip())

    def test_schedules_file_is_compact(self):
        from ott_adapter.server import _save_schedules
        _save_schedules(self.data_dir, {"schedules": {"test": {"interval": "hourly"}}})
        raw = (self.data_dir / "schedules.json").read_text(encoding="utf-8")
        self.assertNotIn('\n', raw.strip())


# ── T1: rebuild_index re-entry guard ─────────────────────────

class T1RebuildIndexReentryTest(OttAdapterTest):
    def test_reentry_returns_none(self):
        self._write_content("test1", [{"title": "a", "content": "hello", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        from ott_adapter.scheduler import rebuild_index

        results = []
        barrier = threading.Barrier(10)

        def call():
            barrier.wait()  # all threads start at the same time
            results.append(rebuild_index(self.data_dir))

        threads = [threading.Thread(target=call) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        non_none = [r for r in results if r is not None]
        none_count = sum(1 for r in results if r is None)
        self.assertEqual(len(non_none), 1, f"expected 1 non-None, got {len(non_none)}")
        self.assertEqual(none_count, 9, f"expected 9 None, got {none_count}")

    def test_rebuild_still_works_sequentially(self):
        self._write_content("test1", [{"title": "a", "content": "hello", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        from ott_adapter.scheduler import rebuild_index
        idx = rebuild_index(self.data_dir)
        self.assertIsNotNone(idx)
        self.assertEqual(len(idx["sources"]), 1)


# ── T7: ThreadPoolExecutor ────────────────────────────────

class T7ThreadPoolTest(OttAdapterTest):
    def test_server_class_has_pool(self):
        from ott_adapter.server import ThreadLimitedServer
        self.assertTrue(hasattr(ThreadLimitedServer, '_pool'))
        self.assertEqual(ThreadLimitedServer._pool._max_workers, 8)

    def test_server_starts_and_serves(self):
        from ott_adapter.server import start_server, ThreadLimitedServer
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        t = threading.Thread(target=start_server, args=(port, str(self.data_dir)), daemon=True)
        t.start()
        time.sleep(1)

        import urllib.request
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5)
        self.assertEqual(r.status, 200)
        data = json.loads(r.read())
        self.assertIn("version", data)


# ── T8: TTL cache ─────────────────────────────────────────

class T8TTLCacheTest(OttAdapterTest):
    def test_get_schedules_cached(self):
        from ott_adapter.server import _get_schedules, _cache_invalidate, _save_schedules
        _save_schedules(self.data_dir, {"schedules": {"test": {"interval": "hourly"}}})
        # First call reads from file
        s1 = _get_schedules(self.data_dir)
        self.assertIn("test", s1.get("schedules", {}))
        # Modify file directly (bypass cache)
        p = self.data_dir / "schedules.json"
        import json as j
        p.write_text(j.dumps({"schedules": {"other": {"interval": "daily"}}}, separators=(",", ":")), encoding="utf-8")
        # Second call should still return cached (old) data
        s2 = _get_schedules(self.data_dir)
        self.assertIn("test", s2.get("schedules", {}))
        # After invalidation, returns fresh data
        _cache_invalidate(str(p))
        s3 = _get_schedules(self.data_dir)
        self.assertIn("other", s3.get("schedules", {}))

    def test_read_index_cached(self):
        from ott_adapter.server import _read_index, _cache_invalidate, _rebuild_and_invalidate
        self._write_content("test1", [{"title": "a", "content": "hello", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        _rebuild_and_invalidate(self.data_dir)
        i1 = _read_index(self.data_dir)
        self.assertEqual(len(i1["sources"]), 1)
        # Add another source directly
        self._write_content("test2", [{"title": "b", "content": "world", "fetched_at": "2024-01-02T00:00:00+08:00"}])
        _rebuild_and_invalidate(self.data_dir)
        # Cache should be invalidated by rebuild
        i2 = _read_index(self.data_dir)
        self.assertEqual(len(i2["sources"]), 2)


# ── T2: File write locks ──────────────────────────────────

class T2FileWriteLockTest(OttAdapterTest):
    def test_get_write_lock_same_key(self):
        from ott_adapter.server import _get_write_lock

        lock_a = _get_write_lock("test1")
        lock_b = _get_write_lock("test1")
        self.assertIs(lock_a, lock_b)

        lock_c = _get_write_lock("test2")
        self.assertIsNot(lock_a, lock_c)

    def test_schedule_lock_exists(self):
        from ott_adapter.server import _schedule_lock
        self.assertTrue(_schedule_lock.acquire(blocking=False))
        _schedule_lock.release()


# ── T3+4: Enriched index ──────────────────────────────────

class T34EnrichedIndexTest(OttAdapterTest):
    def test_index_has_preview_fields(self):
        from ott_adapter.scheduler import build_index
        self._write_content("test1", [{"title": "a", "content": "hello world", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        idx = build_index(self.data_dir)
        src = idx["sources"][0]
        self.assertIn("title_preview", src)
        self.assertIn("entry_preview", src)
        self.assertIn("recent_entries", src)
        self.assertEqual(src["title_preview"], "test1")
        self.assertIn("hello world", src["entry_preview"])

    def test_recent_entries_in_index(self):
        from ott_adapter.scheduler import build_index
        entries = [
            {"title": "e1", "content": "one", "fetched_at": "2024-01-01T00:00:00+08:00"},
            {"title": "e2", "content": "two", "fetched_at": "2024-01-02T00:00:00+08:00"},
            {"title": "e3", "content": "three", "fetched_at": "2024-01-03T00:00:00+08:00"},
        ]
        self._write_content("test1", entries)
        idx = build_index(self.data_dir)
        recent = idx["sources"][0]["recent_entries"]
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[-1]["title"], "e3")  # last entry in list

    def test_api_list_sources_no_file_read(self):
        from ott_adapter.server import _read_index, _rebuild_and_invalidate
        self._write_content("test1", [{"title": "a", "content": "hello", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        _rebuild_and_invalidate(self.data_dir)
        sources = _read_index(self.data_dir).get("sources", [])
        self.assertEqual(len(sources), 1)
        self.assertIn("title_preview", sources[0])
        self.assertIn("entry_preview", sources[0])

    def test_api_entries_recent_from_index(self):
        from ott_adapter.server import _read_index, _rebuild_and_invalidate
        self._write_content("src1", [
            {"title": "e1", "content": "one", "fetched_at": "2024-01-01T00:00:00+08:00"},
            {"title": "e2", "content": "two", "fetched_at": "2024-01-02T00:00:00+08:00"},
        ])
        self._write_content("src2", [
            {"title": "f1", "content": "three", "fetched_at": "2024-01-03T00:00:00+08:00"},
        ])
        _rebuild_and_invalidate(self.data_dir)
        recent = _read_index(self.data_dir).get("sources", [])[0].get("recent_entries", [])
        self.assertTrue(len(recent) >= 1)


# ── T5: openDetail by entry ID ────────────────────────────
# T1: test_rebuild_index_reentry
# T7: test_thread_pool
# T8: test_ttl_cache
# T2: test_file_write_race
# T3+4: test_enriched_index, test_api_list_sources, test_api_entries_recent
# T5: test_open_detail_by_id
    # T6: test_pagination


# ── OTT Core v1 read-only distribution ───────────────────────

class OttCoreV1Test(OttAdapterTest):
    def _start_server(self):
        from ott_adapter.server import start_server
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        t = threading.Thread(target=start_server, args=(port, str(self.data_dir)), daemon=True)
        t.start()
        time.sleep(0.5)
        return port

    def _get_json(self, port: int, path: str) -> dict:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
            self.assertEqual(r.status, 200)
            return json.loads(r.read())

    def _request_json(self, port: int, path: str) -> tuple[int, dict]:
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_capabilities_declares_ott_v1_service(self):
        port = self._start_server()
        data = self._get_json(port, "/ott/v1/capabilities")
        self.assertEqual(data["protocol"], "ott")
        self.assertEqual(data["version"], "1.0")
        self.assertIn("service", data["profiles"])
        self.assertTrue(data["features"]["entry_summary"])

    def test_entries_are_summary_only(self):
        self._write_content("test1", [{"title": "a", "content": "hello world", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        self._rebuild_index()
        port = self._start_server()
        data = self._get_json(port, "/ott/v1/entries?limit=10")
        self.assertEqual(data["total"], 1)
        entry = data["entries"][0]
        self.assertIn("entry_id", entry)
        self.assertIn("current_revision_id", entry)
        self.assertEqual(entry["content_mode"], "inline")
        self.assertNotIn("content", entry)

    def test_entry_detail_returns_inline_content(self):
        self._write_content("test1", [{"title": "a", "content": "hello world", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        self._rebuild_index()
        port = self._start_server()
        entries = self._get_json(port, "/ott/v1/entries?limit=10")["entries"]
        detail = self._get_json(port, f"/ott/v1/entries/{entries[0]['entry_id']}")
        self.assertEqual(detail["content"], "hello world")
        self.assertEqual(detail["content_mode"], "inline")
        self.assertTrue(detail["content_hash"].startswith("sha256:"))

    def test_segmented_entry_returns_segment(self):
        content = "甲" * 4500
        self._write_content("long", [{"title": "long", "content": content, "fetched_at": "2024-01-01T00:00:00+08:00"}])
        self._rebuild_index()
        port = self._start_server()
        entry = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]
        self.assertEqual(entry["content_mode"], "segmented")
        detail = self._get_json(port, f"/ott/v1/entries/{entry['entry_id']}")
        self.assertEqual(detail["segment_count"], 5)
        self.assertNotIn("content", detail)
        segment = self._get_json(
            port,
            f"/ott/v1/entries/{entry['entry_id']}/revisions/{entry['current_revision_id']}/segments/2",
        )
        self.assertEqual(segment["index"], 2)
        self.assertEqual(segment["start_char"], 1000)
        self.assertEqual(segment["end_char"], 2000)
        self.assertEqual(segment["content"], "甲" * 1000)

    def test_entry_id_is_stable_when_fetched_at_changes(self):
        self._write_content("stable", [{"title": "same", "content": "v1", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        self._rebuild_index()
        port = self._start_server()
        first = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]

        self._write_content("stable", [{"title": "same", "content": "v2", "fetched_at": "2024-02-01T00:00:00+08:00"}])
        from ott_adapter.server import _rebuild_and_invalidate
        _rebuild_and_invalidate(self.data_dir)
        second = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]

        self.assertEqual(first["entry_id"], second["entry_id"])
        self.assertNotEqual(first["current_revision_id"], second["current_revision_id"])

    def test_entries_support_pagination_filtering_and_empty_results(self):
        self._write_content("src1", [
            {"title": "alpha", "content": "one", "fetched_at": "2024-01-01T00:00:00+08:00"},
            {"title": "beta", "content": "two", "fetched_at": "2024-01-02T00:00:00+08:00"},
        ])
        self._write_content("src2", [
            {"title": "gamma", "content": "three", "fetched_at": "2024-01-03T00:00:00+08:00"},
        ])
        self._rebuild_index()
        port = self._start_server()

        page = self._get_json(port, "/ott/v1/entries?page=1&limit=2")
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["pages"], 2)
        self.assertEqual(len(page["entries"]), 2)

        filtered = self._get_json(port, "/ott/v1/entries?source_key=src1&limit=10")
        self.assertEqual(filtered["total"], 2)
        self.assertTrue(all(e["source_key"] == "src1" for e in filtered["entries"]))

        searched = self._get_json(port, "/ott/v1/entries?q=gamma&limit=10")
        self.assertEqual(searched["total"], 1)
        self.assertEqual(searched["entries"][0]["title"], "gamma")

        empty = self._get_json(port, "/ott/v1/entries?q=missing&limit=10")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["entries"], [])

    def test_ott_errors_have_stable_envelope(self):
        self._write_content("long", [{"title": "long", "content": "甲" * 4500, "fetched_at": "2024-01-01T00:00:00+08:00"}])
        self._rebuild_index()
        port = self._start_server()
        entry = self._get_json(port, "/ott/v1/entries?limit=10")["entries"][0]

        status, bad_page = self._request_json(port, "/ott/v1/entries?page=bad")
        self.assertEqual(status, 400)
        self.assertEqual(bad_page["error"]["code"], "invalid_page")

        status, missing = self._request_json(port, "/ott/v1/entries/ent_missing")
        self.assertEqual(status, 404)
        self.assertEqual(missing["error"]["code"], "entry_not_found")

        status, missing_segment = self._request_json(
            port,
            f"/ott/v1/entries/{entry['entry_id']}/revisions/{entry['current_revision_id']}/segments/99",
        )
        self.assertEqual(status, 404)
        self.assertEqual(missing_segment["error"]["code"], "segment_out_of_range")

    def test_sources_use_ott_entry_statistics(self):
        self._write_content("src", [
            {"title": "one", "content": "abc", "fetched_at": "2024-01-01T00:00:00+08:00"},
            {"title": "two", "content": "甲乙", "fetched_at": "2024-01-02T00:00:00+08:00"},
        ])
        self._rebuild_index()
        port = self._start_server()
        source = self._get_json(port, "/ott/v1/sources")["sources"][0]
        self.assertEqual(source["entry_count"], 2)
        self.assertEqual(source["char_count"], 5)

    def test_legacy_routes_remain_compatible(self):
        self._write_content("legacy", [{"title": "old", "content": "hello", "fetched_at": "2024-01-01T00:00:00+08:00"}])
        self._rebuild_index()
        port = self._start_server()
        index = self._get_json(port, "/registry_index.json")
        content = self._get_json(port, "/content/legacy.json")
        api_entries = self._get_json(port, "/api/entries?limit=10")
        self.assertIn("sources", index)
        self.assertEqual(content["source_key"], "legacy")
        self.assertEqual(api_entries["total"], 1)
        self.assertEqual(api_entries["entries"][0]["content"], "hello")

if __name__ == "__main__":
    unittest.main()
