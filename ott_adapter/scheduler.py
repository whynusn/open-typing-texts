"""OTT 调度器 — 抓取、索引、热更新、贡献指南。"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


def _find_python():
    """找到真正的 Python 解释器（避开 Electron AppImage 包装器）。"""
    candidates = ["/usr/bin/python3", "/usr/local/bin/python3", sys.executable]
    for path in candidates:
        if not path:
            continue
        try:
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and "Python" in r.stdout:
                return path
        except Exception:
            continue
    return "python3"

_PYTHON = _find_python()


def run_script(script_path, timeout=60):
    try:
        r = subprocess.run([_PYTHON, str(script_path)], cwd=script_path.parent.parent,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


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
            sources.append({
                "source_key": key,
                "label": d.get("title", key),
                "description": d.get("metadata", {}).get("description", ""),
                "charCount": len(content),
                "category": d.get("metadata", {}).get("category", "static"),
                "update_freq": "daily" if "daily" in key else "static",
            })
    return {"version": 1,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "sources": sources}


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
            if existing.exists() and (time.time() - existing.stat.st_mtime) < 72000:
                continue
        success, output = run_script(s)
        if success:
            ok += 1
    return ok


def rebuild_index(data_dir):
    """重建索引文件（原子写）。"""
    index = build_index(data_dir)
    p = data_dir / "registry_index.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "content").mkdir(exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return index


# ── 热更新 ──────────────────────────────────────────────────────────

def start_hot_reload(data_dir, interval=30):
    """监控 scripts/ 目录，发现新脚本自动抓取。

    优先 watchdog（事件驱动），不可用时回退轮询。
    """
    scripts_dir = (data_dir / "scripts").resolve()
    if HAS_WATCHDOG:
        _start_watchdog(scripts_dir, data_dir)
    else:
        _start_polling(scripts_dir, data_dir, interval)


def _start_watchdog(scripts_dir, data_dir):
    class Handler(FileSystemEventHandler):
        def __init__(self):
            self.known = set(s.name for s in scripts_dir.glob("fetch_*.py")) if scripts_dir.exists() else set()

        def on_created(self, event):
            if event.is_directory:
                return
            name = Path(event.src_path).name
            if name.startswith("fetch_") and name.endswith(".py"):
                script = scripts_dir / name
                if script.exists():
                    print(f"[hot-reload] 发现新脚本: {name}")
                    ok, output = run_script(script)
                    if not ok:
                        print(f"[hot-reload] {name} 失败: {output[:100]}")
                    self.known.add(name)
                    rebuild_index(data_dir)

        def on_deleted(self, event):
            if not event.is_directory:
                name = Path(event.src_path).name
                if name.startswith("fetch_") and name.endswith(".py"):
                    self.known.discard(name)
                    rebuild_index(data_dir)

    observer = Observer()
    observer.schedule(Handler(), str(scripts_dir), recursive=False)
    observer.daemon = True
    observer.start()
    print("[hot-reload] 已启用（watchdog 事件驱动）")


def _start_polling(scripts_dir, data_dir, interval):
    known = set(s.name for s in scripts_dir.glob("fetch_*.py")) if scripts_dir.exists() else set()

    def _watch():
        nonlocal known
        while True:
            time.sleep(interval)
            try:
                current = set(s.name for s in scripts_dir.glob("fetch_*.py")) if scripts_dir.exists() else set()
                new = current - known
                if new:
                    for name in new:
                        script = scripts_dir / name
                        if script.exists():
                            print(f"[hot-reload] 发现新脚本: {name}")
                            run_script(script)
                    rebuild_index(data_dir)
                    known = current
                elif current != known:
                    rebuild_index(data_dir)
                    known = current
            except Exception as e:
                print(f"[hot-reload] 错误: {e}")

    threading.Thread(target=_watch, daemon=True).start()
    print(f"[hot-reload] 已启用（轮询 {interval}s，装 watchdog 升级事件驱动）")
