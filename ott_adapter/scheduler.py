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


def run_script(script_path, timeout=60):
    """运行脚本，使用当前 Python 解释器（保证 venv 依赖可用）。"""
    try:
        r = subprocess.run([sys.executable, str(script_path)], cwd=script_path.parent.parent,
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            # 合并 stdout + stderr 用于诊断
            msg = (r.stdout + "\n" + r.stderr).strip()
            return False, msg.split("\n")[-1][:200]  # 只取最后一行关键信息
        return True, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "执行超时"
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
            entries = d.get("entries", [])
            sources.append({
                "source_key": key,
                "label": d.get("title", key),
                "description": d.get("metadata", {}).get("description", ""),
                "charCount": len(content),
                "entries_count": len(entries),
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
            if existing.exists() and (time.time() - existing.stat().st_mtime) < 72000:
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


# ── 逐脚本定时调度 ──────────────────────────────────────────

SCHEDULES_FILE = "schedules.json"


def _load_schedules(data_dir) -> dict:
    """加载 schedules.json。"""
    p = data_dir / SCHEDULES_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"schedules": {}}


def _save_schedules(data_dir, schedules):
    """原子写入 schedules.json。"""
    p = data_dir / SCHEDULES_FILE
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def start_per_script_scheduler(data_dir, tick=60):
    """按 schedules.json 逐脚本定时执行。

    每 tick 秒检查一次，到期则运行脚本并更新 last_run。
    """
    secs_map = {"hourly": 3600, "daily": 86400, "weekly": 604800}

    def _loop():
        while True:
            time.sleep(tick)
            try:
                schedules = _load_schedules(data_dir)
                now = time.time()
                scripts_dir = data_dir / "scripts"
                changed = False

                for name, sched in list(schedules.get("schedules", {}).items()):
                    if not sched.get("enabled"):
                        continue
                    interval = sched.get("interval", "manual")
                    interval_secs = secs_map.get(interval)
                    if not interval_secs:
                        continue

                    last_run = sched.get("last_run")
                    if last_run is not None:
                        try:
                            last_ts = _parse_iso(last_run)
                        except (ValueError, TypeError):
                            last_ts = 0
                        if now - last_ts < interval_secs:
                            continue

                    # 到期，运行脚本
                    script = scripts_dir / f"fetch_{name}.py"
                    if not script.exists():
                        continue

                    print(f"[scheduler] 定时执行: fetch_{name}.py ({interval})")
                    run_script(script)
                    content_file = data_dir / "content" / f"{name}.json"
                    if content_file.exists():
                        sched["last_run"] = time.strftime(
                            "%Y-%m-%dT%H:%M:%S", time.gmtime(content_file.stat().st_mtime + 8 * 3600)
                        ) + "+08:00"
                    else:
                        sched["last_run"] = time.strftime(
                            "%Y-%m-%dT%H:%M:%S+08:00", time.localtime()
                        )
                    schedules["schedules"][name] = sched
                    changed = True

                if changed:
                    _save_schedules(data_dir, schedules)

            except Exception as e:
                print(f"[scheduler] 调度循环错误: {e}")

    threading.Thread(target=_loop, daemon=True).start()
    print(f"[scheduler] 逐脚本定时已启动（按 schedules.json 调度）")


def _parse_iso(iso_str: str) -> float:
    """解析 ISO 8601 时间戳为 Unix 时间戳（简化版）。"""
    from datetime import datetime
    # 处理 'Z' 后缀和时区偏移
    s = iso_str.replace("Z", "+00:00")
    if "+" in s and s.count(":") > 2:
        # 有偏移量，去掉偏移部分的后两个 segment
        parts = s.rsplit(":", 1)
        s = parts[0] + parts[1][:2] if len(parts) > 1 else s
    return datetime.fromisoformat(s).timestamp()
