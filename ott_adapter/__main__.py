"""OTT 适配器 CLI — 一键启动 WEB 服务器。

用法：
     ott-adapter                           # 默认端口 18888
     ott-adapter --port 19999              # 指定端口
     ott-adapter --data-dir /path/to/ott   # 数据目录
     ott-adapter --fetch                   # 启动时抓取所有脚本
     ott-adapter --refresh daily           # 后台定时刷新（hourly/daily/once）
"""

import argparse
import sys
from pathlib import Path
from .server import start_server
from .scheduler import (
    run_all_fetches,
    rebuild_index,
    start_hot_reload,
    start_background_refresh,
    start_per_script_scheduler,
)


def main():
    p = argparse.ArgumentParser(
        prog="ott-adapter",
        description="OTT 本地适配器（实现 OTT Core v1，只读协议 /ott/v1）",
    )
    p.add_argument("--port", type=int, default=18888)
    p.add_argument("--data-dir", type=Path, default=Path("."))
    p.add_argument("--fetch", action="store_true",
        help="启动时抓取所有脚本（默认跳过）",
    )
    p.add_argument(
        "--refresh",
        choices=["once", "hourly", "daily"],
        default="daily",
        help="后台刷新频率（once=不刷新，hourly/daily=后台定时跑所有脚本），仅影响未启用逐脚本调度的脚本")
    p.add_argument(
        "--scheduler",
        action="store_true",
        default=True,
        help="启用逐脚本定时调度（按 schedules.json）",
    )

    args = p.parse_args()
    d = args.data_dir.resolve()

    if args.fetch:
        print("[adapter] 正在抓取所有脚本...")
        n = run_all_fetches(d)
        print(f"[adapter] 抓取完成: {n} 个成功")

    idx = rebuild_index(d)
    scripts_dir = d / "scripts"
    n_scripts = len(list(scripts_dir.glob("fetch_*.py"))) if scripts_dir.exists() else 0
    n_entries = sum(s.get("entries_count", 0) for s in idx["sources"])
    print(f"[adapter] 索引: {n_entries} 篇文本 · {n_scripts} 个脚本")

    start_hot_reload(d)
    start_background_refresh(d, args.refresh)
    if args.scheduler:
        start_per_script_scheduler(d)
    start_server(args.port, d)


if __name__ == "__main__":
    main()
