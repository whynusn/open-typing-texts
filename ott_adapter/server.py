import re
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__
from . import server_state as _state
from .server_admin_entries import AdminEntryRoutes
from .server_admin_script_mutations import AdminScriptMutationRoutes
from .server_admin_scripts import AdminScriptReadRunRoutes
from .server_admin_sources import AdminSourceRoutes
from .server_http import err as _err
from .server_ott_routes import OttReadOnlyRoutes
from .server_repo_routes import RepoManifestRoutes
from .server_static_routes import StaticFileRoutes

_cache_invalidate = _state.cache_invalidate
_get_schedules = _state.get_schedules
_get_write_lock = _state.get_write_lock
_read_index = _state.read_index
_rebuild_and_invalidate = _state.rebuild_and_invalidate
_save_schedules = _state.save_schedules
_schedule_lock = _state._schedule_lock
_validate_ott_json = _state.validate_ott_json


class OttHandler(
    OttReadOnlyRoutes,
    StaticFileRoutes,
    RepoManifestRoutes,
    AdminSourceRoutes,
    AdminScriptReadRunRoutes,
    AdminScriptMutationRoutes,
    AdminEntryRoutes,
    BaseHTTPRequestHandler,
):
    data_dir = Path(".")
    _start_time = time.time()

    def log_message(self, format, *args):
        pass

    # ── 路由入口 ──────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(unquote(self.path))
        path = parsed.path.rstrip("/") or "/"
        self._route("GET", path, parsed)

    def do_POST(self):
        parsed = urlparse(unquote(self.path))
        path = parsed.path.rstrip("/") or "/"
        self._route("POST", path, parsed)

    def do_DELETE(self):
        parsed = urlparse(unquote(self.path))
        path = parsed.path.rstrip("/") or "/"
        self._route("DELETE", path, parsed)

    def do_OPTIONS(self):
        parsed = urlparse(unquote(self.path))
        path = parsed.path.rstrip("/") or "/"
        if self._is_admin_request_path(path) and not self._admin_origin_allowed():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _route(self, method, path, parsed):
        """路由表：按 specificity 降序匹配。"""
        # ── OTT Core v1 read-only distribution API ───────────
        if method == "GET" and path == "/ott/v1/capabilities":
            return self._ott_capabilities()

        if method == "GET" and path == "/ott/v1/sources":
            return self._ott_sources()

        if method == "GET" and path == "/ott/v1/entries":
            return self._ott_entries(parsed)

        m = re.match(r"^/ott/v1/entries/([a-zA-Z0-9_]+)$", path)
        if m and method == "GET":
            return self._ott_entry_detail(m.group(1), parsed)

        m = re.match(
            r"^/ott/v1/entries/([a-zA-Z0-9_]+)/revisions/([a-zA-Z0-9_]+)/segments/(\d+)$",
            path,
        )
        if m and method == "GET":
            return self._ott_segment(m.group(1), m.group(2), int(m.group(3)))

        # ── OTT Repo v1 control plane (self-describing manifest) ──
        if method == "GET" and path == "/ott-repo.json":
            return self._ott_repo_manifest()

        # ── Optional Admin Profile + legacy /api alias ───────
        admin_path = None
        if path.startswith("/ott-admin/v1/"):
            admin_path = "/api" + path.removeprefix("/ott-admin/v1")
        elif path == "/api" or path.startswith("/api/"):
            admin_path = path
        if admin_path:
            if not self._admin_origin_allowed():
                return _err(self, "Admin API requires same-origin request", 403)
            if self._route_admin(method, admin_path):
                return

        # ── Static Profile + legacy static routes ─────────────
        if method == "GET":
            if path == "/" or path == "/index.html":
                return self._serve_frontend()

            if path == "/registry_index.json":
                return self._serve_file(self.data_dir / "registry_index.json")

            if path == "/ott.json":
                return self._serve_file(self.data_dir / "ott.json")

            if path == "/sources.json":
                return self._serve_file(self.data_dir / "sources.json")

            if path == "/entries.json":
                return self._serve_file(self.data_dir / "entries.json")

            m = re.match(r"^/entries/([a-zA-Z0-9_]+)\.json$", path)
            if m:
                return self._serve_file(
                    self.data_dir / "entries" / f"{m.group(1)}.json"
                )

            m = re.match(r"^/segments/([a-zA-Z0-9_]+)/(\d+)\.txt$", path)
            if m:
                return self._serve_file(
                    self.data_dir / "segments" / m.group(1) / f"{m.group(2)}.txt"
                )

            m = re.match(r"^/content/([a-zA-Z0-9_]+)\.json$", path)
            if m:
                return self._serve_file(
                    self.data_dir / "content" / f"{m.group(1)}.json"
                )

        _err(self, "Not found", 404)

    def _route_admin(self, method, path) -> bool:
        """Route the Admin Profile and its legacy `/api` alias."""
        if method == "GET" and path == "/api/status":
            self._api_status()
            return True

        if method == "GET" and path == "/api/sources":
            self._api_list_sources()
            return True

        if method == "POST" and path == "/api/sources":
            self._api_create_source()
            return True

        if method == "DELETE" and re.match(r"^/api/sources/[a-zA-Z0-9_]+$", path):
            self._api_delete_source(path.split("/")[-1])
            return True

        if method == "GET" and path == "/api/scripts":
            self._api_list_scripts()
            return True

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)$", path)
        if m and method == "GET":
            self._api_script_detail(m.group(1))
            return True

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/test$", path)
        if m and method == "POST":
            self._api_script_test(m.group(1))
            return True

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/run$", path)
        if m and method == "POST":
            self._api_script_run(m.group(1))
            return True

        if method == "POST" and path == "/api/scripts":
            self._api_create_script()
            return True

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/save$", path)
        if m and method == "POST":
            self._api_script_save(m.group(1))
            return True

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/rename$", path)
        if m and method == "POST":
            self._api_script_rename(m.group(1))
            return True

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/cron$", path)
        if m:
            name = m.group(1)
            if method == "GET":
                self._api_script_cron_get(name)
                return True
            if method == "POST":
                self._api_script_cron_set(name)
                return True

        if method == "GET" and path == "/api/entries/recent":
            self._api_entries_recent()
            return True

        if method == "GET" and path == "/api/entries":
            self._api_entries()
            return True

        if method == "POST" and path == "/api/entries":
            self._api_entry_add()
            return True

        m = re.match(r"^/api/entries/([a-zA-Z0-9_]+)$", path)
        if m and method == "DELETE":
            self._api_entry_delete(m.group(1))
            return True

        if method == "POST" and path == "/api/refresh":
            self._api_refresh()
            return True

        return False

    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        if self._is_admin_request_path(
            urlparse(unquote(self.path)).path.rstrip("/") or "/"
        ):
            if origin and self._admin_origin_allowed():
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _is_admin_request_path(self, path):
        return (
            path == "/api"
            or path.startswith(("/api/", "/ott-admin/v1/"))
        )

    def _admin_origin_allowed(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        host = self.headers.get("Host", "")
        return parsed.scheme == "http" and parsed.netloc == host


class ThreadLimitedServer(ThreadingHTTPServer):
    _pool = ThreadPoolExecutor(max_workers=8)

    def process_request(self, request, client_address):
        self._pool.submit(self.process_request_thread, request, client_address)


def start_server(port, data_dir):
    OttHandler.data_dir = Path(data_dir)
    server = ThreadLimitedServer(("127.0.0.1", port), OttHandler)
    print(f" OTT 适配器 {__version__} 已启动（OTT Core v1）")
    print(f"   地址: http://127.0.0.1:{port}")
    print(f"   数据: {data_dir}")
    print(" Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止.")
        server.server_close()
