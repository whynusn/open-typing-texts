import threading
import time
from pathlib import Path

from .scheduler import rebuild_index, run_all_fetches, run_script

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:
    FileSystemEventHandler = None
    Observer = None
    HAS_WATCHDOG = False


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
    if Observer is None or FileSystemEventHandler is None:
        raise RuntimeError("watchdog is unavailable")

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self.known = (
                set(s.name for s in scripts_dir.glob("fetch_*.py"))
                if scripts_dir.exists()
                else set()
            )

        def on_created(self, event):
            if event.is_directory:
                return
            src_path = (
                event.src_path.decode()
                if isinstance(event.src_path, bytes)
                else event.src_path
            )
            name = Path(src_path).name
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
                src_path = (
                    event.src_path.decode()
                    if isinstance(event.src_path, bytes)
                    else event.src_path
                )
                name = Path(src_path).name
                if name.startswith("fetch_") and name.endswith(".py"):
                    self.known.discard(name)
                    rebuild_index(data_dir)

    observer = Observer()
    observer.schedule(Handler(), str(scripts_dir), recursive=False)
    observer.daemon = True
    observer.start()
    print("[hot-reload] 已启用（watchdog 事件驱动）")


def _start_polling(scripts_dir, data_dir, interval):
    known = (
        set(s.name for s in scripts_dir.glob("fetch_*.py"))
        if scripts_dir.exists()
        else set()
    )

    def _watch():
        nonlocal known
        while True:
            time.sleep(interval)
            try:
                current = (
                    set(s.name for s in scripts_dir.glob("fetch_*.py"))
                    if scripts_dir.exists()
                    else set()
                )
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


def start_background_refresh(data_dir, interval):
    """定时刷新（不推送）。"""
    if interval == "once":
        return
    secs = {"hourly": 3600, "daily": 86400}.get(interval)
    if not secs:
        return

    def _loop():
        while True:
            time.sleep(secs)
            run_all_fetches(data_dir)
            rebuild_index(data_dir)

    threading.Thread(target=_loop, daemon=True).start()
