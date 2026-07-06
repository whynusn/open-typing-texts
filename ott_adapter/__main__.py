"""OTT 适配器 CLI — 一键启动。

用法：
    ott-adapter                              # 默认：抓取 + 服务 + 热更新
    ott-adapter --port 19999                  # 指定端口
    ott-adapter --no-fetch                    # 跳过首次抓取
    ott-adapter --refresh daily               # 定时抓取（hourly/daily/once）
    ott-adapter --self-host daily             # 自托管：自动 pull + fetch + push
    ott-adapter --data-dir /path/to/ott       # 数据目录
"""

import argparse
import sys
from pathlib import Path
from .server import start_server
from .scheduler import (
    run_all_fetches,
    rebuild_index,
    start_background_refresh,
    start_hot_reload,
    start_self_host,
)


def main():
    p = argparse.ArgumentParser(prog="ott-adapter", description="OTT 本地适配器")
    p.add_argument("--port", type=int, default=18888, help="监听端口")
    p.add_argument("--data-dir", type=Path, default=Path("."), help="数据目录")
    p.add_argument("--no-fetch", action="store_true", help="跳过首次抓取")
    p.add_argument("--refresh", choices=["once", "hourly", "daily"], default="once",
                   help="定时抓取频率")
    p.add_argument("--self-host", choices=["once", "hourly", "daily"], default=None,
                   help="自托管模式：自动 pull + fetch + commit + push")
    p.add_argument("--hot-reload-interval", type=int, default=30,
                   help="脚本目录热更新检测间隔（秒，默认 30）")

    args = p.parse_args()
    d = args.data_dir.resolve()

    # 1. 首次抓取
    if not args.no_fetch:
        print("[adapter] 正在抓取文本...")
        n = run_all_fetches(d)
        print(f"[adapter] 抓取完成: {n} 个成功")

    # 2. 重建索引
    idx = rebuild_index(d)
    print(f"[adapter] 索引: {len(idx['sources'])} 个文本源")

    # 3. 启动后台服务
    start_hot_reload(d, interval=args.hot_reload_interval)
    start_background_refresh(d, args.refresh)
    if args.self_host:
        start_self_host(d, interval=args.self_host, enabled=True)

    # 4. 启动 HTTP 服务（阻塞）
    start_server(args.port, d)


if __name__ == "__main__":
    main()
