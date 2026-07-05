"""OTT 适配器调度器。

负责运行抓取脚本生成 JSON，以及定时刷新。
"""

import subprocess
import sys
import time
from pathlib import Path


def run_script(script_path: Path) -> bool:
    """运行指定的 Python 脚本。"""
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=script_path.parent.parent,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"[scheduler] {script_path.name} failed: {result.stderr.strip()}")
            return False
        return True
    except Exception as e:
        print(f"[scheduler] {script_path.name} error: {e}")
        return False


def run_all_fetches(data_dir: Path):
    """运行所有抓取脚本。"""
    scripts_dir = data_dir / "scripts"
    if not scripts_dir.exists():
        print("[scheduler] scripts/ directory not found")
        return

    for script in sorted(scripts_dir.glob("fetch_*.py")):
        print(f"[scheduler] running {script.name}...")
        run_script(script)

    # 生成索引
    gen_script = scripts_dir / "gen_index.py"
    if gen_script.exists():
        print("[scheduler] running gen_index.py...")
        run_script(gen_script)


def start_scheduler(data_dir: Path, interval: str):
    """启动后台定时调度。"""
    if interval == "once":
        return

    seconds = {
        "hourly": 3600,
        "daily": 86400,
    }.get(interval)

    if not seconds:
        print(f"[scheduler] unknown interval: {interval}")
        return

    import threading

    def _loop():
        while True:
            time.sleep(seconds)
            run_all_fetches(data_dir)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"[scheduler] refresh interval: {interval}")
