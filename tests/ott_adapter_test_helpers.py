import json
import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class OttAdapterTest(unittest.TestCase):
    data_dir: Path

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="ott_test_")
        self.data_dir = Path(self._tmp)
        (self.data_dir / "content").mkdir()
        (self.data_dir / "scripts").mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_content(self, source_key: str, entries: list[dict], title: str = ""):
        data = {
            "source_key": source_key,
            "title": title or source_key,
            "content": entries[-1]["content"] if entries else "",
            "entries": entries,
        }
        path = self.data_dir / "content" / f"{source_key}.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return path

    def _read_content(self, source_key: str) -> dict:
        return json.loads(
            (self.data_dir / "content" / f"{source_key}.json").read_text(
                encoding="utf-8"
            )
        )

    def _make_registry_index(self):
        from ott_adapter.scheduler import build_index

        return build_index(self.data_dir)

    def _rebuild_index(self):
        from ott_adapter.scheduler import rebuild_index

        return rebuild_index(self.data_dir)

    def _start_server(self) -> int:
        from ott_adapter.server import start_server

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        thread = threading.Thread(
            target=start_server, args=(port, str(self.data_dir)), daemon=True
        )
        thread.start()
        time.sleep(0.5)
        return port

    def _get_json(self, port: int, path: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
            self.assertEqual(r.status, 200)
            return json.loads(r.read())

    def _request_json(self, port: int, path: str) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{path}", timeout=5
            ) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _post_json(self, port: int, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(body or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read())
