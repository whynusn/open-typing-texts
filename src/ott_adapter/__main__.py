"""OTT 适配器 CLI 入口。

用法：
    ott-adapter [--port 18888] [--data-dir path] [--refresh once|hourly|daily]
"""

import argparse
import sys
from pathlib import Path

from .server import start_server
from .scheduler import run_all_fetches, start_scheduler


def main():
    parser = argparse.ArgumentParser(
        prog="ott-adapter",
        description="OTT 本地 HTTP 适配器 — 为跟打器提供文本服务",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=18888,
        help="监听端口（默认 18888）",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("."),
        help="OTT 仓库根目录（默认当前目录）",
    )
    parser.add_argument(
        "--refresh",
        choices=["once", "hourly", "daily"],
        default="once",
        help="刷新频率（默认 once：不自动刷新）",
    )

    args = parser.parse_args()

    # 先抓取一次
    run_all_fetches(args.data_dir)

    # 启动后台定时刷新
    start_scheduler(args.data_dir, args.refresh)

    # 启动 HTTP 服务（阻塞）
    start_server(args.port, args.data_dir)


if __name__ == "__main__":
    main()
