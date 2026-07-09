"""OTT Core v1 data-model helpers.

This module is shared by the adapter server and index builder so the public
read-only protocol uses one identity and summary model.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

INLINE_CONTENT_CHAR_LIMIT = 4096
DEFAULT_SEGMENT_SIZE = 1000
IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def valid_identifier(value: str) -> bool:
    return bool(value) and bool(IDENTIFIER_RE.match(value))


def entries_from_content_file(path: Path, include_content: bool = True) -> list[dict]:
    """Return normalized OTT entries from one legacy content file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    source_key = str(data.get("source_key") or path.stem)
    source_label = str(data.get("title") or source_key)
    top_meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    raw_entries = _raw_entries(data, top_meta, path)
    base_ids: list[str] = []
    for entry in raw_entries:
        content = entry.get("content", "") if isinstance(entry.get("content"), str) else ""
        base_ids.append(_entry_base_id(source_key, entry, content))
    duplicate_bases = {value for value in base_ids if base_ids.count(value) > 1}

    result = []
    for entry, base_id in zip(raw_entries, base_ids, strict=False):
        content = entry.get("content", "") if isinstance(entry.get("content"), str) else ""
        if not content:
            continue
        meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        content_hash = sha256_text(content)
        entry_id = str(entry.get("entry_id") or meta.get("entry_id") or "")
        if not valid_identifier(entry_id):
            entry_id = base_id
            if base_id in duplicate_bases:
                entry_id = f"{base_id}_{content_hash.removeprefix('sha256:')[:8]}"
        revision_id = str(
            entry.get("revision_id") or meta.get("revision_id") or ""
        )
        if not valid_identifier(revision_id):
            revision_id = (
                "rev_"
                + hashlib.sha256(f"{entry_id}\0{content_hash}".encode("utf-8")).hexdigest()[:24]
            )
        char_count = len(content)
        content_mode = (
            "inline" if char_count <= INLINE_CONTENT_CHAR_LIMIT else "segmented"
        )
        normalized = {
            "entry_id": entry_id,
            "source_key": source_key,
            "source_label": source_label,
            "title": str(entry.get("title") or source_label or source_key),
            "preview": content[:100].replace("\n", " ").strip(),
            "category": str(meta.get("category", top_meta.get("category", "")) or ""),
            "tags": meta.get("tags", []) if isinstance(meta.get("tags", []), list) else [],
            "fetched_at": str(entry.get("fetched_at", "") or ""),
            "char_count": char_count,
            "charCount": char_count,
            "content_mode": content_mode,
            "current_revision_id": revision_id,
            "revision_id": revision_id,
            "content_hash": content_hash,
            "segment_count": (
                (char_count + DEFAULT_SEGMENT_SIZE - 1) // DEFAULT_SEGMENT_SIZE
                if content_mode == "segmented"
                else 0
            ),
            "segment_size_hint": (
                DEFAULT_SEGMENT_SIZE if content_mode == "segmented" else 0
            ),
        }
        if include_content:
            normalized["content"] = content
        result.append(normalized)
    return result


def entry_summary(entry: dict) -> dict:
    return {
        "entry_id": entry["entry_id"],
        "source_key": entry["source_key"],
        "title": entry.get("title", ""),
        "preview": entry.get("preview", ""),
        "char_count": entry.get("char_count", 0),
        "charCount": entry.get("char_count", 0),
        "content_mode": entry.get("content_mode", "inline"),
        "current_revision_id": entry.get("current_revision_id", ""),
        "updated_at": entry.get("fetched_at", ""),
        "fetched_at": entry.get("fetched_at", ""),
        "category": entry.get("category", ""),
        "tags": entry.get("tags", []),
        "source_label": entry.get("source_label", ""),
        "segment_count": entry.get("segment_count", 0),
        "segment_size_hint": entry.get("segment_size_hint", 0),
    }


def entry_detail(entry: dict, include_content: bool = True) -> dict:
    detail = entry_summary(entry)
    detail.update(
        {
            "content_hash": entry.get("content_hash", ""),
            "revision_id": entry.get("current_revision_id", ""),
        }
    )
    if entry.get("content_mode") == "segmented":
        detail["segment_count"] = entry.get("segment_count", 0)
        detail["segment_size_hint"] = entry.get("segment_size_hint", DEFAULT_SEGMENT_SIZE)
        return detail
    detail["content"] = entry.get("content", "") if include_content else ""
    return detail


def _raw_entries(data: dict, top_meta: dict, path: Path) -> list[dict]:
    entries = data.get("entries", [])
    if isinstance(entries, list) and entries:
        return [entry for entry in entries if isinstance(entry, dict)]
    content = data.get("content")
    if isinstance(content, str) and content:
        return [
            {
                "title": data.get("title", ""),
                "content": content,
                "metadata": top_meta,
                "fetched_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S+08:00",
                    time.localtime(path.stat().st_mtime),
                ),
            }
        ]
    return []


def _entry_base_id(source_key: str, entry: dict, content: str) -> str:
    explicit = str(entry.get("entry_id") or "")
    meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    explicit = explicit or str(meta.get("entry_id") or "")
    if valid_identifier(explicit):
        return explicit
    title = str(entry.get("title") or "").strip()
    identity = f"{source_key}\0{title}" if title else f"{source_key}\0{sha256_text(content)}"
    return "ent_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
