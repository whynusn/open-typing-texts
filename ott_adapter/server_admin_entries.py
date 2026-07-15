import json
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from .server_http import err as _err, json_body as _json_body, json_resp as _json_resp
from .server_state import (
    SOURCE_KEY_RE,
    get_write_lock as _get_write_lock,
    read_index as _read_index,
    rebuild_and_invalidate as _rebuild_and_invalidate,
    update_last_run as _update_last_run,
)


class AdminEntryRoutes:
    data_dir: Path
    path: str

    def _api_entries_recent(self):
        index = _read_index(self.data_dir)
        all_recent = []
        for s in index.get("sources", []):
            all_recent.extend(s.get("recent_entries", []))
        all_recent.sort(key=lambda x: x.get("fetched_at", "") or "", reverse=True)
        _json_resp(self, {"entries": all_recent[:5]})

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
                entries = [
                    {
                        "title": d.get("title", ""),
                        "content": d["content"],
                        "metadata": d.get("metadata", {}),
                        "fetched_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S+08:00", time.localtime(f.stat().st_mtime)
                        ),
                    }
                ]
            for e in entries:
                meta = e.get("metadata", {})
                all_entries.append(
                    {
                        "id": f"{sk}-{e.get('fetched_at', '')}",
                        "source_key": sk,
                        "source_label": label,
                        "title": e.get("title", ""),
                        "content": e.get("content", ""),
                        "preview": (e.get("content", "")[:100])
                        .replace("\n", " ")
                        .strip(),
                        "category": meta.get("category", ""),
                        "tags": meta.get("tags", []),
                        "fetched_at": e.get("fetched_at", ""),
                        "charCount": len(e.get("content", "")),
                    }
                )
        all_entries.sort(key=lambda x: x["fetched_at"], reverse=True)
        total = len(all_entries)
        # 分页（安全阀，默认返回全部）
        qs = dict(
            p.split("=")
            for p in urlparse(unquote(self.path)).query.split("&")
            if "=" in p
        )
        page = max(1, int(qs.get("page", 1)))
        limit = min(500, max(1, int(qs.get("limit", total or 500))))
        start = (page - 1) * limit
        paged = all_entries[start : start + limit]
        _json_resp(
            self,
            {
                "entries": paged,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if limit else 1,
            },
        )

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
        with _get_write_lock(source_key):
            if fpath.exists():
                try:
                    d = json.loads(fpath.read_text(encoding="utf-8"))
                except Exception:
                    d = {}
                entries = d.get("entries", [])
                if not entries and d.get("content"):
                    entries = [
                        {
                            "title": d.get("title", ""),
                            "content": d.get("content", ""),
                            "metadata": d.get("metadata", {}),
                            "fetched_at": now_iso,
                        }
                    ]
                dup = False
                for i, e in enumerate(entries):
                    if e.get("content") == content:
                        entries[i] = {
                            "title": title,
                            "content": content,
                            "metadata": {
                                "category": body.get("category", ""),
                                "tags": [
                                    t.strip()
                                    for t in body.get("tags", "").split(",")
                                    if t.strip()
                                ],
                                "description": body.get("description", ""),
                            },
                            "fetched_at": now_iso,
                        }
                        dup = True
                        break
                if not dup:
                    entries.append(
                        {
                            "title": title,
                            "content": content,
                            "metadata": {
                                "category": body.get("category", ""),
                                "tags": [
                                    t.strip()
                                    for t in body.get("tags", "").split(",")
                                    if t.strip()
                                ],
                                "description": body.get("description", ""),
                            },
                            "fetched_at": now_iso,
                        }
                    )
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
                        "tags": [
                            t.strip()
                            for t in body.get("tags", "").split(",")
                            if t.strip()
                        ],
                        "description": body.get("description", ""),
                    },
                    "entries": [
                        {
                            "title": title,
                            "content": content,
                            "metadata": {
                                "category": body.get("category", ""),
                                "tags": [
                                    t.strip()
                                    for t in body.get("tags", "").split(",")
                                    if t.strip()
                                ],
                                "description": body.get("description", ""),
                            },
                            "fetched_at": now_iso,
                        }
                    ],
                }
            tmp = fpath.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(fpath)
        _rebuild_and_invalidate(self.data_dir)
        _update_last_run(self.data_dir, source_key)
        _json_resp(
            self, {"ok": True, "source_key": source_key, "fetched_at": now_iso}, 201
        )

    def _api_entry_delete(self, source_key):
        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")
        content_dir = self.data_dir / "content"
        fpath = content_dir / f"{source_key}.json"
        if not fpath.exists():
            return _err(self, f"合集 '{source_key}' 不存在", 404)
        delete_all = body.get("delete_all", False)
        entry_id = body.get("entry_id")
        with _get_write_lock(source_key):
            d = json.loads(fpath.read_text(encoding="utf-8"))
            entries = d.get("entries", [])
            if delete_all or (not entry_id and not entries):
                d["entries"] = []
                d["content"] = ""
            elif entry_id and entries:
                idx = None
                prefix = f"{source_key}-"
                eid = entry_id
                if eid.startswith(prefix):
                    eid = eid[len(prefix) :]
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
            tmp = fpath.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(fpath)
        _rebuild_and_invalidate(self.data_dir)
        _update_last_run(self.data_dir, source_key)
        entries_left = len(d.get("entries", []))
        _json_resp(self, {"ok": True, "entries_left": entries_left})

    # ── API: 重建索引 ─────────────────────────────────────
