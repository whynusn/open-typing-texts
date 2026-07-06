"""OTT 适配器 CLI — 一键启动 WEB 服务器。

用法：
    ott-adapter                           # 默认端口 18888
    ott-adapter --port 19999              # 指定端口
    ott-adapter --data-dir /path/to/ott   # 数据目录
    ott-adapter --no-fetch                # 跳过首次抓取
    ott-adapter --refresh daily           # 定时抓取（hourly/daily/once）
"""

import argparse
import sys
from pathlib import Path
from .server import start_server
from .scheduler import run_all_fetches, rebuild_index, start_hot_reload, start_background_refresh


def main():
    p = argparse.ArgumentParser(prog="ott-adapter", description="OTT 本地适配器")
    p.add_argument("--port", type=int, default=18888)
    p.add_argument("--data-dir", type=Path, default=Path("."))
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument("--refresh", choices=["once", "hourly", "daily"], default="once")

    args = p.parse_args()
    d = args.data_dir.resolve()

    if not args.no_fetch:
        print("[adapter] 正在抓取文本...")
        n = run_all_fetches(d)
        print(f"[adapter] 抓取完成: {n} 个成功")

    idx = rebuild_index(d)
    print(f"[adapter] 索引: {len(idx['sources'])} 个文本源")

    start_hot_reload(d)
    start_background_refresh(d, args.refresh)
    start_server(args.port, d)


if __name__ == "__main__":
    main()
