"""OTT 适配器 HTTP 服务 + Web UI — 全新 v2 设计。

提供 RESTful API + 嵌入式 SPA 前端。
零外部依赖，仅用 Python stdlib。
"""

import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse
from .scheduler import run_script, rebuild_index

# ── 常量 ────────────────────────────────────────────────────
SOURCE_KEY_RE = re.compile(r"^[a-zA-Z0-9_]+$")
SCHEDULES_FILE = "schedules.json"
MAX_CONTENT_SIZE = 1024 * 1024  # 1MB POST body limit

# ── 请求读取辅助 ──────────────────────────────────────────────

def _read_body(self) -> bytes:
    length = int(self.headers.get("Content-Length", 0))
    if length > MAX_CONTENT_SIZE:
        return b""
    return self.rfile.read(length) if length else b""


def _json_body(self):
    try:
        return json.loads(_read_body(self) or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _json_resp(self, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self._cors_headers()
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    try:
        self.wfile.write(body)
    except (BrokenPipeError, ConnectionError):
        pass  # 客户端提前断开，无需处理


def _err(self, msg, status=400):
    _json_resp(self, {"error": msg}, status)


# ── 调度器集成 ───────────────────────────────────────────────

def _get_schedules(data_dir) -> dict:
    p = data_dir / SCHEDULES_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"schedules": {}}


def _save_schedules(data_dir, schedules):
    p = data_dir / SCHEDULES_FILE
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _update_last_run(data_dir, name):
    """同步 schedules.json 中 name 的 last_run 为 content 文件 mtime（口径对齐脚本页）。"""
    schedules = _get_schedules(data_dir)
    if name not in schedules.get("schedules", {}):
        return
    content_file = data_dir / "content" / f"{name}.json"
    if content_file.exists():
        schedules["schedules"][name]["last_run"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(content_file.stat().st_mtime + 8 * 3600)
        ) + "+08:00"
        _save_schedules(data_dir, schedules)


def _read_index(data_dir) -> dict:
    p = data_dir / "registry_index.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "updated_at": "", "sources": []}


# ── HTTP Handler ────────────────────────────────────────────

class OttHandler(BaseHTTPRequestHandler):
    data_dir = Path(".")
    _start_time = time.time()

    def log_message(self, fmt, *args):
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
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _route(self, method, path, parsed):
        """路由表：按 specificity 降序匹配。"""
        # ── API v2 ──────────────────────────────────────
        if method == "GET" and path == "/api/status":
            return self._api_status()

        if method == "GET" and path == "/api/sources":
            return self._api_list_sources()

        if method == "POST" and path == "/api/sources":
            return self._api_create_source()

        if method == "DELETE" and re.match(r"^/api/sources/[a-zA-Z0-9_]+$", path):
            return self._api_delete_source(path.split("/")[-1])

        if method == "GET" and path == "/api/scripts":
            return self._api_list_scripts()

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)$", path)
        if m and method == "GET":
            return self._api_script_detail(m.group(1))

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/test$", path)
        if m and method == "POST":
            return self._api_script_test(m.group(1))

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/run$", path)
        if m and method == "POST":
            return self._api_script_run(m.group(1))

        if method == "POST" and path == "/api/scripts":
            return self._api_create_script()

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/save$", path)
        if m and method == "POST":
            return self._api_script_save(m.group(1))

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/rename$", path)
        if m and method == "POST":
            return self._api_script_rename(m.group(1))

        m = re.match(r"^/api/scripts/([a-zA-Z0-9_]+)/cron$", path)
        if m:
            name = m.group(1)
            if method == "GET":
                return self._api_script_cron_get(name)
            if method == "POST":
                return self._api_script_cron_set(name)

        if method == "GET" and path == "/api/entries/recent":
            return self._api_entries_recent()

        if method == "GET" and path == "/api/entries":
            return self._api_entries()

        if method == "POST" and path == "/api/entries":
            return self._api_entry_add()

        m = re.match(r"^/api/entries/([a-zA-Z0-9_]+)$", path)
        if m and method == "DELETE":
            return self._api_entry_delete(m.group(1))

        if method == "POST" and path == "/api/refresh":
            return self._api_refresh()

        # ── 旧版兼容路由 ──────────────────────────────
        if method == "GET":
            if path == "/" or path == "/index.html":
                return self._serve_frontend()

            if path == "/registry_index.json":
                return self._serve_file(self.data_dir / "registry_index.json")

            m = re.match(r"^/content/([a-zA-Z0-9_]+)\.json$", path)
            if m:
                return self._serve_file(
                    self.data_dir / "content" / f"{m.group(1)}.json"
                )

        _err(self, "Not found", 404)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    # ── 文件服务 ──────────────────────────────────────────

    def _serve_file(self, path):
        if not path.exists():
            return _err(self, f"Not found: {path.name}", 404)
        body = path.read_bytes()
        self.send_response(200)
        self._cors_headers()
        ctype = "application/json; charset=utf-8" if path.suffix == ".json" else "application/octet-stream"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError):
            pass  # 客户端提前断开，无需处理

    # ── API: 系统状态 ─────────────────────────────────────

    def _api_status(self):
        dd = self.data_dir
        sources = _read_index(dd).get("sources", [])
        scripts_dir = dd / "scripts"
        scripts = sorted(s.name for s in scripts_dir.glob("fetch_*.py")) if scripts_dir.exists() else []
        script_keys = {s.removeprefix("fetch_").removesuffix(".py") for s in scripts}
        schedules = _get_schedules(dd)
        n_enabled = sum(
            1 for name, s in schedules.get("schedules", {}).items()
            if name in script_keys and s.get("enabled")
        )
        now = time.time()

        _json_resp(self, {
            "version": 2,
            "uptime": int(now - self._start_time),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self._start_time + 8 * 3600)) + "+08:00",
            "now_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "stats": {
                "sources": len(sources),
                "scripts": len(scripts),
                "active_schedules": n_enabled,
                "entries": sum(s.get("entries_count", 0) for s in sources),
            },
            "data_dir": str(dd.resolve()),
        })

    # ── API: 文本源列表 ──────────────────────────────────

    def _api_list_sources(self):
        index = _read_index(self.data_dir)
        sources = index.get("sources", [])

        # 注入 content 预览
        for s in sources:
            key = s["source_key"]
            content_file = self.data_dir / "content" / f"{key}.json"
            if content_file.exists():
                try:
                    d = json.loads(content_file.read_text(encoding="utf-8"))
                    s["_hasContent"] = True
                    s["_title"] = d.get("title", "")
                    s["_preview"] = (d.get("content", "") or "")[:120]
                except Exception:
                    s["_hasContent"] = False
                    s["_preview"] = ""
            else:
                s["_hasContent"] = False
                s["_preview"] = ""

            # 检查对应脚本是否存在
            script = self.data_dir / "scripts" / f"fetch_{key}.py"
            s["_hasScript"] = script.exists()

        _json_resp(self, {
            "version": index.get("version", 1),
            "updated_at": index.get("updated_at", ""),
            "sources": sources,
        })

    # ── API: 创建静态合集 ───────────────────────────────

    def _api_create_source(self):
        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        source_key = (body.get("source_key") or "").strip()
        title = (body.get("title") or "未命名").strip()
        content = (body.get("content") or "").strip()
        description = (body.get("description") or content[:80]).strip()
        category = (body.get("category") or "static").strip()
        tags = body.get("tags", [])
        author = (body.get("author") or "").strip()

        if not source_key:
            return _err(self, "source_key 必填")
        if not SOURCE_KEY_RE.match(source_key):
            return _err(self, "source_key 只能包含字母、数字、下划线")
        if not content:
            return _err(self, "content 必填")

        dd = self.data_dir
        content_dir = dd / "content"
        content_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "source_key": source_key,
            "title": title,
            "content": content,
            "metadata": {
                "description": description,
                "category": category,
                "tags": tags,
                "date": time.strftime("%Y-%m-%d"),
            },
        }
        if author:
            data["metadata"]["author"] = author

        path = content_dir / f"{source_key}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

        # 重建索引
        rebuild_index(dd)

        _json_resp(self, {"ok": True, "source_key": source_key}, 201)

    # ── API: 删除合集 ───────────────────────────────────

    def _api_delete_source(self, key):
        if not SOURCE_KEY_RE.match(key):
            return _err(self, "无效的 source_key")

        dd = self.data_dir
        content_file = dd / "content" / f"{key}.json"
        if not content_file.exists():
            return _err(self, f"source '{key}' 不存在", 404)

        content_file.unlink()
        rebuild_index(dd)

        _json_resp(self, {"ok": True, "source_key": key})

    # ── API: 脚本列表 ─────────────────────────────────────

    def _api_list_scripts(self):
        scripts_dir = self.data_dir / "scripts"
        scripts = []
        if scripts_dir.exists():
            for f in sorted(scripts_dir.glob("fetch_*.py")):
                key = f.stem.replace("fetch_", "", 1)
                content_file = self.data_dir / "content" / f"{key}.json"
                has_content = content_file.exists()
                content_age = time.time() - content_file.stat().st_mtime if has_content else None
                scripts.append({
                    "name": f.name,
                    "source_key": key,
                    "size": f.stat().st_size,
                    "has_content": has_content,
                    "content_age_seconds": content_age,
                    "content_age_human": _format_age(content_age) if content_age else None,
                })
        _json_resp(self, {"scripts": scripts})

    # ── API: 脚本详情 ─────────────────────────────────────

    def _api_script_detail(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)

        source = script.read_text(encoding="utf-8")
        content_file = self.data_dir / "content" / f"{name}.json"
        has_content = content_file.exists()
        content_preview = None
        if has_content:
            try:
                d = json.loads(content_file.read_text(encoding="utf-8"))
                content_preview = d.get("content", "")[:200]
            except Exception:
                pass

        _json_resp(self, {
            "name": script.name,
            "source_key": name,
            "size": script.stat().st_size,
            "source": source,
            "has_content": has_content,
            "content_preview": content_preview,
        })

    # ── API: 脚本测试（dry-run）───────────────────────────

    def _api_script_test(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)

        # 测试模式：添加 --dry-run
        cmd = [sys.executable, str(script), "--dry-run"]
        if "--date" in script.read_text(encoding="utf-8"):
            cmd.extend(["--date", time.strftime("%Y-%m-%d")])

        start = time.time()
        try:
            r = subprocess.run(
                cmd,
                cwd=self.data_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return _json_resp(self, {
                "ok": False, "error": "执行超时（30s）",
                "duration": time.time() - start,
            })
        except Exception as e:
            return _json_resp(self, {
                "ok": False, "error": str(e),
                "duration": time.time() - start,
            })

        elapsed = round(time.time() - start, 3)
        success = r.returncode == 0

        # 尝试解析 JSON 输出（如果脚本输出指向已有文件则读文件）
        preview_content = None
        validation = None
        if success:
            content_file = self.data_dir / "content" / f"{name}.json"
            if content_file.exists():
                try:
                    d = json.loads(content_file.read_text(encoding="utf-8"))
                    preview_content = (d.get("content", "") or "")[:200]
                    # schema 验证
                    validation = _validate_ott_json(d)
                except json.JSONDecodeError as e:
                    validation = {"valid": False, "error": f"JSON 解析失败: {e}"}
            else:
                validation = {"valid": False, "error": "测试未产生 content 文件"}

        _json_resp(self, {
            "ok": success,
            "exit_code": r.returncode,
            "duration": elapsed,
            "stdout": r.stdout[:2000] if r.stdout else "",
            "stderr": r.stderr[:2000] if r.stderr else "",
            "preview": preview_content,
            "validation": validation or {"valid": True},
        })

    # ── API: 脚本运行（真实抓取）─────────────────────────

    def _api_script_run(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)

        success, output = run_script(script)

        if success:
            _update_last_run(self.data_dir, name)
        rebuild_index(self.data_dir)

        if success:
            content_file = self.data_dir / "content" / f"{name}.json"
            preview = None
            if content_file.exists():
                try:
                    d = json.loads(content_file.read_text(encoding="utf-8"))
                    preview = (d.get("content", "") or "")[:200]
                except Exception:
                    pass
            _json_resp(self, {
                "ok": True, "output": output[:2000] if output else "",
                "preview": preview,
            })
        else:
            _json_resp(self, {
                "ok": False, "error": output[:500] if output else "执行失败",
            })

    # ── API: 创建脚本 ─────────────────────────────────────

    def _api_create_script(self):
        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        source_key = (body.get("source_key") or "").strip()
        source_code = body.get("source_code") or ""

        if not source_key:
            return _err(self, "source_key 必填")
        if not SOURCE_KEY_RE.match(source_key):
            return _err(self, "source_key 只能含字母数字下划线")

        scripts_dir = self.data_dir / "scripts"
        script_file = scripts_dir / f"fetch_{source_key}.py"
        if script_file.exists():
            return _err(self, f"脚本 fetch_{source_key}.py 已存在", 409)

        # 使用模板填充
        if not source_code.strip():
            source_code = _script_template(source_key)

        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_file.write_text(source_code, encoding="utf-8")
        _json_resp(self, {"ok": True, "name": f"fetch_{source_key}.py", "source_key": source_key}, 201)

    # ── API: 保存脚本源码 ─────────────────────────────────

    def _api_script_save(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)

        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        source_code = body.get("source_code", "")
        if not source_code.strip():
            return _err(self, "源码不可为空")

        script.write_text(source_code, encoding="utf-8")
        _json_resp(self, {"ok": True, "name": f"fetch_{name}.py"})

    # ── API: 重命名脚本 ───────────────────────────────────

    def _api_script_rename(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        new_key = (body.get("new_key") or "").strip()
        if not new_key:
            return _err(self, "new_key 必填")
        if not SOURCE_KEY_RE.match(new_key):
            return _err(self, "new_key 只能含字母数字下划线")

        dd = self.data_dir
        old_script = dd / "scripts" / f"fetch_{name}.py"
        new_script = dd / "scripts" / f"fetch_{new_key}.py"
        if not old_script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)
        if new_script.exists():
            return _err(self, f"目标脚本 'fetch_{new_key}.py' 已存在", 409)

        old_script.rename(new_script)

        # 也重命名对应的 content 文件（如果存在）
        old_content = dd / "content" / f"{name}.json"
        new_content = dd / "content" / f"{new_key}.json"
        if old_content.exists():
            try:
                d = json.loads(old_content.read_text(encoding="utf-8"))
                d["source_key"] = new_key
                tmp = new_content.with_suffix(".tmp")
                tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(new_content)
                old_content.unlink()
            except Exception:
                pass

        rebuild_index(dd)
        _json_resp(self, {"ok": True, "old_key": name, "new_key": new_key})

    # ── API: Cron 配置 ────────────────────────────────────

    def _api_script_cron_get(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        schedules = _get_schedules(self.data_dir)
        sched = schedules.get("schedules", {}).get(name, {
            "interval": "manual",
            "enabled": False,
            "last_run": None,
            "next_run": None,
        })
        _json_resp(self, sched)

    def _api_script_cron_set(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        interval = body.get("interval", "manual")
        if interval not in ("manual", "hourly", "daily", "weekly"):
            return _err(self, "interval 可选: manual / hourly / daily / weekly")

        enabled = body.get("enabled", interval != "manual")

        schedules = _get_schedules(self.data_dir)
        if "schedules" not in schedules:
            schedules["schedules"] = {}

        now = time.time()
        prev = schedules["schedules"].get(name, {})
        last_run = prev.get("last_run")

        schedules["schedules"][name] = {
            "interval": interval,
            "enabled": enabled,
            "last_run": last_run,
            "next_run": _calc_next_run(interval, last_run) if enabled else None,
        }

        _save_schedules(self.data_dir, schedules)
        _json_resp(self, {"ok": True, **schedules["schedules"][name]})

    # ── API: 最近条目（仪表盘用，不含全文） ────────────────

    def _api_entries_recent(self):
        content_dir = self.data_dir / "content"
        recent = []
        if content_dir.exists():
            for f in content_dir.glob("*.json"):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                sk = d.get("source_key", f.stem)
                entries = d.get("entries", [])
                if not entries and d.get("content"):
                    entries = [{"title": d.get("title", ""), "fetched_at": ""}]
                for e in entries:
                    recent.append({
                        "source_key": sk,
                        "title": e.get("title", sk),
                        "fetched_at": e.get("fetched_at", ""),
                    })
            recent.sort(key=lambda x: x["fetched_at"], reverse=True)
            recent = recent[:5]
        _json_resp(self, {"entries": recent})

    # ── API: 全部条目 ─────────────────────────────────────

    def _api_entries(self):
        """聚合所有合集的全部历史条目。"""
        content_dir = self.data_dir / "content"
        all_entries = []
        for f in sorted(content_dir.glob("*.json"), reverse=True):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            sk = d.get("source_key", f.stem)
            label = d.get("title", sk)
            entries = d.get("entries", [])
            if not entries and d.get("content"):
                entries = [{
                    "title": d.get("title", ""), "content": d["content"],
                    "metadata": d.get("metadata", {}),
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime(f.stat().st_mtime)),
                }]
            for e in entries:
                meta = e.get("metadata", {})
                all_entries.append({
                    "id": f"{sk}-{e.get('fetched_at', '')}",
                    "source_key": sk,
                    "source_label": label,
                    "title": e.get("title", ""),
                    "content": e.get("content", ""),
                    "preview": (e.get("content", "")[:100]).replace("\n", " ").strip(),
                    "category": meta.get("category", ""),
                    "tags": meta.get("tags", []),
                    "fetched_at": e.get("fetched_at", ""),
                    "charCount": len(e.get("content", "")),
                })
        all_entries.sort(key=lambda x: x["fetched_at"], reverse=True)
        _json_resp(self, {"entries": all_entries, "total": len(all_entries)})

    def _api_entry_add(self):
        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")
        source_key = (body.get("source_key") or "").strip()
        if not source_key or not SOURCE_KEY_RE.match(source_key):
            return _err(self, "source_key 必填，只能含字母数字下划线")
        title = (body.get("title") or "").strip()
        content = body.get("content", "")
        if not content:
            return _err(self, "内容不可为空")
        content_dir = self.data_dir / "content"
        content_dir.mkdir(parents=True, exist_ok=True)
        fpath = content_dir / f"{source_key}.json"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())
        if fpath.exists():
            try:
                d = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                d = {}
            entries = d.get("entries", [])
            if not entries and d.get("content"):
                entries = [{
                    "title": d.get("title", ""),
                    "content": d.get("content", ""),
                    "metadata": d.get("metadata", {}),
                    "fetched_at": now_iso,
                }]
            dup = False
            for i, e in enumerate(entries):
                if e.get("content") == content:
                    entries[i] = {
                        "title": title,
                        "content": content,
                        "metadata": {
                            "category": body.get("category", ""),
                            "tags": [t.strip() for t in body.get("tags", "").split(",") if t.strip()],
                            "description": body.get("description", ""),
                        },
                        "fetched_at": now_iso,
                    }
                    dup = True
                    break
            if not dup:
                entries.append({
                    "title": title,
                    "content": content,
                    "metadata": {
                        "category": body.get("category", ""),
                        "tags": [t.strip() for t in body.get("tags", "").split(",") if t.strip()],
                        "description": body.get("description", ""),
                    },
                    "fetched_at": now_iso,
                })
            d["entries"] = entries
            d["title"] = title
            d["content"] = content
        else:
            d = {
                "source_key": source_key,
                "title": title,
                "content": content,
                "metadata": {
                    "category": body.get("category", ""),
                    "tags": [t.strip() for t in body.get("tags", "").split(",") if t.strip()],
                    "description": body.get("description", ""),
                },
                "entries": [{
                    "title": title,
                    "content": content,
                    "metadata": {
                        "category": body.get("category", ""),
                        "tags": [t.strip() for t in body.get("tags", "").split(",") if t.strip()],
                        "description": body.get("description", ""),
                    },
                    "fetched_at": now_iso,
                }],
            }
        fpath.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        rebuild_index(self.data_dir)
        _update_last_run(self.data_dir, source_key)
        _json_resp(self, {"ok": True, "source_key": source_key, "fetched_at": now_iso}, 201)

    def _api_entry_delete(self, source_key):
        body = _json_body(self)
        content_dir = self.data_dir / "content"
        fpath = content_dir / f"{source_key}.json"
        if not fpath.exists():
            return _err(self, f"合集 '{source_key}' 不存在", 404)
        delete_all = body.get("delete_all", False) if body else False
        entry_id = body.get("entry_id") if body else None
        d = json.loads(fpath.read_text(encoding="utf-8"))
        entries = d.get("entries", [])
        if delete_all or (not entry_id and not entries):
            # 清空条目，保留文件骨架
            d["entries"] = []
            d["content"] = ""
        elif entry_id and entries:
            idx = None
            # 按 id 匹配（格式: source_key-fetched_at）
            prefix = f"{source_key}-"
            eid = entry_id
            if eid.startswith(prefix):
                eid = eid[len(prefix):]
            for i, e in enumerate(entries):
                if e.get("fetched_at", "") == eid:
                    idx = i
                    break
            if idx is None:
                return _err(self, f"未找到条目: {entry_id}", 404)
            entries.pop(idx)
            d["entries"] = entries
            if entries:
                d["title"] = entries[-1].get("title", "")
                d["content"] = entries[-1].get("content", "")
            else:
                d["title"] = ""
                d["content"] = ""
        fpath.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        rebuild_index(self.data_dir)
        _update_last_run(self.data_dir, source_key)
        entries_left = len(d.get("entries", []))
        _json_resp(self, {"ok": True, "entries_left": entries_left})

    # ── API: 重建索引 ─────────────────────────────────────

    def _api_refresh(self):
        try:
            idx = rebuild_index(self.data_dir)
            _json_resp(self, {
                "ok": True,
                "sources": len(idx.get("sources", [])),
            })
        except Exception as e:
            _err(self, f"重建索引失败: {e}", 500)

    # ── Web UI 前端 ──────────────────────────────────────

    def _serve_frontend(self):
        body = FRONTEND_HTML.encode("utf-8")
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


# ── 工具函数 ────────────────────────────────────────────────

def _script_template(source_key):
    return f'''#!/usr/bin/env python3
"""fetch_{source_key}.py — {{description}}。

DISCLAIMER: 请确保抓取行为符合目标网站 robots.txt 及当地版权法，使用者自负全责。
"""

import json
import time
from pathlib import Path
import httpx

SOURCE_KEY = "{source_key}"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "content" / f"{{SOURCE_KEY}}.json"


def _load_data():
    """读取已有数据，兼容旧格式自动迁移。"""
    if not OUTPUT_PATH.exists():
        return {{"source_key": SOURCE_KEY, "entries": []}}
    d = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    if "entries" not in d and "content" in d:
        d["entries"] = [{{
            "title": d.pop("title", ""),
            "content": d.pop("content", ""),
            "metadata": d.pop("metadata", {{}}),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
        }}]
    d.setdefault("entries", [])
    return d


def _append_entry(d, entry):
    """追加一条记录，顶层保留最新内容以兼容旧客户端。"""
    entry["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())
    content = entry.get("content", "")
    for i, e in enumerate(d["entries"]):
        if e.get("content") == content:
            d["entries"][i] = entry
            d["title"] = entry["title"]
            d["content"] = content
            d["metadata"] = entry.get("metadata", {{}})
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = OUTPUT_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(OUTPUT_PATH)
            print(f"[{{SOURCE_KEY}}] 已更新（重复内容）— 共 {{len(d['entries'])}} 篇")
            return
    d["entries"].append(entry)
    d["title"] = entry["title"]
    d["content"] = entry["content"]
    d["metadata"] = entry.get("metadata", {{}})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    print(f"[{{SOURCE_KEY}}] 已追加 — 共 {{len(d['entries'])}} 篇")


def fetch():
    with httpx.Client(timeout=20, trust_env=False) as client:
        resp = client.get("https://example.com/api/text")
        resp.raise_for_status()
        return resp.json()


def main():
    data = fetch()
    entry = {{
        "title": data.get("title", SOURCE_KEY),
        "content": data["text"],
        "metadata": {{
            "description": "你的文本描述",
            "category": "static",
            "tags": ["标签1", "标签2"],
        }}
    }}
    d = _load_data()
    _append_entry(d, entry)


if __name__ == "__main__":
    main()
'''


def _format_age(seconds):
    if seconds is None:
        return "未知"
    if seconds < 60:
        return f"{int(seconds)} 秒前"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    days = int(seconds // 86400)
    return f"{days} 天前"


def _calc_next_run(interval, last_run_ts=None):
    now = time.time()
    base = last_run_ts or now
    offsets = {"hourly": 3600, "daily": 86400, "weekly": 604800}
    secs = offsets.get(interval)
    if not secs:
        return None
    nxt = max(base + secs, now + 60)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(nxt))


def _validate_ott_json(data: dict) -> dict:
    """验证 OTT 内容文件是否符合 SPEC.md 规范。"""
    errors = []
    if not isinstance(data, dict):
        return {"valid": False, "error": "顶层不是 JSON 对象"}

    source_key = data.get("source_key")
    if not source_key or not isinstance(source_key, str):
        errors.append("缺少或无效 source_key（必填字符串）")
    elif not SOURCE_KEY_RE.match(source_key):
        errors.append("source_key 只能含字母数字下划线")

    content_val = data.get("content")
    content_str = content_val if isinstance(content_val, str) else ""
    if not content_str:
        errors.append("缺少或无效 content（必填非空字符串）")

    title_val = data.get("title")
    title_str = title_val if isinstance(title_val, str) else ""
    if not title_str:
        errors.append("缺少或无效 title（必填字符串）")

    if errors:
        return {"valid": False, "error": "; ".join(errors)}
    return {"valid": True, "charCount": len(content_str), "source_key": source_key}


def start_server(port, data_dir):
    OttHandler.data_dir = Path(data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), OttHandler)
    print(f" OTT 适配器 v2 已启动")
    print(f"   地址: http://127.0.0.1:{port}")
    print(f"   数据: {data_dir}")
    print(f" Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止.")
        server.server_close()


# ═══════════════════════════════════════════════════════════════
# 前端 SPA — 单 HTML 文件，嵌入 CSS + JS
# ═══════════════════════════════════════════════════════════════

FRONTEND_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OTT 控制台</title>
<style>
/* ═══════════════════════════════════════════════
   设计令牌
   ═══════════════════════════════════════════════ */
:root {
  --bg-canvas:      #0d0d0f;
  --bg-surface:     #161618;
  --bg-elevated:    #1c1c20;
  --bg-sidebar:     #111113;
  --bg-input:       #1a1a1e;
  --bg-code:        #0a0a0c;

  --text-primary:   rgba(255,255,255,0.92);
  --text-regular:   rgba(255,255,255,0.82);
  --text-secondary: rgba(255,255,255,0.58);
  --text-muted:     rgba(255,255,255,0.40);

  --gold:         #D4A800;
  --gold-hover:   #E8B800;
  --gold-dim:     rgba(212,168,0,0.13);
  --gold-glow:    rgba(212,168,0,0.20);

  --green:        #52c41a;
  --red:          #ff4d4f;
  --blue:         #1677ff;
  --orange:       #faad14;
  --purple:       #722ed1;

  --border:       rgba(255,255,255,0.07);
  --border-hover: rgba(255,255,255,0.14);
  --border-accent:rgba(212,168,0,0.25);

  --radius-sm: 6px;
  --radius:    10px;
  --radius-lg: 14px;

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
  --shadow:    0 4px 20px rgba(0,0,0,0.35);
  --shadow-lg: 0 12px 40px rgba(0,0,0,0.5);

  --ease: cubic-bezier(0.16, 1, 0.3, 1);
  --font: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
  --font-mono: "SF Mono", "Fira Code", "Cascadia Code", "JetBrains Mono", "Consolas", monospace;

  --sidebar-w: 228px;
  --transition: 180ms var(--ease);
}

*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{
  font-family:var(--font);
  background:var(--bg-canvas);
  color:var(--text-primary);
  font-size:14px;
  line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
::selection{background:var(--gold-dim);color:#fff}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border-hover);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.2)}

/* ═══ 布局 ═══ */
.app{display:flex;height:100vh;overflow:hidden}

/* ═══ 侧边栏 ═══ */
.sidebar{
  width:var(--sidebar-w);flex-shrink:0;
  background:var(--bg-sidebar);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;
  position:relative;
}
.sidebar::after{
  content:'';position:absolute;top:0;right:-1px;bottom:0;width:1px;
  background:linear-gradient(to bottom, transparent, var(--gold-dim) 30%, var(--gold-dim) 70%, transparent);
  opacity:0.3;
}
.sidebar-header{
  padding:22px 20px 18px;
  border-bottom:1px solid var(--border);
}
.sidebar-header h1{
  font-size:19px;font-weight:600;
  display:flex;align-items:center;gap:10px;
  letter-spacing:-0.3px;
}
.sidebar-header h1 .logo{
  width:30px;height:30px;
  background:linear-gradient(135deg, var(--gold), #E8B800);
  border-radius:7px;display:inline-flex;align-items:center;justify-content:center;
  font-size:12px;font-weight:700;color:#0d0d0f;
  box-shadow:0 2px 8px var(--gold-glow);
}
.sidebar-header .sub{
  font-size:11px;color:var(--text-muted);margin-top:3px;padding-left:40px;
  letter-spacing:0.5px;
}
.nav{flex:1;padding:14px 10px;overflow-y:auto}
.nav-item{
  display:flex;align-items:center;gap:10px;
  padding:9px 12px;border-radius:var(--radius-sm);
  cursor:pointer;color:var(--text-secondary);
  transition:all var(--transition);font-size:13px;font-weight:500;
  user-select:none;position:relative;
}
.nav-item:hover{background:rgba(255,255,255,0.04);color:var(--text-primary)}
.nav-item.active{
  background:var(--gold-dim);color:var(--gold);font-weight:600;
}
.nav-item.active::before{
  content:'';position:absolute;left:0;top:7px;bottom:7px;width:2.5px;
  background:var(--gold);border-radius:0 3px 3px 0;
}
.nav-item .ico{width:20px;text-align:center;font-size:13px;flex-shrink:0;opacity:0.65}
.nav-item.active .ico{opacity:1}
.nav-item .badge{
  margin-left:auto;
  background:rgba(255,255,255,0.07);color:var(--text-secondary);
  font-size:10px;font-weight:600;padding:1px 7px;border-radius:8px;
  min-width:20px;text-align:center;
}
.nav-item.active .badge{background:var(--gold-dim);color:var(--gold)}

/* ═══ 主内容 ═══ */
.main{flex:1;overflow-y:auto;padding:28px 32px;min-width:0}
.page{display:none;animation:fadeIn 220ms var(--ease)}
.page.active{display:block}
.page-header{margin-bottom:22px}
.page-header h2{font-size:20px;font-weight:600;letter-spacing:-0.3px}
.page-header p{font-size:13px;color:var(--text-secondary);margin-top:3px}

/* ═══ 卡片 ═══ */
.card{
  background:var(--bg-surface);
  border:1px solid var(--border);
  border-radius:var(--radius);
  padding:22px;
  margin-bottom:18px;
  transition:all var(--transition);
}
.card:hover{border-color:var(--border-hover)}
.card-header{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:14px;padding-bottom:11px;border-bottom:1px solid var(--border);
}
.card-header h3{font-size:14px;font-weight:600;color:var(--text-regular);letter-spacing:-0.2px}

/* ═══ 统计卡片 ═══ */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:26px}
.stat{
  background:var(--bg-surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:18px 22px;
  transition:all var(--transition);cursor:default;position:relative;overflow:hidden;
}
.stat::before{
  content:'';position:absolute;top:0;left:0;width:100%;height:100%;
  background:linear-gradient(135deg, transparent 60%, rgba(255,255,255,0.02));
  pointer-events:none;
}
.stat:hover{border-color:var(--border-hover);transform:translateY(-1px)}
.stat .val{font-size:28px;font-weight:600;letter-spacing:-0.5px;line-height:1.2}
.stat .lbl{font-size:12px;color:var(--text-secondary);margin-top:4px}
.stat.gold{border-left:3px solid var(--gold)}
.stat.blue{border-left:3px solid var(--blue)}
.stat.purple{border-left:3px solid var(--purple)}
.stat.orange{border-left:3px solid var(--orange)}

/* ═══ 表格 ═══ */
.table-wrap{overflow-x:auto;margin:0 -4px}
table{width:100%;border-collapse:separate;border-spacing:0}
th{
  padding:9px 16px;text-align:left;
  font-size:11px;font-weight:600;color:var(--text-muted);
  text-transform:uppercase;letter-spacing:0.4px;
  border-bottom:1px solid var(--border);
  background:var(--bg-surface);position:sticky;top:0;
  white-space:nowrap;
}
td{
  padding:11px 16px;border-bottom:1px solid var(--border);
  font-size:13px;color:var(--text-regular);
  transition:background var(--transition);
}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,0.02)}
td .tag{
  display:inline-block;
  background:var(--gold-dim);color:var(--gold);
  font-size:10px;font-weight:600;padding:2px 9px;border-radius:4px;
  letter-spacing:0.2px;
}
td .tag-blue{background:rgba(22,119,255,0.12);color:var(--blue)}
td .tag-green{background:rgba(82,196,26,0.12);color:var(--green)}

/* ═══ 按钮 ═══ */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:5px;
  padding:7px 16px;border-radius:var(--radius-sm);border:none;
  font-family:var(--font);font-size:13px;font-weight:500;
  cursor:pointer;transition:all var(--transition);text-decoration:none;
  line-height:1.4;
}
.btn:active{transform:scale(0.97)}
.btn-gold{
  background:linear-gradient(135deg, #C49A00, #E8B800);color:#0d0d0f;font-weight:600;
}
.btn-gold:hover{box-shadow:0 4px 14px var(--gold-glow);transform:translateY(-1px)}
.btn-ghost{background:transparent;color:var(--text-secondary);border:1px solid var(--border)}
.btn-ghost:hover{background:rgba(255,255,255,0.04);border-color:var(--border-hover);color:var(--text-primary)}
.btn-outline{background:transparent;color:var(--gold);border:1px solid var(--gold)}
.btn-outline:hover{background:var(--gold-dim)}
.btn-danger{background:var(--red);color:#fff;font-weight:600}
.btn-danger:hover{background:#e84748;box-shadow:0 4px 14px rgba(255,77,79,0.25)}
.btn-sm{padding:4px 11px;font-size:12px;border-radius:5px}
.btn-xs{padding:2px 8px;font-size:11px;border-radius:4px}
.btn:disabled{opacity:0.35;cursor:not-allowed;transform:none!important}

/* ═══ 表单 ═══ */
.form-group{margin-bottom:18px}
.form-group label{display:block;font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px}
.form-group input,.form-group textarea,.form-group select{
  width:100%;padding:9px 13px;
  background:var(--bg-input);border:1px solid var(--border);
  border-radius:var(--radius-sm);color:var(--text-primary);font-size:13px;
  transition:all var(--transition);outline:none;font-family:var(--font);
}
.form-group input:focus,.form-group textarea:focus,.form-group select:focus{
  border-color:var(--gold);box-shadow:0 0 0 3px var(--gold-dim);
}
.form-group textarea{min-height:80px;resize:vertical;font-family:var(--font-mono);font-size:12px;line-height:1.6}
.form-group .hint{font-size:11px;color:var(--text-muted);margin-top:4px}

/* ═══ 工具栏 ═══ */
.toolbar{display:flex;gap:10px;margin-bottom:18px;align-items:center;flex-wrap:wrap}
.toolbar input{
  flex:1;min-width:160px;padding:8px 13px;
  background:var(--bg-input);border:1px solid var(--border);
  border-radius:var(--radius-sm);color:var(--text-primary);font-size:13px;
  outline:none;transition:all var(--transition);font-family:var(--font);
}
.toolbar input:focus{border-color:var(--gold);box-shadow:0 0 0 3px var(--gold-dim)}
.toolbar select{
  padding:8px 13px;background:var(--bg-input);border:1px solid var(--border);
  border-radius:var(--radius-sm);color:var(--text-primary);font-size:13px;
  outline:none;cursor:pointer;font-family:var(--font);
}
.toolbar select:focus{border-color:var(--gold)}

/* ═══ 模态框 ═══ */
.modal-overlay{
  position:fixed;inset:0;
  background:rgba(0,0,0,0.55);
  backdrop-filter:blur(4px);
  -webkit-backdrop-filter:blur(4px);
  z-index:100;display:none;
  align-items:center;justify-content:center;
  animation:fadeIn 180ms var(--ease);
}
.modal-overlay.open{display:flex}
.modal{
  background:var(--bg-elevated);
  border:1px solid var(--border-hover);
  border-radius:var(--radius-lg);
  width:90%;max-width:700px;
  max-height:85vh;overflow-y:auto;
  padding:26px 28px;
  box-shadow:var(--shadow-lg);
  animation:slideUp 250ms var(--ease);
  position:relative;
}
.modal.wide{max-width:820px}
.modal .close-btn{
  position:absolute;top:14px;right:14px;
  width:32px;height:32px;
  display:flex;align-items:center;justify-content:center;
  border:none;background:rgba(255,255,255,0.04);
  border:1px solid var(--border);border-radius:50%;
  cursor:pointer;color:var(--text-secondary);font-size:14px;
  transition:all var(--transition);
}
.modal .close-btn:hover{background:rgba(255,255,255,0.08);color:var(--text-primary)}
.modal-title{font-size:17px;font-weight:600;margin-bottom:6px;padding-right:32px;letter-spacing:-0.3px}
.modal-meta{font-size:12px;color:var(--text-secondary);margin-bottom:18px;display:flex;flex-wrap:wrap;gap:12px}

/* ═══ 内容展示 ═══ */
.content-box{
  background:var(--bg-code);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:16px;
  font-family:var(--font-mono);font-size:13px;line-height:1.8;
  white-space:pre-wrap;word-break:break-word;max-height:380px;overflow-y:auto;
  color:var(--text-regular);
}
.code-box{
  background:var(--bg-code);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:14px;
  font-family:var(--font-mono);font-size:12px;line-height:1.5;
  overflow:auto;white-space:pre;max-height:320px;
  color:var(--text-regular);
}
.terminal{
  background:#08080a;border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:14px;
  font-family:var(--font-mono);font-size:12px;line-height:1.5;
  white-space:pre-wrap;word-break:break-all;max-height:260px;overflow-y:auto;
  color:#98c379;
}
.terminal .err{color:#e06c75}
.terminal .info{color:#61afef}
.terminal .warn{color:#e5c07b}

/* ═══ 状态指示点 ═══ */
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;flex-shrink:0}
.dot.gold{background:var(--gold);box-shadow:0 0 6px var(--gold-glow)}
.dot.green{background:var(--green);box-shadow:0 0 6px rgba(82,196,26,0.25)}
.dot.red{background:var(--red);box-shadow:0 0 6px rgba(255,77,79,0.25)}
.dot.gray{background:var(--text-muted)}
.dot.blue{background:var(--blue);box-shadow:0 0 6px rgba(22,119,255,0.25)}

/* ═══ 消息提示 ═══ */
.toast-c{position:fixed;top:18px;right:18px;z-index:999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{
  pointer-events:auto;
  background:rgba(28,28,32,0.92);
  backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);
  border:1px solid var(--border-hover);
  border-radius:var(--radius-sm);padding:11px 18px;
  min-width:260px;max-width:380px;
  box-shadow:var(--shadow-lg);
  animation:slideIn 220ms var(--ease);
  font-size:13px;font-weight:500;
  display:flex;align-items:center;gap:9px;
}
.toast.gold{border-left:3px solid var(--gold)}
.toast.red{border-left:3px solid var(--red)}
.toast.blue{border-left:3px solid var(--blue)}
.toast.green{border-left:3px solid var(--green)}

/* ═══ Cron 设置 ═══ */
.cron-row{
  display:flex;align-items:center;gap:12px;
  padding:11px 16px;background:var(--bg-input);
  border:1px solid var(--border);border-radius:var(--radius-sm);
  margin-bottom:7px;transition:border-color var(--transition);
}
.cron-row:hover{border-color:var(--border-hover)}
.cron-row .name{font-weight:600;min-width:100px;font-size:13px}
.cron-row select{
  padding:5px 10px;background:var(--bg-canvas);
  border:1px solid var(--border);border-radius:4px;
  color:var(--text-primary);font-size:12px;outline:none;cursor:pointer;
  font-family:var(--font);
}
.cron-row .info{font-size:11px;color:var(--text-muted)}
.toggle{
  position:relative;width:38px;height:20px;
  background:rgba(255,255,255,0.1);border-radius:10px;
  cursor:pointer;transition:background var(--transition);flex-shrink:0;
}
.toggle.on{background:var(--gold)}
.toggle::after{
  content:'';position:absolute;top:2px;left:2px;
  width:16px;height:16px;background:#fff;border-radius:50%;
  transition:transform var(--transition);
}
.toggle.on::after{transform:translateX(18px)}

/* ═══ 空状态 / 加载 ═══ */
.loading{text-align:center;padding:50px 20px;color:var(--text-muted)}
.loading .spinner{
  display:inline-block;width:26px;height:26px;
  border:2px solid rgba(255,255,255,0.07);
  border-top-color:var(--gold);
  border-radius:50%;animation:spin .7s linear infinite;
  margin-bottom:12px;
}
.empty{text-align:center;padding:50px 20px;color:var(--text-muted)}
.empty .ico{font-size:34px;margin-bottom:10px;opacity:0.3}
.empty p{font-size:13px;color:var(--text-secondary)}
.empty code{background:rgba(255,255,255,0.05);padding:2px 7px;border-radius:4px;font-family:var(--font-mono);font-size:12px}

/* ═══ 双栏布局 ═══ */
.split{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.split-wide{display:grid;grid-template-columns:2fr 1fr;gap:16px}
@media(max-width:900px){.split,.split-wide{grid-template-columns:1fr}}

/* ═══ 行内编辑 ═══ */
.inline-edit{display:flex;align-items:center;gap:8px}
.inline-edit input{
  padding:5px 10px;background:var(--bg-input);
  border:1px solid var(--border);border-radius:4px;
  color:var(--text-primary);font-family:var(--font-mono);font-size:13px;
  outline:none;width:180px;
}
.inline-edit input:focus{border-color:var(--gold)}

/* ═══ 操作栏 ═══ */
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}

/* ═══ 动画 ═══ */
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes slideUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes slideIn{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}
@keyframes spin{to{transform:rotate(360deg)}}

/* ═══ 响应式 ═══ */
@media(max-width:768px){
  .sidebar{width:58px}
  .sidebar-header h1 .label,.sidebar-header .sub,.nav-item .label,.nav-item .badge{display:none}
  .sidebar-header{padding:16px 10px}
  .nav-item{padding:9px;justify-content:center}
  .main{padding:16px}
  .stats{grid-template-columns:repeat(2,1fr)}
  .modal{padding:20px;width:95%}
}
@media(max-width:480px){
  .stats{grid-template-columns:1fr}
  .toolbar{flex-direction:column}
  .toolbar input{min-width:auto;width:100%}
}
</style>
</head>
<body>
<div class="app">

<!-- ═══ 侧边栏 ═══ -->
<aside class="sidebar">
  <div class="sidebar-header">
    <h1><span class="logo">O</span><span class="label">TT</span></h1>
    <div class="sub label">控制台</div>
  </div>
  <nav class="nav" id="sidebar-nav">
    <div class="nav-item active" data-page="dashboard" onclick="navigate('dashboard')">
      <span class="ico">&#9632;</span><span class="label">总览</span>
    </div>
    <div class="nav-item" data-page="library" onclick="navigate('library')">
      <span class="ico">&#9776;</span><span class="label">文库</span>
      <span class="badge" id="lib-badge">0</span>
    </div>
    <div class="nav-item" data-page="scripts" onclick="navigate('scripts')">
      <span class="ico">&#9889;</span><span class="label">脚本</span>
      <span class="badge" id="scr-badge">0</span>
    </div>
    <div class="nav-item" data-page="schedules" onclick="navigate('schedules')">
      <span class="ico">&#9716;</span><span class="label">定时</span>
    </div>
    <div class="nav-item" data-page="settings" onclick="navigate('settings')">
      <span class="ico">&#9881;</span><span class="label">设置</span>
    </div>
  </nav>
</aside>

<!-- ═══ 主内容 ═══ -->
<main class="main">

<!-- ── 总览 ── -->
<div class="page active" id="page-dashboard">
  <div class="page-header"><h2>总览</h2><p>OTT 控制台概览</p></div>
  <div class="stats" id="dash-stats"></div>
  <div class="split-wide">
    <div class="card">
      <div class="card-header"><h3>最近活动</h3></div>
      <div id="dash-recent" style="min-height:50px"></div>
    </div>
    <div class="card">
      <div class="card-header"><h3>脚本状态</h3></div>
      <div id="dash-scripts" style="min-height:50px"></div>
    </div>
  </div>
  <div class="card">
    <div class="card-header"><h3>系统</h3><button class="btn btn-ghost btn-sm" onclick="refreshStatus()">刷新</button></div>
    <div id="dash-sysinfo" style="font-size:13px;color:var(--text-secondary)"></div>
  </div>
</div>

<!-- ── 文库 ── -->
<div class="page" id="page-library">
  <div class="page-header"><h2>文库</h2><p>全部历史文本</p></div>
  <div class="toolbar">
    <input type="text" id="lib-search" placeholder="搜索标题、正文..." oninput="renderLibrary()">
    <select id="lib-source" onchange="renderLibrary()"><option value="">全部合集</option></select>
    <select id="lib-cat" onchange="renderLibrary()"><option value="">全部分类</option></select>
    <span id="lib-count" style="font-size:12px;color:var(--text-muted);white-space:nowrap"></span>
    <button class="btn btn-ghost btn-sm" onclick="renderLibrary()">&#8635;</button>
    <button class="btn btn-gold btn-sm" onclick="openLibAddModal()">&#43; 添加</button>
  </div>
  <div id="lib-list" style="display:flex;flex-direction:column;gap:8px"></div>
  <div id="lib-empty" class="empty" style="display:none">
    <div class="ico">&#9744;</div><p>暂无文本。<a href="#" onclick="openLibAddModal();return false">添加一篇</a> 或创建抓取脚本</p>
  </div>
</div>

<!-- ── 脚本 ── -->
<div class="page" id="page-scripts">
  <div class="page-header">
    <h2>脚本</h2>
    <p>管理抓取脚本 — 运行、测试、编辑、创建</p>
  </div>
  <div style="margin-bottom:14px">
    <button class="btn btn-gold" onclick="openNewScript()">&#43; 新建脚本</button>
  </div>
  <div class="card" style="padding:0">
    <div class="table-wrap"><table><thead><tr>
      <th>脚本</th><th>标识</th><th>大小</th><th>最近抓取</th><th></th>
    </tr></thead><tbody id="scr-body"></tbody></table></div>
    <div id="scr-empty" class="empty" style="display:none">
      <div class="ico">&#9744;</div><p>暂无脚本。添加 <code>fetch_xxx.py</code> 到 <code>scripts/</code> 目录，或<a href="#" onclick="openNewScript()">新建一个</a></p>
    </div>
  </div>
</div>

<!-- ── 定时 ── -->
<div class="page" id="page-schedules">
  <div class="page-header"><h2>定时任务</h2><p>为每个脚本配置抓取频率</p></div>
  <div class="card" id="sched-body"></div>
  <div id="sched-empty" class="empty" style="display:none">
    <div class="ico">&#9716;</div><p>暂无脚本，请先创建脚本</p>
  </div>
</div>

<!-- ── 设置 ── -->
<div class="page" id="page-settings">
  <div class="page-header"><h2>设置</h2><p>系统配置和状态信息</p></div>
  <div class="card" style="max-width:500px">
    <div id="settings-body"></div>
    <div style="margin-top:18px;display:flex;gap:10px">
      <button class="btn btn-outline" onclick="refreshAll()">重建索引</button>
      <button class="btn btn-ghost" onclick="refreshStatus();fetchAndRenderSettings()">刷新</button>
    </div>
  </div>
</div>

</main></div>

<!-- ═══ 模态框 ═══ -->

<!-- 详情弹窗 -->
<div class="modal-overlay" id="modal-detail" onclick="if(event.target===this)closeModal('modal-detail')">
  <div class="modal">
    <button class="close-btn" onclick="closeModal('modal-detail')">&#10005;</button>
    <div class="modal-title" id="det-title"></div>
    <div class="modal-meta" id="det-meta"></div>
    <div class="content-box" id="det-content"></div>
    <div class="actions" id="det-actions"></div>
  </div>
</div>

<!-- 脚本弹窗 -->
<div class="modal-overlay" id="modal-script" onclick="if(event.target===this)closeModal('modal-script')">
  <div class="modal wide">
    <button class="close-btn" onclick="closeModal('modal-script')">&#10005;</button>
    <div class="modal-title" id="scr-title" onclick="toggleScriptRename()" style="cursor:pointer" title="点击修改标识"></div>
    <div class="modal-meta" id="scr-meta"></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
      <button class="btn btn-gold btn-sm" id="scr-btn-test" onclick="runScriptTest()">&#9654; 测试</button>
      <button class="btn btn-ghost btn-sm" id="scr-btn-run" onclick="runScriptReal()">&#9654; 抓取</button>
      <button class="btn btn-ghost btn-sm" onclick="toggleScriptSource()" id="scr-btn-source">&#9776; 源码</button>
      <button class="btn btn-ghost btn-sm" onclick="toggleScriptRename()" id="scr-btn-rename">&#9998; 重命名</button>
      <span style="margin-left:auto;display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" id="scr-btn-edit" onclick="toggleScriptEdit()">&#9998; 编辑</button>
      </span>
    </div>
    <div id="scr-output" style="display:none">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:0.4px">输出</div>
      <div class="terminal" id="scr-terminal"></div>
    </div>
    <div id="scr-source-box" style="display:none;margin-top:8px">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:0.4px">源码</div>
      <div class="code-box" id="scr-source-code"></div>
    </div>
    <div id="scr-edit-box" style="display:none;margin-top:8px">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:0.4px">编辑源码</div>
      <textarea id="scr-editor" style="width:100%;min-height:220px;padding:14px;background:#08080a;border:1px solid var(--border);border-radius:var(--radius-sm);color:#98c379;font-family:var(--font-mono);font-size:12px;line-height:1.6;resize:vertical;outline:none"></textarea>
      <div style="margin-top:8px;display:flex;gap:8px">
        <button class="btn btn-gold btn-sm" onclick="saveScriptEdit()">保存</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleScriptEdit()">取消</button>
      </div>
    </div>
    <div id="scr-rename-box" style="display:none;margin-top:8px">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:0.4px">重命名脚本</div>
      <div class="inline-edit">
        <span style="color:var(--text-muted)">fetch_</span>
        <input id="scr-rename-input" placeholder="新键名">
        <span style="color:var(--text-muted)">.py</span>
        <button class="btn btn-gold btn-xs" onclick="confirmRename()">重命名</button>
        <button class="btn btn-ghost btn-xs" onclick="toggleScriptRename()">取消</button>
      </div>
    </div>
    <div id="scr-validation" style="display:none;margin-top:10px">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:0.4px">验证</div>
      <div id="scr-validation-body" style="font-size:13px"></div>
    </div>
  </div>
</div>

<!-- 新建脚本弹窗 -->
<div class="modal-overlay" id="modal-new-script" onclick="if(event.target===this)closeModal('modal-new-script')">
  <div class="modal wide">
    <button class="close-btn" onclick="closeModal('modal-new-script')">&#10005;</button>
    <div class="modal-title">新建脚本</div>
    <div class="modal-meta" style="margin-bottom:14px">基于模板创建新的抓取脚本</div>
    <div class="form-group">
      <label>合集标识 *</label>
      <input id="new-scr-key" placeholder="my_source（字母数字下划线）" oninput="this.value=this.value.replace(/[^a-zA-Z0-9_]/g,'')">
      <div class="hint">将创建 <code>scripts/fetch_{key}.py</code></div>
    </div>
    <div class="form-group">
      <label>脚本源码</label>
      <textarea id="new-scr-editor" rows="16" style="width:100%;min-height:200px;padding:14px;background:#08080a;border:1px solid var(--border);border-radius:var(--radius-sm);color:#98c379;font-family:var(--font-mono);font-size:12px;line-height:1.6;resize:vertical;outline:none"></textarea>
      <div class="hint">编辑模板或粘贴你自己的抓取脚本</div>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-gold" onclick="createNewScript()">创建脚本</button>
      <button class="btn btn-ghost" onclick="fillScriptTemplate()">填充模板</button>
      <button class="btn btn-ghost" onclick="closeModal('modal-new-script')">取消</button>
    </div>
  </div>
</div>

<!-- 添加文本弹窗 -->
<div class="modal-overlay" id="modal-add-entry" onclick="if(event.target===this)closeModal('modal-add-entry')">
  <div class="modal" style="max-width:520px">
    <button class="close-btn" onclick="closeModal('modal-add-entry')">&#10005;</button>
    <div class="modal-title">添加文本</div>
    <div class="modal-meta" style="margin-bottom:14px">手动添加一篇文本到文库</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
      <input id="lib-add-key" placeholder="合集标识（字母数字下划线）" style="padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);outline:none" oninput="this.value=this.value.replace(/[^a-zA-Z0-9_]/g,'')">
      <input id="lib-add-title" placeholder="标题" style="padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);outline:none">
    </div>
    <textarea id="lib-add-content" rows="5" placeholder="粘贴或输入文本内容" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);outline:none;resize:vertical;box-sizing:border-box;font-family:inherit;font-size:13px;margin-bottom:10px"></textarea>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
      <input id="lib-add-cat" placeholder="分类（可选）" style="padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);outline:none">
      <input id="lib-add-tags" placeholder="标签（逗号分隔）" style="padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);outline:none">
    </div>
    <div style="display:flex;gap:10px">
      <button class="btn btn-gold" onclick="libAddEntry()">提交</button>
      <button class="btn btn-ghost" onclick="closeModal('modal-add-entry')">取消</button>
    </div>
  </div>
</div>

<!-- ═══ 消息容器 ═══ -->
<div class="toast-c" id="toast-c"></div>

<script>
/* ════════════════════════════════════════════════════════════
   核心 SPA
   ════════════════════════════════════════════════════════════ */

let state = { status: null, sources: [], scripts: [], categories: [], entries: [] };
let currentScript = null;
let currentDetailKey = null;
function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-'+page).classList.add('active');
  let navItem = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (navItem) navItem.classList.add('active');
  if (page==='dashboard') renderDashboard();
  if (page==='library') fetchAndRenderLibrary();
  if (page==='scripts') fetchAndRenderScripts();
  if (page==='schedules') fetchAndRenderSchedules();
  if (page==='settings') fetchAndRenderSettings();
}

function toast(msg, type='blue') {
  const c = document.getElementById('toast-c');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.innerHTML = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; setTimeout(() => t.remove(), 300); }, 3000);
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  if (id==='modal-script') { currentScript=null; }
  if (id==='modal-new-script') { clearNewScriptForm(); }
}

/* ═══ API 辅助 ═══ */

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'HTTP '+r.status);
  return data;
}

function copyText(t) {
  navigator.clipboard.writeText(t).then(() => toast('已复制', 'green')).catch(() => {});
}

/* ════════════════════════════════════════════════════════════
   总览
   ════════════════════════════════════════════════════════════ */

async function renderDashboard() {
  document.getElementById('dash-stats').innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const [status, sources, recentData] = await Promise.all([
      api('GET', '/api/status'), api('GET', '/api/sources'), api('GET', '/api/entries/recent')
    ]);
    state.status = status;
    state.sources = sources.sources || [];
    document.getElementById('lib-badge').textContent = status.stats.entries;
    renderDashStats(status, sources);
    renderDashRecent(recentData.entries || []);
    fetchAndRenderDashScripts();
    renderDashSysInfo(status);
  } catch(e) {
    document.getElementById('dash-stats').innerHTML = '<div class="empty"><p>加载失败: '+e.message+'</p></div>';
  }
}

function renderDashStats(status, srcData) {
  const srcs = srcData.sources || [];
  const cats = new Set(srcs.map(s=>s.category).filter(Boolean));
  let uptimeStr = '刚刚';
  const u = status.uptime;
  if (u) {
    if (u < 60) uptimeStr = u + '秒';
    else if (u < 3600) uptimeStr = Math.floor(u/60) + '分 ' + (u%60) + '秒';
    else if (u < 86400) uptimeStr = Math.floor(u/3600) + '时 ' + Math.floor((u%3600)/60) + '分';
    else uptimeStr = Math.floor(u/86400) + '天 ' + Math.floor((u%86400)/3600) + '时';
  }
  document.getElementById('dash-stats').innerHTML =
    '<div class="stat gold"><div class="val">'+(status.stats.entries||srcs.length)+'</div><div class="lbl">文本篇数</div></div>' +
    '<div class="stat blue"><div class="val">'+status.stats.scripts+'</div><div class="lbl">抓取脚本</div></div>' +
    '<div class="stat purple"><div class="val">'+cats.size+'</div><div class="lbl">分类数</div></div>' +
    '<div class="stat orange"><div class="val">'+status.stats.active_schedules+'</div><div class="lbl">定时任务</div></div>';
}

function renderDashRecent(entries) {
  const el = document.getElementById('dash-recent');
  if (!entries.length) { el.innerHTML = '<div style="color:var(--text-muted);padding:18px;text-align:center;font-size:13px">暂无活动</div>'; return; }
  const sorted = [...entries].sort((a,b)=>((b.fetched_at||'') > (a.fetched_at||'') ? 1 : -1));
  el.innerHTML = sorted.slice(0,5).map(e =>
    '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">' +
    '<span><span class="dot gold"></span>'+(e.title||e.source_key)+'</span>' +
    '<span style="color:var(--text-muted);font-size:11px">'+(e.fetched_at||'').slice(0,10)+'</span></div>'
  ).join('');
}

async function fetchAndRenderDashScripts() {
  try {
    const d = await api('GET', '/api/scripts');
    state.scripts = d.scripts || [];
    const el = document.getElementById('dash-scripts');
    if (!state.scripts.length) { el.innerHTML = '<div style="color:var(--text-muted);padding:18px;text-align:center;font-size:13px">暂无脚本</div>'; return; }
    el.innerHTML = state.scripts.map(s =>
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">' +
      '<span><span class="dot '+(s.has_content?'green':'gray')+'"></span>'+s.name+'</span>' +
      '<span style="color:var(--text-muted);font-size:11px">'+(s.content_age_human||'从未')+'</span></div>'
    ).join('');
    document.getElementById('scr-badge').textContent = state.scripts.length;
  } catch(e) { document.getElementById('dash-scripts').innerHTML = '<div style="color:var(--text-muted);padding:18px;text-align:center">加载失败</div>'; }
}

function renderDashSysInfo(status) {
  const s = status;
  let uptimeStr = '刚刚';
  if (s.uptime) {
    const u = s.uptime;
    if (u < 60) uptimeStr = u + ' 秒';
    else if (u < 3600) uptimeStr = Math.floor(u/60) + ' 分 ' + (u%60) + ' 秒';
    else if (u < 86400) uptimeStr = Math.floor(u/3600) + ' 时 ' + Math.floor((u%3600)/60) + ' 分';
    else uptimeStr = Math.floor(u/86400) + ' 天 ' + Math.floor((u%86400)/3600) + ' 时';
  }
  document.getElementById('dash-sysinfo').innerHTML =
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">' +
    '<span style="color:var(--text-muted)">运行时长</span><span>'+uptimeStr+'</span>' +
    '<span style="color:var(--text-muted)">启动时间</span><span>'+(s.started_at||'?')+'</span>' +
    '<span style="color:var(--text-muted)">API 版本</span><span>v'+(s.version||2)+'</span>' +
    '<span style="color:var(--text-muted)">数据目录</span><span style="font-family:var(--font-mono);font-size:11px;word-break:break-all">'+(s.data_dir||'?')+'</span></div>';
}

/* ════════════════════════════════════════════════════════════
   文库
   ════════════════════════════════════════════════════════════ */

async function fetchAndRenderLibrary() {
  document.getElementById('lib-list').innerHTML = '<div class="card" style="padding:20px;text-align:center;color:var(--text-muted)"><div class="spinner"></div>加载中...</div>';
  try {
    const data = await api('GET', '/api/entries');
    state.entries = data.entries || [];
    const srcs = [...new Set(state.entries.map(e=>e.source_key))];
    const cats = [...new Set(state.entries.map(e=>e.category).filter(Boolean))];
    const sSel = document.getElementById('lib-source'), sCur = sSel.value;
    sSel.innerHTML = '<option value="">全部合集</option>'+srcs.map(s=>'<option value="'+s+'">'+s+'</option>').join('');
    if (srcs.includes(sCur)) sSel.value = sCur;
    const cSel = document.getElementById('lib-cat'), cCur = cSel.value;
    cSel.innerHTML = '<option value="">全部分类</option>'+cats.map(c=>'<option value="'+c+'">'+c+'</option>').join('');
    if (cats.includes(cCur)) cSel.value = cCur;
    renderLibrary();
    document.getElementById('lib-badge').textContent = state.entries.length;
    document.getElementById('lib-count').textContent = '共 '+state.entries.length+' 篇';
  } catch(e) {
    document.getElementById('lib-list').innerHTML = '<div class="card" style="padding:20px;text-align:center;color:var(--red)">加载失败: '+e.message+'</div>';
  }
}

function renderLibrary() {
  const list = document.getElementById('lib-list');
  const q = (document.getElementById('lib-search').value||'').toLowerCase();
  const src = document.getElementById('lib-source').value;
  const cat = document.getElementById('lib-cat').value;
  let filtered = state.entries;
  if (q) filtered = filtered.filter(e => (e.title||'').toLowerCase().includes(q)||(e.content||'').toLowerCase().includes(q));
  if (src) filtered = filtered.filter(e => e.source_key === src);
  if (cat) filtered = filtered.filter(e => e.category === cat);
  const empty = document.getElementById('lib-empty');
  if (!filtered.length) { list.innerHTML=''; empty.style.display='block'; return; }
  empty.style.display='none';
  list.innerHTML = filtered.map((e,i) =>
    '<div class="card entry-card" onclick="openDetail('+i+')" style="cursor:pointer;padding:14px 18px">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
        '<span style="font-size:11px;font-weight:600;color:var(--gold);background:var(--gold-dim);padding:2px 8px;border-radius:4px">'+escHtml(e.source_key)+'</span>' +
        (e.category?'<span class="tag">'+escHtml(e.category)+'</span>':'') +
        '<span style="font-size:11px;color:var(--text-muted);margin-left:auto">'+escHtml((e.fetched_at||'').slice(0,10))+'</span>' +
      '</div>' +
      '<div style="font-weight:600;font-size:14px;margin-bottom:4px">'+escHtml(e.title||'无标题')+'</div>' +
      '<div style="font-size:12px;color:var(--text-secondary);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">'+escHtml(e.preview||'')+'</div>' +
      (e.tags&&e.tags.length?'<div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap">'+e.tags.map(t=>'<span style="font-size:10px;color:var(--text-muted);background:var(--bg-elevated);padding:1px 6px;border-radius:3px">'+escHtml(t)+'</span>').join('')+'</div>':'') +
    '</div>'
  ).join('');
}

function openLibAddModal() {
  document.getElementById('lib-add-key').value = '';
  document.getElementById('lib-add-title').value = '';
  document.getElementById('lib-add-content').value = '';
  document.getElementById('lib-add-cat').value = '';
  document.getElementById('lib-add-tags').value = '';
  document.getElementById('modal-add-entry').classList.add('open');
  setTimeout(() => document.getElementById('lib-add-key').focus(), 100);
}

async function libAddEntry() {
  const key = document.getElementById('lib-add-key').value.trim();
  const title = document.getElementById('lib-add-title').value.trim();
  const content = document.getElementById('lib-add-content').value;
  if (!key || !content) { toast('合集标识和内容为必填', 'red'); return; }
  if (!/^[a-zA-Z0-9_]+$/.test(key)) { toast('合集标识只能含字母数字下划线', 'red'); return; }
  try {
    const r = await api('POST', '/api/entries', {
      source_key: key, title: title || key,
      content: content,
      category: document.getElementById('lib-add-cat').value.trim(),
      tags: document.getElementById('lib-add-tags').value.trim(),
    });
    closeModal('modal-add-entry');
    fetchAndRenderLibrary();
  } catch(e) { toast('添加失败: '+e.message, 'red'); }
}

async function deleteEntry(idx) {
  const e = state.entries[idx];
  if (!e || !confirm('确认删除 "'+(e.title||e.source_key)+'" ？')) return;
  try {
    await api('DELETE', '/api/entries/'+e.source_key, {entry_id: e.id});
    closeModal('modal-detail');
    fetchAndRenderLibrary();
  } catch(e) { alert('删除失败: '+e.message); }
}

function navigateToScript(key) {
  navigate('scripts');
  setTimeout(() => {
    const rows = document.querySelectorAll('#scr-body tr');
    for (let r of rows) {
      if (r.textContent.includes(key)) {
        r.style.background = 'var(--gold-dim)';
        r.scrollIntoView({behavior:'smooth',block:'center'});
        setTimeout(() => r.style.background='', 2000);
        break;
      }
    }
  }, 300);
}

/* ════════════════════════════════════════════════════════════
   详情
   ════════════════════════════════════════════════════════════ */

function openDetail(idx) {
  const e = state.entries[idx];
  if (!e) return;
  const ov = document.getElementById('modal-detail');
  ov.classList.add('open');
  document.getElementById('det-title').textContent = e.title || e.source_key;
  let meta = [];
  meta.push('合集: '+e.source_key);
  if (e.category) meta.push(e.category);
  if (e.fetched_at) meta.push(e.fetched_at.slice(0,10));
  meta.push(e.charCount + ' 字');
  document.getElementById('det-meta').innerHTML = meta.join(' &middot; ');
  document.getElementById('det-content').textContent = e.content || '(空)';
  document.getElementById('det-actions').innerHTML =
    '<button class="btn btn-outline btn-sm" onclick="copyText(document.getElementById(\'det-content\').textContent)">复制文本</button>' +
    '<button class="btn btn-ghost btn-sm" onclick="deleteEntry('+idx+')" style="color:var(--red)">删除</button>';
}

/* ════════════════════════════════════════════════════════════
   脚本列表
   ════════════════════════════════════════════════════════════ */

async function fetchAndRenderScripts() {
  document.getElementById('scr-body').innerHTML = '<tr><td colspan="5"><div class="loading"><div class="spinner"></div></div></td></tr>';
  try {
    const d = await api('GET', '/api/scripts');
    state.scripts = d.scripts || [];
    renderScripts();
    document.getElementById('scr-badge').textContent = state.scripts.length;
  } catch(e) {
    document.getElementById('scr-body').innerHTML = '<tr><td colspan="5"><div class="empty"><p>加载失败: '+e.message+'</p></div></td></tr>';
  }
}

function renderScripts() {
  const body = document.getElementById('scr-body');
  const empty = document.getElementById('scr-empty');
  if (!state.scripts.length) { body.innerHTML=''; empty.style.display='block'; return; }
  empty.style.display='none';
  body.innerHTML = state.scripts.map(s =>
    '<tr><td><span class="dot '+(s.has_content?'green':'gray')+'"></span><strong>'+s.name+'</strong></td>' +
    '<td style="font-family:var(--font-mono);font-size:12px;color:var(--text-muted)">'+s.source_key+'</td>' +
    '<td style="font-size:12px;color:var(--text-secondary)">'+(s.size/1024).toFixed(1)+' KB</td>' +
    '<td style="font-size:12px;color:var(--text-muted)">'+(s.content_age_human||'从未')+'</td>' +
    '<td style="text-align:right;white-space:nowrap">' +
    '<button class="btn btn-ghost btn-xs" onclick="openScript(\''+s.source_key+'\')">打开</button>' +
    ' <button class="btn btn-ghost btn-xs" onclick="quickTest(\''+s.source_key+'\')">测试</button>' +
    ' <button class="btn btn-ghost btn-xs" onclick="quickRun(\''+s.source_key+'\')">抓取</button></td></tr>'
  ).join('');
}

/* ════════════════════════════════════════════════════════════
   脚本弹窗
   ════════════════════════════════════════════════════════════ */

async function openScript(key) {
  currentScript = key;
  document.getElementById('scr-title').textContent = key;
  document.getElementById('scr-meta').innerHTML = '<span>fetch_'+key+'.py</span>';
  document.getElementById('scr-output').style.display = 'none';
  document.getElementById('scr-source-box').style.display = 'none';
  document.getElementById('scr-edit-box').style.display = 'none';
  document.getElementById('scr-rename-box').style.display = 'none';
  document.getElementById('scr-validation').style.display = 'none';
  document.getElementById('modal-script').classList.add('open');
  try {
    const d = await api('GET', '/api/scripts/'+key);
    document.getElementById('scr-source-code').textContent = d.source||'(无法读取)';
    document.getElementById('scr-editor').value = d.source||'';
    document.getElementById('scr-rename-input').value = key;
  } catch(e) {}
}

function toggleScriptSource() {
  const box = document.getElementById('scr-source-box');
  box.style.display = box.style.display==='none'?'block':'none';
}

function toggleScriptEdit() {
  const box = document.getElementById('scr-edit-box');
  const isOpen = box.style.display !== 'none';
  box.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) {
    document.getElementById('scr-editor').value = document.getElementById('scr-source-code').textContent;
  }
}

function toggleScriptRename() {
  const box = document.getElementById('scr-rename-box');
  box.style.display = box.style.display==='none'?'block':'none';
}

async function runScriptTest() {
  const key = currentScript; if (!key) return;
  const term = document.getElementById('scr-terminal');
  const out = document.getElementById('scr-output');
  const val = document.getElementById('scr-validation');
  const valBody = document.getElementById('scr-validation-body');
  out.style.display='block'; term.innerHTML='<span class="info">运行测试...</span>';
  val.style.display='none';
  document.getElementById('scr-source-box').style.display='none';
  document.getElementById('scr-edit-box').style.display='none';
  try {
    const r = await api('POST', '/api/scripts/'+key+'/test');
    let html = '';
    if (r.stdout) html += '<span class="info">标准输出:</span>\n'+escHtml(r.stdout)+'\n';
    if (r.stderr) html += '\n<span class="err">错误输出:</span>\n'+escHtml(r.stderr)+'\n';
    html += '\n<span class="info">耗时: '+r.duration+'秒 · 退出码: '+r.exit_code+'</span>';
    term.innerHTML = html;
    if (r.validation) {
      val.style.display='block';
      if (r.validation.valid) valBody.innerHTML = '<span style="color:var(--green)">&#10003; 有效的 OTT 输出</span> · '+r.validation.charCount+' 字' + (r.preview?'<div style="margin-top:8px;padding:10px;background:var(--bg-code);border-radius:6px;font-size:12px;color:var(--text-secondary)">'+escHtml(r.preview)+'</div>':'');
      else valBody.innerHTML = '<span style="color:var(--red)">&#10007; '+escHtml(r.validation.error)+'</span>';
    }
    if (r.ok) toast('测试通过', 'green'); else toast('测试失败', 'red');
  } catch(e) { term.innerHTML = '<span class="err">错误: '+escHtml(e.message)+'</span>'; toast('测试出错', 'red'); }
}

async function runScriptReal() {
  const key = currentScript; if (!key) return;
  const term = document.getElementById('scr-terminal');
  const out = document.getElementById('scr-output');
  out.style.display='block'; term.innerHTML='<span class="info">正在抓取...</span>';
  try {
    const r = await api('POST', '/api/scripts/'+key+'/run');
    if (r.ok) { term.innerHTML = '<span class="info">&#10003; 抓取成功</span>\n'+(r.output?escHtml(r.output):''); toast('抓取完成', 'green'); fetchAndRenderScripts(); fetchAndRenderLibrary(); }
    else { term.innerHTML = '<span class="err">&#10007; 失败: '+escHtml(r.error)+'</span>'; toast('抓取失败', 'red'); }
  } catch(e) { term.innerHTML = '<span class="err">错误: '+escHtml(e.message)+'</span>'; }
}

async function saveScriptEdit() {
  const key = currentScript;
  const source = document.getElementById('scr-editor').value;
  if (!key || !source.trim()) return toast('源码不能为空', 'red');
  try {
    await api('POST', '/api/scripts/'+key+'/save', { source_code: source });
    toast('脚本已保存', 'green');
    document.getElementById('scr-source-code').textContent = source;
    document.getElementById('scr-edit-box').style.display = 'none';
  } catch(e) { toast('保存失败: '+e.message, 'red'); }
}

async function confirmRename() {
  const oldKey = currentScript;
  const newKey = document.getElementById('scr-rename-input').value.trim();
  if (!newKey) return toast('新键名不能为空', 'red');
  if (!/^[a-zA-Z0-9_]+$/.test(newKey)) return toast('只能使用字母数字和下划线', 'red');
  try {
    await api('POST', '/api/scripts/'+oldKey+'/rename', { new_key: newKey });
    toast('已重命名为 fetch_'+newKey+'.py', 'green');
    closeModal('modal-script');
    fetchAndRenderScripts();
    fetchAndRenderLibrary();
  } catch(e) { toast('重命名失败: '+e.message, 'red'); }
}

async function quickTest(key) {
  currentScript = key;
  document.getElementById('scr-title').textContent = key;
  document.getElementById('scr-meta').innerHTML = '<span>fetch_'+key+'.py</span>';
  document.getElementById('scr-output').style.display='none';
  document.getElementById('scr-source-box').style.display='none';
  document.getElementById('scr-edit-box').style.display='none';
  document.getElementById('scr-rename-box').style.display='none';
  document.getElementById('scr-validation').style.display='none';
  document.getElementById('modal-script').classList.add('open');
  try { const d = await api('GET', '/api/scripts/'+key); document.getElementById('scr-source-code').textContent = d.source||''; document.getElementById('scr-editor').value = d.source||''; document.getElementById('scr-rename-input').value = key; } catch(e) {}
  setTimeout(() => runScriptTest(), 400);
}

async function quickRun(key) {
  currentScript = key;
  document.getElementById('scr-title').textContent = key;
  document.getElementById('scr-meta').innerHTML = '<span>fetch_'+key+'.py</span>';
  document.getElementById('scr-output').style.display='none';
  document.getElementById('scr-source-box').style.display='none';
  document.getElementById('scr-edit-box').style.display='none';
  document.getElementById('scr-rename-box').style.display='none';
  document.getElementById('scr-validation').style.display='none';
  document.getElementById('modal-script').classList.add('open');
  try { const d = await api('GET', '/api/scripts/'+key); document.getElementById('scr-source-code').textContent = d.source||''; document.getElementById('scr-editor').value = d.source||''; document.getElementById('scr-rename-input').value = key; } catch(e) {}
  setTimeout(() => runScriptReal(), 400);
}

/* ════════════════════════════════════════════════════════════
   新建脚本
   ════════════════════════════════════════════════════════════ */

function openNewScript() {
  document.getElementById('new-scr-key').value = '';
  document.getElementById('new-scr-key').disabled = false;
  document.getElementById('new-scr-editor').value = '';
  document.getElementById('modal-new-script').classList.add('open');
  fillScriptTemplate();
}

function fillScriptTemplate() {
  const key = document.getElementById('new-scr-key').value || 'my_source';
  document.getElementById('new-scr-editor').value = `#!/usr/bin/env python3
"""fetch_${key}.py — {{description}}。

免责声明: 请确保抓取行为符合目标网站 robots.txt 及当地版权法，使用者自负全责。
"""

import json
import time
from pathlib import Path
import httpx

SOURCE_KEY = "${key}"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "content" / f"{SOURCE_KEY}.json"


def _load_data():
    """读取已有数据，兼容旧格式自动迁移。"""
    if not OUTPUT_PATH.exists():
        return {"source_key": SOURCE_KEY, "entries": []}
    d = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    if "entries" not in d and "content" in d:
        d["entries"] = [{
            "title": d.pop("title", ""),
            "content": d.pop("content", ""),
            "metadata": d.pop("metadata", {}),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
        }]
    d.setdefault("entries", [])
    return d


def _append_entry(d, entry):
    entry["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())
    content = entry.get("content", "")
    for i, e in enumerate(d["entries"]):
        if e.get("content") == content:
            d["entries"][i] = entry
            d["title"] = entry["title"]
            d["content"] = content
            d["metadata"] = entry.get("metadata", {})
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = OUTPUT_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(OUTPUT_PATH)
            print(f"[{SOURCE_KEY}] 已更新（重复内容）— 共 {len(d['entries'])} 篇")
            return
    d["entries"].append(entry)
    d["title"] = entry["title"]
    d["content"] = content
    d["metadata"] = entry.get("metadata", {})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    print(f"[{SOURCE_KEY}] 已追加 — 共 {len(d['entries'])} 篇")


def fetch():
    with httpx.Client(timeout=20, trust_env=False) as client:
        resp = client.get("https://example.com/api/text")
        resp.raise_for_status()
        return resp.json()


def main():
    data = fetch()
    entry = {
        "title": data.get("title", SOURCE_KEY),
        "content": data["text"],
        "metadata": {
            "description": "你的文本描述",
            "category": "static",
            "tags": ["标签1", "标签2"],
        }
    }
    d = _load_data()
    _append_entry(d, entry)


if __name__ == "__main__":
    main()
`;
}

async function createNewScript() {
  const key = document.getElementById('new-scr-key').value.trim();
  const source = document.getElementById('new-scr-editor').value;
  if (!key) return toast('合集标识不能为空', 'red');
  if (!/^[a-zA-Z0-9_]+$/.test(key)) return toast('只能使用字母数字和下划线', 'red');
  if (!source.trim()) return toast('源码不能为空', 'red');
  try {
    await api('POST', '/api/scripts', { source_key: key, source_code: source });
    toast('脚本 fetch_'+key+'.py 已创建', 'green');
    closeModal('modal-new-script');
    fetchAndRenderScripts();
  } catch(e) { toast('创建失败: '+e.message, 'red'); }
}

function clearNewScriptForm() {
  document.getElementById('new-scr-key').value = '';
  document.getElementById('new-scr-editor').value = '';
}

/* ════════════════════════════════════════════════════════════
   定时任务
   ════════════════════════════════════════════════════════════ */

async function fetchAndRenderSchedules() {
  const body = document.getElementById('sched-body');
  body.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const scr = await api('GET', '/api/scripts');
    const scripts = scr.scripts || [];
    if (!scripts.length) { document.getElementById('sched-empty').style.display='block'; body.innerHTML=''; return; }
    document.getElementById('sched-empty').style.display='none';
    const scheds = await Promise.all(scripts.map(s => api('GET', '/api/scripts/'+s.source_key+'/cron').catch(()=>({}))));
    state.schedules = {};
    scripts.forEach((s,i) => { state.schedules[s.source_key] = scheds[i]||{}; });
    renderSchedules();
  } catch(e) { body.innerHTML = '<div class="empty"><p>加载失败: '+e.message+'</p></div>'; }
}

function renderSchedules() {
  document.getElementById('sched-body').innerHTML = Object.entries(state.schedules).map(([key, sched]) => {
    const on = sched.enabled||false;
    const interval = sched.interval||'manual';
    const last = sched.last_run ? new Date(sched.last_run).toLocaleString('zh-CN') : '从未';
    return '<div class="cron-row"><span class="name">'+key+'</span>' +
      '<select onchange="updateSchedule(\''+key+'\')" id="sched-sel-'+key+'">' +
      '<option value="manual"'+(interval==='manual'?' selected':'')+'>手动</option>' +
      '<option value="hourly"'+(interval==='hourly'?' selected':'')+'>每小时</option>' +
      '<option value="daily"'+(interval==='daily'?' selected':'')+'>每天</option>' +
      '<option value="weekly"'+(interval==='weekly'?' selected':'')+'>每周</option></select>' +
      '<div class="toggle '+(on?'on':'')+'" onclick="toggleSchedule(\''+key+'\')" id="sched-tog-'+key+'"></div>' +
      '<span class="info">上次: '+last+'</span></div>';
  }).join('');
}

async function updateSchedule(key) {
  const interval = document.getElementById('sched-sel-'+key).value;
  try { await api('POST', '/api/scripts/'+key+'/cron', { interval, enabled: interval!=='manual' }); toast('定时已更新: '+key, 'green'); fetchAndRenderSchedules(); }
  catch(e) { toast('更新失败: '+e.message, 'red'); }
}

async function toggleSchedule(key) {
  const tog = document.getElementById('sched-tog-'+key);
  const on = !tog.classList.contains('on');
  const sel = document.getElementById('sched-sel-'+key);
  const interval = on ? (sel.value==='manual'?'daily':sel.value) : 'manual';
  try { await api('POST', '/api/scripts/'+key+'/cron', { interval, enabled: on }); toast(on?'定时已开启':'定时已关闭', 'green'); fetchAndRenderSchedules(); }
  catch(e) { toast('操作失败: '+e.message, 'red'); }
}

/* ════════════════════════════════════════════════════════════
    设置
   ════════════════════════════════════════════════════════════ */

async function fetchAndRenderSettings() {
  try {
    const s = await api('GET', '/api/status');
    let uptimeStr = '刚刚';
    if (s.uptime) {
      const u = s.uptime;
      if (u < 60) uptimeStr = u + ' 秒';
      else if (u < 3600) uptimeStr = Math.floor(u/60) + ' 分 ' + (u%60) + ' 秒';
      else if (u < 86400) uptimeStr = Math.floor(u/3600) + ' 时 ' + Math.floor((u%3600)/60) + ' 分';
      else uptimeStr = Math.floor(u/86400) + ' 天 ' + Math.floor((u%86400)/3600) + ' 时';
    }
    document.getElementById('settings-body').innerHTML =
      '<div style="margin-bottom:14px"><div style="font-size:12px;color:var(--text-muted)">API 版本</div><div style="font-weight:600">v'+s.version+'</div></div>' +
      '<div style="margin-bottom:14px"><div style="font-size:12px;color:var(--text-muted)">运行时长</div><div style="font-weight:600">'+uptimeStr+'</div></div>' +
      '<div style="margin-bottom:14px"><div style="font-size:12px;color:var(--text-muted)">启动时间</div><div>'+(s.started_at||'?')+'</div></div>' +
      '<div style="margin-bottom:14px"><div style="font-size:12px;color:var(--text-muted)">数据目录</div><div style="font-family:var(--font-mono);font-size:12px;word-break:break-all">'+(s.data_dir||'?')+'</div></div>' +
      '<div style="margin-bottom:14px"><div style="font-size:12px;color:var(--text-muted)">文章 · 脚本 · 定时任务</div><div>'+s.stats.entries+' · '+s.stats.scripts+' · '+s.stats.active_schedules+'</div></div>';
  } catch(e) { document.getElementById('settings-body').innerHTML = '<div style="color:var(--red)">加载失败: '+e.message+'</div>'; }
}

/* ════════════════════════════════════════════════════════════
   删除 / 刷新 / 工具
   ════════════════════════════════════════════════════════════ */

async function deleteSource(key) {
  if (!confirm('确定删除「'+key+'」？')) return;
  try { await api('DELETE', '/api/sources/'+key); toast('已删除: '+key, 'green'); fetchAndRenderLibrary(); }
  catch(e) { toast('删除失败: '+e.message, 'red'); }
}

async function refreshStatus() {
  try { state.status = await api('GET', '/api/status'); renderDashSysInfo(state.status); toast('已刷新', 'green'); }
  catch(e) { toast('刷新失败', 'red'); }
}

async function refreshAll() {
  try { await api('POST', '/api/refresh'); toast('索引已重建', 'green'); renderDashboard(); }
  catch(e) { toast('重建失败: '+e.message, 'red'); }
}

function escHtml(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

/* ════════════════════════════════════════════════════════════
   初始化
   ════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
  renderDashboard();
  fetchAndRenderSettings();
});
</script>
</body>
</html>'''


# ── 旧版入口（兼容） ──────────────────────────────────────
# 新 server.py 通过 start_server() 启动，签名不变。
