"""OTT 调度器 — 抓取、索引、热更新、自托管。"""

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
    candidates = [
        "/usr/bin/python3",
        "/usr/local/bin/python3",
        sys.executable,
    ]
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
    scripts_dir = data_dir / "scripts"
    if not scripts_dir.exists():
        return 0
    ok = 0
    for s in sorted(scripts_dir.glob("fetch_*.py")):
        if not force:
            key = s.stem.replace("fetch_", "")
            existing = data_dir / "content" / f"{key}.json"
            if existing.exists() and (time.time() - existing.stat().st_mtime) < 72000:
                continue
        success, output = run_script(s)
        if success:
            ok += 1
    return ok


def rebuild_index(data_dir):
    index = build_index(data_dir)
    p = data_dir / "registry_index.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "content").mkdir(exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return index


# ── 热更新：监控 scripts/ 目录 ─────────────────────────────────────

def start_hot_reload(data_dir, interval=30):
    """监控 scripts/ 目录，检测到新脚本时自动抓取并重建索引。

    优先使用 watchdog（事件驱动），不可用时回退到轮询。
    """
    scripts_dir = (data_dir / "scripts").resolve()

    if HAS_WATCHDOG:
        _start_watchdog(scripts_dir, data_dir)
    else:
        _start_polling(scripts_dir, data_dir, interval)


def _start_watchdog(scripts_dir, data_dir):
    """使用 watchdog 事件驱动监控。"""

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self.known = set(s.name for s in scripts_dir.glob("fetch_*.py")) if scripts_dir.exists() else set()

        def on_created(self, event):
            if event.is_directory or not event.src_path.endswith(".json"):
                name = Path(event.src_path).name
                if name.startswith("fetch_") and name.endswith(".py"):
                    self._handle_new(name)

        def on_deleted(self, event):
            if not event.is_directory:
                name = Path(event.src_path).name
                if name.startswith("fetch_") and name.endswith(".py"):
                    self.known.discard(name)
                    rebuild_index(data_dir)

        def _handle_new(self, name):
            script = scripts_dir / name
            if script.exists():
                print(f"[hot-reload] 发现新脚本: {name}")
                ok, output = run_script(script)
                if not ok:
                    print(f"[hot-reload] {name} 失败: {output[:100]}")
                self.known.add(name)
                rebuild_index(data_dir)

    handler = Handler()
    observer = Observer()
    observer.schedule(handler, str(scripts_dir), recursive=False)
    observer.daemon = True
    observer.start()
    print(f"[hot-reload] 已启用（watchdog 事件驱动）")


def _start_polling(scripts_dir, data_dir, interval):
    """使用轮询监控（watchdog 不可用时的回退）。"""
    known_scripts = set(s.name for s in scripts_dir.glob("fetch_*.py")) if scripts_dir.exists() else set()

    def _watch():
        nonlocal known_scripts
        while True:
            time.sleep(interval)
            try:
                current = set(s.name for s in scripts_dir.glob("fetch_*.py")) if scripts_dir.exists() else set()
                new_scripts = current - known_scripts
                if new_scripts:
                    print(f"[hot-reload] 发现新脚本: {', '.join(new_scripts)}")
                    for name in new_scripts:
                        script = scripts_dir / name
                        if script.exists():
                            run_script(script)
                    rebuild_index(data_dir)
                    known_scripts = current
                elif current != known_scripts:
                    rebuild_index(data_dir)
                    known_scripts = current
            except Exception as e:
                print(f"[hot-reload] 错误: {e}")

    t = threading.Thread(target=_watch, daemon=True)
    t.start()
    print(f"[hot-reload] 已启用（轮询间隔: {interval}s，安装 watchdog 可升级为事件驱动）")


# ── 自托管：自动 pull → fetch → commit → push ────────────────────

def git_auto_push(data_dir, remote="origin", branch="main"):
    """拉取最新 → 运行抓取 → 提交并推送。"""
    try:
        # 拉取最新脚本
        subprocess.run(["git", "pull", "--rebase", remote, branch],
                       cwd=data_dir, capture_output=True, timeout=30,
                       check=True)

        # 运行抓取
        run_all_fetches(data_dir, force=True)
        idx = rebuild_index(data_dir)
        if not idx["sources"]:
            return

        # 检查是否有变更
        status = subprocess.run(["git", "status", "--porcelain", "content/", "registry_index.json"],
                                cwd=data_dir, capture_output=True, text=True)
        if not status.stdout.strip():
            return  # 无变更

        # 提交
        subprocess.run(["git", "add", "content/", "registry_index.json"],
                       cwd=data_dir, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: auto update ({time.strftime('%Y-%m-%d %H:%M')})"],
                       cwd=data_dir, check=True)

        # 推送
        subprocess.run(["git", "push", remote, branch],
                       cwd=data_dir, check=True, timeout=30)
        print("[self-host] 已自动推送更新")

    except subprocess.CalledProcessError as e:
        print(f"[self-host] git 操作失败: {e}")
    except Exception as e:
        print(f"[self-host] 错误: {e}")


def start_self_host(data_dir, interval="daily", enabled=False):
    """启动后台自托管线程。"""
    if not enabled:
        return

    # 检查是否为 git 仓库
    git_dir = data_dir / ".git"
    if not git_dir.exists():
        print("[self-host] 警告：当前目录不是 git 仓库，请执行 git init 并添加 remote")
        return

    seconds = {"hourly": 3600, "daily": 86400}.get(interval)
    if not seconds:
        return

    def _loop():
        while True:
            time.sleep(seconds)
            git_auto_push(data_dir)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"[self-host] 自托管已启用，间隔: {interval}")


def start_background_refresh(data_dir, interval):
    """兼容旧接口的定时刷新（不推送）。"""
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

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
