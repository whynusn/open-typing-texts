from pathlib import Path
from urllib.parse import parse_qs

from . import __version__
from .ott_core import (
    DEFAULT_SEGMENT_SIZE,
    entries_from_content_file,
    entry_detail as core_entry_detail,
    entry_summary as core_entry_summary,
    sha256_text,
)
from .server_http import json_resp as _json_resp, ott_err as _ott_err
from .server_state import SOURCE_KEY_RE, read_index as _read_index


def _sha256_text(text: str) -> str:
    return sha256_text(text)


def _entries_from_content_file(path: Path) -> list[dict]:
    return entries_from_content_file(path, include_content=True)


def _all_ott_entries(data_dir: Path) -> list[dict]:
    content_dir = data_dir / "content"
    entries: list[dict] = []
    if content_dir.exists():
        for path in sorted(content_dir.glob("*.json"), reverse=True):
            entries.extend(_entries_from_content_file(path))
    entries.sort(key=lambda x: x.get("fetched_at", "") or "", reverse=True)
    return entries


def _entry_summary(entry: dict) -> dict:
    return core_entry_summary(entry)


def _all_ott_entry_summaries(data_dir: Path) -> list[dict]:
    index = _read_index(data_dir)
    entries: list[dict] = []
    for source in index.get("sources", []):
        if isinstance(source, dict) and isinstance(source.get("ott_entries"), list):
            entries.extend(
                entry for entry in source["ott_entries"] if isinstance(entry, dict)
            )
    if not entries:
        entries = [_entry_summary(entry) for entry in _all_ott_entries(data_dir)]
    entries.sort(
        key=lambda x: x.get("fetched_at", "") or x.get("updated_at", ""), reverse=True
    )
    return entries


def _find_ott_entry(data_dir: Path, entry_id: str) -> dict | None:
    for entry in _all_ott_entries(data_dir):
        if entry.get("entry_id") == entry_id:
            return entry
    return None


def _entry_detail(entry: dict, include_content: bool = True) -> dict:
    return core_entry_detail(entry, include_content=include_content)


class OttReadOnlyRoutes:
    data_dir: Path

    def _ott_capabilities(self):
        _json_resp(
            self,
            {
                "protocol": "ott",
                "version": "1.0",
                "profiles": ["service"],
                "adapter_version": __version__,
                "features": {
                    "entry_summary": True,
                    "inline_content": True,
                    "segmented_content": True,
                    "search": True,
                    "static_fallback": False,
                },
            },
        )

    def _ott_sources(self):
        index = _read_index(self.data_dir)
        sources = []
        for src in index.get("sources", []):
            if not isinstance(src, dict) or not src.get("source_key"):
                continue
            tags = []
            category = src.get("category")
            if category:
                tags.append(str(category))
            sources.append(
                {
                    "source_key": str(src.get("source_key", "")),
                    "label": str(src.get("label") or src.get("source_key") or ""),
                    "description": str(src.get("description", "") or ""),
                    "tags": tags,
                    "rights_summary": "user-provided",
                    "category": str(category or ""),
                    "entry_count": int(src.get("entries_count", 0) or 0),
                    "char_count": int(src.get("charCount", 0) or 0),
                    "updated_at": str(index.get("updated_at", "") or ""),
                }
            )
        _json_resp(self, {"sources": sources, "total": len(sources)})

    def _ott_entries(self, parsed):
        qs = parse_qs(parsed.query)
        source_key = (qs.get("source_key", [""])[0] or "").strip()
        query = (qs.get("q", [""])[0] or "").strip().lower()
        if source_key and not SOURCE_KEY_RE.match(source_key):
            return _ott_err(
                self, "invalid_source_key", "source_key 只能含字母数字下划线"
            )
        try:
            page = max(1, int(qs.get("page", ["1"])[0] or "1"))
        except ValueError:
            return _ott_err(self, "invalid_page", "page 必须是正整数")
        try:
            limit = min(200, max(1, int(qs.get("limit", ["40"])[0] or "40")))
        except ValueError:
            return _ott_err(self, "invalid_limit", "limit 必须是正整数")

        entries = _all_ott_entry_summaries(self.data_dir)
        if source_key:
            entries = [e for e in entries if e.get("source_key") == source_key]
        if query:
            entries = [
                e
                for e in entries
                if query in (e.get("title", "") + " " + e.get("preview", "")).lower()
            ]

        total = len(entries)
        start = (page - 1) * limit
        paged = entries[start : start + limit]
        pages = (total + limit - 1) // limit if limit else 1
        _json_resp(
            self,
            {
                "entries": [_entry_summary(e) for e in paged],
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages,
            },
        )

    def _ott_entry_detail(self, entry_id, parsed):
        include_content = (
            parse_qs(parsed.query).get("include_content", ["true"])[0].lower()
            != "false"
        )
        entry = _find_ott_entry(self.data_dir, entry_id)
        if entry is None:
            return _ott_err(
                self, "entry_not_found", f"entry not found: {entry_id}", 404
            )
        _json_resp(self, _entry_detail(entry, include_content=include_content))

    def _ott_segment(self, entry_id, revision_id, index):
        entry = _find_ott_entry(self.data_dir, entry_id)
        if entry is None:
            return _ott_err(
                self, "entry_not_found", f"entry not found: {entry_id}", 404
            )
        if entry.get("current_revision_id") != revision_id:
            return _ott_err(
                self, "revision_not_found", f"revision not found: {revision_id}", 404
            )
        if entry.get("content_mode") != "segmented":
            return _ott_err(self, "entry_not_segmented", "entry is not segmented", 400)
        total = int(entry.get("segment_count", 0) or 0)
        if index < 1 or index > total:
            return _ott_err(
                self, "segment_out_of_range", f"segment out of range: {index}", 404
            )
        content = entry.get("content", "")
        segment_size = int(
            entry.get("segment_size_hint", DEFAULT_SEGMENT_SIZE) or DEFAULT_SEGMENT_SIZE
        )
        start = (index - 1) * segment_size
        end = min(len(content), start + segment_size)
        segment_content = content[start:end]
        _json_resp(
            self,
            {
                "entry_id": entry_id,
                "revision_id": revision_id,
                "index": index,
                "start_char": start,
                "end_char": end,
                "char_count": len(segment_content),
                "content_hash": _sha256_text(segment_content),
                "content": segment_content,
            },
        )

    # ── API: 系统状态 ─────────────────────────────────────
