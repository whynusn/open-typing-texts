import json
import time
from pathlib import Path

from . import __version__
from .server_http import err as _err, json_body as _json_body, json_resp as _json_resp
from .server_state import (
    SOURCE_KEY_RE,
    get_schedules as _get_schedules,
    get_write_lock as _get_write_lock,
    read_index as _read_index,
    rebuild_and_invalidate as _rebuild_and_invalidate,
)


class AdminSourceRoutes:
    data_dir: Path
    _start_time: float

    def _api_status(self):
        dd = self.data_dir
        sources = _read_index(dd).get("sources", [])
        scripts_dir = dd / "scripts"
        scripts = (
            sorted(s.name for s in scripts_dir.glob("fetch_*.py"))
            if scripts_dir.exists()
            else []
        )
        script_keys = {s.removeprefix("fetch_").removesuffix(".py") for s in scripts}
        schedules = _get_schedules(dd)
        n_enabled = sum(
            1
            for name, s in schedules.get("schedules", {}).items()
            if name in script_keys and s.get("enabled")
        )
        now = time.time()

        _json_resp(
            self,
            {
                "version": 2,
                "admin_api_version": "1.0",
                "adapter_version": __version__,
                "ott_core_version": "1.0",
                "uptime": int(now - self._start_time),
                "started_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.gmtime(self._start_time + 8 * 3600)
                )
                + "+08:00",
                "now_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "stats": {
                    "sources": len(sources),
                    "scripts": len(scripts),
                    "active_schedules": n_enabled,
                    "entries": sum(s.get("entries_count", 0) for s in sources),
                },
                "data_dir": str(dd.resolve()),
            },
        )

    # ── API: 文本源列表 ──────────────────────────────────

    def _api_list_sources(self):
        index = _read_index(self.data_dir)
        sources = index.get("sources", [])

        # 预览从索引取，不再读每个 content 文件
        for s in sources:
            s["_hasContent"] = bool(s.get("entry_preview") or s.get("title_preview"))
            s["_title"] = s.get("title_preview", "")
            s["_preview"] = s.get("entry_preview", "")
            # 检查对应脚本是否存在（轻量 stat，不读文件内容）
            script = self.data_dir / "scripts" / f"fetch_{s['source_key']}.py"
            s["_hasScript"] = script.exists()

        _json_resp(
            self,
            {
                "version": index.get("version", 1),
                "updated_at": index.get("updated_at", ""),
                "sources": sources,
            },
        )

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
        with _get_write_lock(source_key):
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(path)

        # 重建索引
        _rebuild_and_invalidate(dd)

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
        _rebuild_and_invalidate(dd)

        _json_resp(self, {"ok": True, "source_key": key})

    # ── API: 脚本列表 ─────────────────────────────────────

    def _api_refresh(self):
        try:
            idx = _rebuild_and_invalidate(self.data_dir)
            _json_resp(
                self,
                {
                    "ok": True,
                    "sources": len(idx.get("sources", [])),
                },
            )
        except Exception as e:
            _err(self, f"重建索引失败: {e}", 500)

    # ── Web UI 前端 ──────────────────────────────────────
