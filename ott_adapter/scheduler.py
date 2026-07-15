"""OTT 调度器 — 抓取、索引、热更新、贡献指南。"""

import json
import subprocess
import sys
import threading
import time

from . import __version__
from .ott_core import build_static_profile, entries_from_content_file, entry_summary


def run_script(script_path, timeout=60):
    """运行脚本，使用当前 Python 解释器（保证 venv 依赖可用）。"""
    try:
        r = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=script_path.parent.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if r.returncode != 0:
            # 合并 stdout + stderr 用于诊断
            msg = (r.stdout + "\n" + r.stderr).strip()
            return False, msg.split("\n")[-1][:200]  # 只取最后一行关键信息
        return True, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "执行超时"
    except Exception as e:
        return False, str(e)


def _recent_from_entries(entries: list, d: dict) -> list:
    """从 entries 中提取最近 10 条摘要（title + fetched_at），用于索引缓存。"""
    if not entries and d.get("content"):
        return [
            {
                "title": d.get("title", ""),
                "fetched_at": "",
                "source_key": d.get("source_key", ""),
            }
        ]
    result = []
    for e in entries[-10:]:
        result.append(
            {
                "title": e.get("title", ""),
                "fetched_at": e.get("fetched_at", ""),
                "source_key": d.get("source_key", ""),
            }
        )
    return result


def _recent_from_ott_entries(entries: list[dict]) -> list[dict]:
    return [
        {
            "title": entry.get("title", ""),
            "fetched_at": entry.get("fetched_at", ""),
            "source_key": entry.get("source_key", ""),
        }
        for entry in entries[-10:]
    ]


def build_index(data_dir):
    """扫描 content/ 目录构建索引。"""
    content_dir = data_dir / "content"
    sources = []
    if content_dir.exists():
        for f in sorted(content_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            key = d.get("source_key") or f.stem
            content = d.get("content", "")
            if not isinstance(content, str):
                content = ""
            ott_entries = [
                entry_summary(entry)
                for entry in entries_from_content_file(f, include_content=False)
            ]
            char_count = sum(int(e.get("char_count", 0) or 0) for e in ott_entries)
            entry_preview = ""
            if ott_entries:
                entry_preview = str(ott_entries[-1].get("preview", "") or "")
            elif content:
                entry_preview = content[:120].replace("\n", " ").strip()
            sources.append(
                {
                    "source_key": key,
                    "label": d.get("title", key),
                    "description": d.get("metadata", {}).get("description", ""),
                    "charCount": char_count,
                    "entries_count": len(ott_entries),
                    "category": d.get("metadata", {}).get("category", "static"),
                    "update_freq": "daily" if "daily" in key else "static",
                    "title_preview": (d.get("title", "") or "")[:120],
                    "entry_preview": entry_preview,
                    "recent_entries": _recent_from_ott_entries(ott_entries),
                    "ott_entries": ott_entries,
                }
            )
    return {
        "version": 2,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "sources": sources,
    }


def run_all_fetches(data_dir, force=False):
    """运行所有抓取脚本。返回成功数量。"""
    scripts_dir = data_dir / "scripts"
    if not scripts_dir.exists():
        return 0
    ok = 0
    for s in sorted(scripts_dir.glob("fetch_*.py")):
        # 幂等性：20 小时内不重复抓取
        if not force:
            key = s.stem.replace("fetch_", "")
            existing = data_dir / "content" / f"{key}.json"
            if existing.exists() and (time.time() - existing.stat().st_mtime) < 72000:
                continue
        success, output = run_script(s)
        if success:
            ok += 1
    return ok


_rebuild_lock = threading.Lock()


def rebuild_index(data_dir):
    """重建索引文件（原子写）。重入安全：同时调用仅第一次执行。"""
    if not _rebuild_lock.acquire(blocking=False):
        return None
    try:
        index = build_index(data_dir)
        p = data_dir / "registry_index.json"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "content").mkdir(exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(index, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(p)
        build_static_profile(data_dir, index, adapter_version=__version__)
        return index
    finally:
        _rebuild_lock.release()


def start_hot_reload(data_dir, interval=30):
    from .hot_reload import start_hot_reload as start

    return start(data_dir, interval)


def start_background_refresh(data_dir, interval):
    from .hot_reload import start_background_refresh as start

    return start(data_dir, interval)


def start_per_script_scheduler(data_dir, tick=60):
    from .script_scheduler import start_per_script_scheduler as start

    return start(data_dir, tick)
