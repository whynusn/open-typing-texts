from importlib import resources

from .server_http import err as _err


def _frontend_html() -> str:
    return (
        resources.files("ott_adapter")
        .joinpath("frontend.html")
        .read_text(encoding="utf-8")
    )


class StaticFileRoutes:
    def _serve_file(self, path):
        if not path.exists():
            return _err(self, f"Not found: {path.name}", 404)
        body = path.read_bytes()
        self.send_response(200)
        self._cors_headers()
        if path.suffix == ".json":
            ctype = "application/json; charset=utf-8"
        elif path.suffix == ".txt":
            ctype = "text/plain; charset=utf-8"
        else:
            ctype = "application/octet-stream"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError):
            pass  # 客户端提前断开，无需处理

    # ── OTT Core v1: read-only distribution ─────────────────

    def _serve_frontend(self):
        body = _frontend_html().encode("utf-8")
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError):
            pass  # 客户端提前断开，无需处理
