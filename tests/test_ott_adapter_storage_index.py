import json
import threading
import unittest
from unittest.mock import patch

from .ott_adapter_test_helpers import OttAdapterTest


class T9CompactJsonTest(OttAdapterTest):
    def test_content_file_is_compact(self):
        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        raw = (self.data_dir / "content" / "test1.json").read_text(encoding="utf-8")
        self.assertNotIn("\n", raw.strip())
        self.assertIn('"content":"hello"', raw)

    def test_index_file_is_compact(self):
        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        self._rebuild_index()
        raw = (self.data_dir / "registry_index.json").read_text(encoding="utf-8")
        self.assertNotIn("\n", raw.strip())

    def test_schedules_file_is_compact(self):
        from ott_adapter.server import _save_schedules

        _save_schedules(self.data_dir, {"schedules": {"test": {"interval": "hourly"}}})
        raw = (self.data_dir / "schedules.json").read_text(encoding="utf-8")
        self.assertNotIn("\n", raw.strip())


class T1RebuildIndexReentryTest(OttAdapterTest):
    def test_reentry_returns_none(self):
        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        import ott_adapter.scheduler as scheduler

        result = []
        entered = threading.Event()
        release = threading.Event()
        original_build_index = scheduler.build_index

        def slow_build_index(data_dir):
            entered.set()
            self.assertTrue(release.wait(5))
            return original_build_index(data_dir)

        def call():
            result.append(scheduler.rebuild_index(self.data_dir))

        with patch.object(scheduler, "build_index", side_effect=slow_build_index):
            thread = threading.Thread(target=call)
            thread.start()
            self.assertTrue(entered.wait(2))
            self.assertIsNone(scheduler.rebuild_index(self.data_dir))
            release.set()
            thread.join(2)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(result), 1)
        self.assertIsNotNone(result[0])

    def test_rebuild_still_works_sequentially(self):
        from ott_adapter.scheduler import rebuild_index

        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        idx = rebuild_index(self.data_dir)

        self.assertIsNotNone(idx)
        if idx is None:
            self.fail("rebuild_index returned None")
        self.assertEqual(len(idx["sources"]), 1)


class T8TTLCacheTest(OttAdapterTest):
    def test_get_schedules_cached(self):
        from ott_adapter.server import (
            _cache_invalidate,
            _get_schedules,
            _save_schedules,
        )

        _save_schedules(self.data_dir, {"schedules": {"test": {"interval": "hourly"}}})
        schedules = _get_schedules(self.data_dir)
        self.assertIn("test", schedules.get("schedules", {}))
        path = self.data_dir / "schedules.json"
        path.write_text(
            json.dumps(
                {"schedules": {"other": {"interval": "daily"}}}, separators=(",", ":")
            ),
            encoding="utf-8",
        )

        cached = _get_schedules(self.data_dir)
        _cache_invalidate(str(path))
        fresh = _get_schedules(self.data_dir)

        self.assertIn("test", cached.get("schedules", {}))
        self.assertIn("other", fresh.get("schedules", {}))

    def test_read_index_cached(self):
        from ott_adapter.server import _read_index, _rebuild_and_invalidate

        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        _rebuild_and_invalidate(self.data_dir)
        first = _read_index(self.data_dir)
        self._write_content(
            "test2",
            [
                {
                    "title": "b",
                    "content": "world",
                    "fetched_at": "2024-01-02T00:00:00+08:00",
                }
            ],
        )
        _rebuild_and_invalidate(self.data_dir)
        second = _read_index(self.data_dir)

        self.assertEqual(len(first["sources"]), 1)
        self.assertEqual(len(second["sources"]), 2)


class T2FileWriteLockTest(OttAdapterTest):
    def test_get_write_lock_same_key(self):
        from ott_adapter.server import _get_write_lock

        lock_a = _get_write_lock("test1")
        lock_b = _get_write_lock("test1")
        lock_c = _get_write_lock("test2")

        self.assertIs(lock_a, lock_b)
        self.assertIsNot(lock_a, lock_c)

    def test_schedule_lock_exists(self):
        from ott_adapter.server import _schedule_lock

        self.assertTrue(_schedule_lock.acquire(blocking=False))
        _schedule_lock.release()


class T34EnrichedIndexTest(OttAdapterTest):
    def test_index_has_preview_fields(self):
        from ott_adapter.scheduler import build_index

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
        source = build_index(self.data_dir)["sources"][0]

        self.assertIn("title_preview", source)
        self.assertIn("entry_preview", source)
        self.assertIn("recent_entries", source)
        self.assertEqual(source["title_preview"], "test1")
        self.assertIn("hello world", source["entry_preview"])

    def test_recent_entries_in_index(self):
        from ott_adapter.scheduler import build_index

        entries = [
            {
                "title": "e1",
                "content": "one",
                "fetched_at": "2024-01-01T00:00:00+08:00",
            },
            {
                "title": "e2",
                "content": "two",
                "fetched_at": "2024-01-02T00:00:00+08:00",
            },
            {
                "title": "e3",
                "content": "three",
                "fetched_at": "2024-01-03T00:00:00+08:00",
            },
        ]
        self._write_content("test1", entries)
        recent = build_index(self.data_dir)["sources"][0]["recent_entries"]

        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[-1]["title"], "e3")

    def test_api_list_sources_no_file_read(self):
        from ott_adapter.server import _read_index, _rebuild_and_invalidate

        self._write_content(
            "test1",
            [
                {
                    "title": "a",
                    "content": "hello",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                }
            ],
        )
        _rebuild_and_invalidate(self.data_dir)
        sources = _read_index(self.data_dir).get("sources", [])

        self.assertEqual(len(sources), 1)
        self.assertIn("title_preview", sources[0])
        self.assertIn("entry_preview", sources[0])

    def test_api_entries_recent_from_index(self):
        from ott_adapter.server import _read_index, _rebuild_and_invalidate

        self._write_content(
            "src1",
            [
                {
                    "title": "e1",
                    "content": "one",
                    "fetched_at": "2024-01-01T00:00:00+08:00",
                },
                {
                    "title": "e2",
                    "content": "two",
                    "fetched_at": "2024-01-02T00:00:00+08:00",
                },
            ],
        )
        self._write_content(
            "src2",
            [
                {
                    "title": "f1",
                    "content": "three",
                    "fetched_at": "2024-01-03T00:00:00+08:00",
                }
            ],
        )
        _rebuild_and_invalidate(self.data_dir)
        recent = (
            _read_index(self.data_dir).get("sources", [])[0].get("recent_entries", [])
        )

        self.assertTrue(len(recent) >= 1)


if __name__ == "__main__":
    unittest.main()
