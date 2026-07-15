import json
import socket
import threading
import time
import unittest
from urllib import error as url_error
from urllib import request as url_request

from .ott_adapter_test_helpers import OttAdapterTest


class T7ThreadPoolTest(OttAdapterTest):
    def test_server_class_has_pool(self):
        from ott_adapter.server import ThreadLimitedServer

        self.assertTrue(hasattr(ThreadLimitedServer, "_pool"))
        self.assertEqual(ThreadLimitedServer._pool._max_workers, 8)

    def test_server_starts_and_serves(self):
        from ott_adapter.server import start_server

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        thread = threading.Thread(
            target=start_server, args=(port, str(self.data_dir)), daemon=True
        )
        thread.start()
        time.sleep(1)

        response = url_request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5)
        self.assertEqual(response.status, 200)
        self.assertIn("version", json.loads(response.read()))

    def test_admin_api_rejects_cross_origin_requests(self):
        from ott_adapter.server import OttHandler, ThreadLimitedServer

        server = ThreadLimitedServer(("127.0.0.1", 0), OttHandler)
        OttHandler.data_dir = self.data_dir
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = url_request.Request(
            f"http://127.0.0.1:{port}/api/status",
            headers={"Origin": "http://evil.example"},
        )
        try:
            with self.assertRaises(url_error.HTTPError) as raised:
                url_request.urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()

    def test_admin_save_rejects_unsafe_script_source(self):
        from ott_adapter.server import OttHandler, ThreadLimitedServer

        scripts_dir = self.data_dir / "scripts"
        script = scripts_dir / "fetch_bad.py"
        script.write_text("print('safe')\n", encoding="utf-8")
        server = ThreadLimitedServer(("127.0.0.1", 0), OttHandler)
        OttHandler.data_dir = self.data_dir
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = json.dumps(
            {
                "source_code": (
                    "import os\n"
                    "from pathlib import Path\n"
                    "get = getattr\n"
                    "replace_alias = get(os, 'replace')\n"
                    "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
                    "replace_alias('content/tmp.json', 'content/../outside.json')\n"
                )
            }
        ).encode("utf-8")
        request = url_request.Request(
            f"http://127.0.0.1:{port}/api/scripts/bad/save",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.assertRaises(url_error.HTTPError) as raised:
                url_request.urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 400)
            self.assertEqual(script.read_text(encoding="utf-8"), "print('safe')\n")
        finally:
            server.shutdown()
            server.server_close()

    def test_admin_run_rejects_unsafe_existing_script(self):
        from ott_adapter.server import OttHandler, ThreadLimitedServer

        scripts_dir = self.data_dir / "scripts"
        (scripts_dir / "fetch_bad.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            "get = getattr\n"
            "replace_alias = get(os, 'replace')\n"
            "Path('content/tmp.json').write_text('x', encoding='utf-8')\n"
            "replace_alias('content/tmp.json', 'content/../outside.json')\n",
            encoding="utf-8",
        )
        server = ThreadLimitedServer(("127.0.0.1", 0), OttHandler)
        OttHandler.data_dir = self.data_dir
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = url_request.Request(
            f"http://127.0.0.1:{port}/api/scripts/bad/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.assertRaises(url_error.HTTPError) as raised:
                url_request.urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 400)
            self.assertFalse((self.data_dir / "outside.json").exists())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
