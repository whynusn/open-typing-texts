import json
import threading
import time
from datetime import datetime

from .scheduler import run_script


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
    tmp.write_text(
        json.dumps(schedules, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
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
                        sched["last_run"] = (
                            time.strftime(
                                "%Y-%m-%dT%H:%M:%S",
                                time.gmtime(content_file.stat().st_mtime + 8 * 3600),
                            )
                            + "+08:00"
                        )
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
    print("[scheduler] 逐脚本定时已启动（按 schedules.json 调度）")


def _parse_iso(iso_str: str) -> float:
    """解析 ISO 8601 时间戳为 Unix 时间戳（简化版）。"""
    # 处理 'Z' 后缀和时区偏移
    s = iso_str.replace("Z", "+00:00")
    if "+" in s and s.count(":") > 2:
        # 有偏移量，去掉偏移部分的后两个 segment
        parts = s.rsplit(":", 1)
        s = parts[0] + parts[1][:2] if len(parts) > 1 else s
    return datetime.fromisoformat(s).timestamp()
