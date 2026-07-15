import json
import re
import threading
import time
from pathlib import Path

from .scheduler import rebuild_index

SOURCE_KEY_RE = re.compile(r"^[a-zA-Z0-9_]+$")
SCHEDULES_FILE = "schedules.json"
_CACHE_TTL = 2.0
_cache: dict[str, tuple[float, dict]] = {}
_write_locks: dict[str, threading.Lock] = {}
_schedule_lock = threading.Lock()
_write_locks_lock = threading.Lock()


def get_write_lock(key: str) -> threading.Lock:
    with _write_locks_lock:
        if key not in _write_locks:
            _write_locks[key] = threading.Lock()
        return _write_locks[key]


def cache_get(key: str) -> dict | None:
    entry = _cache.get(key)
    if entry is not None and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def cache_set(key: str, value: dict):
    _cache[key] = (time.time(), value)


def cache_invalidate(prefix: str = ""):
    if prefix:
        to_delete = [key for key in _cache if key.startswith(prefix)]
        for key in to_delete:
            del _cache[key]
    else:
        _cache.clear()


def rebuild_and_invalidate(data_dir):
    result = rebuild_index(data_dir)
    cache_invalidate(str(data_dir / "registry_index.json"))
    return result if result is not None else read_index(data_dir)


def get_schedules(data_dir) -> dict:
    key = str(data_dir / SCHEDULES_FILE)
    cached = cache_get(key)
    if cached is not None:
        return cached
    path = Path(key)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cache_set(key, data)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"schedules": {}}


def save_schedules(data_dir, schedules):
    path = data_dir / SCHEDULES_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(schedules, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp.replace(path)
    cache_invalidate(str(path))


def update_last_run(data_dir, name):
    with _schedule_lock:
        schedules = get_schedules(data_dir)
        if name not in schedules.get("schedules", {}):
            return
        content_file = data_dir / "content" / f"{name}.json"
        if content_file.exists():
            schedules["schedules"][name]["last_run"] = (
                time.strftime(
                    "%Y-%m-%dT%H:%M:%S",
                    time.gmtime(content_file.stat().st_mtime + 8 * 3600),
                )
                + "+08:00"
            )
            save_schedules(data_dir, schedules)


def read_index(data_dir) -> dict:
    key = str(data_dir / "registry_index.json")
    cached = cache_get(key)
    if cached is not None:
        return cached
    path = Path(key)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cache_set(key, data)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 2, "updated_at": "", "sources": []}


def format_age(seconds):
    if seconds is None:
        return "未知"
    if seconds < 60:
        return f"{int(seconds)} 秒前"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    return f"{int(seconds // 86400)} 天前"


def calc_next_run(interval, last_run_ts=None):
    now = time.time()
    base = last_run_ts or now
    offsets = {"hourly": 3600, "daily": 86400, "weekly": 604800}
    secs = offsets.get(interval)
    if not secs:
        return None
    next_run = max(base + secs, now + 60)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(next_run))


def validate_ott_json(data: dict) -> dict:
    from .validator import validate_content_data

    validation = validate_content_data(data)
    if not validation.valid:
        return {
            "valid": False,
            "error": "; ".join(issue.message for issue in validation.issues),
        }
    return {
        "valid": True,
        "charCount": validation.char_count,
        "source_key": data.get("source_key"),
    }
