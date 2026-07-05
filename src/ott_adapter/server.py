"""OTT 适配器 HTTP 服务。

提供两个端点：
- GET /registry_index.json  → 返回文本来源目录
- GET /content/{key}.json  → 返回单篇文本正文
"""

import json
import re
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote


# source_key 安全校验（与 typetype 客户端 RegistryTextProvider._validate_source_key 一致）
_SOURCE_KEY_RE = re.compile(r"^[^\\\./]+$")


class OttHandler(BaseHTTPRequestHandler):
    """OTT 适配器请求处理器。"""

    data_dir: Path = Path(".")

    def log_message(self, format, *args):
        """静默日志（减少终端噪音）。"""
        pass

    def do_GET(self):
        path = unquote(self.path)

        if path == "/registry_index.json":
            self._serve_file(self.data_dir / "registry_index.json")
        elif path.startswith("/content/") and path.endswith(".json"):
            source_key = path[len("/content/") : -len(".json")]
            if not _SOURCE_KEY_RE.match(source_key):
                self.send_error(400, f"Invalid source_key: {source_key}")
                return
            self._serve_file(self.data_dir / "content" / f"{source_key}.json")
        else:
            self.send_error(404, "Not Found")

    def _serve_file(self, path: Path):
        if not path.exists():
            self.send_error(404, f"File not found: {path.name}")
            return
        try:
            body = path.read_bytes()
        except OSError as e:
            self.send_error(500, str(e))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def start_server(port: int, data_dir: Path):
    """启动 HTTP 服务。"""
    OttHandler.data_dir = Path(data_dir)
    server = HTTPServer(("127.0.0.1", port), OttHandler)
    print(f"OTT adapter listening on http://127.0.0.1:{port}")
    print(f"Data directory: {data_dir}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
