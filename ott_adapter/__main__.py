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
from .script_safety import validate_script_file
from .validation_types import format_report
from .validator import validate_content_file, validate_data_dir, validate_static_profile
from .server import start_server
from .scheduler import (
    run_script,
    run_all_fetches,
    rebuild_index,
    start_hot_reload,
    start_background_refresh,
    start_per_script_scheduler,
)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        return _run_validate(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "validate-script":
        return _run_validate_script(sys.argv[2:])

    p = argparse.ArgumentParser(
        prog="ott-adapter",
        description="OTT 本地适配器（实现 OTT Core v1，只读协议 /ott/v1）",
        epilog=(
            "commands:\n"
            "  ott-adapter validate <path>|--data-dir <dir>|--static-profile <dir>\n"
            "  ott-adapter validate-script <path> [--run]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--port", type=int, default=18888)
    p.add_argument("--data-dir", type=Path, default=Path("."))
    p.add_argument(
        "--fetch",
        action="store_true",
        help="启动时抓取所有脚本（默认跳过）",
    )
    p.add_argument(
        "--refresh",
        choices=["once", "hourly", "daily"],
        default="daily",
        help="后台刷新频率（once=不刷新，hourly/daily=后台定时跑所有脚本），仅影响未启用逐脚本调度的脚本",
    )
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

    idx = rebuild_index(d) or {"sources": []}
    scripts_dir = d / "scripts"
    n_scripts = len(list(scripts_dir.glob("fetch_*.py"))) if scripts_dir.exists() else 0
    n_entries = sum(s.get("entries_count", 0) for s in idx["sources"])
    print(f"[adapter] 索引: {n_entries} 篇文本 · {n_scripts} 个脚本")

    start_hot_reload(d)
    start_background_refresh(d, args.refresh)
    if args.scheduler:
        start_per_script_scheduler(d)
    start_server(args.port, d)
    return 0


def _run_validate(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="ott-adapter validate",
        description="验证 OTT content file 或 Static Profile",
    )
    p.add_argument("path", nargs="?", type=Path)
    p.add_argument("--data-dir", type=Path)
    p.add_argument("--static-profile", type=Path)
    args = p.parse_args(argv)
    selected = [
        value for value in (args.path, args.data_dir, args.static_profile) if value
    ]
    if len(selected) != 1:
        p.error("provide exactly one path, --data-dir, or --static-profile")
    if args.data_dir:
        label = str(args.data_dir)
        report = validate_data_dir(args.data_dir.resolve())
    elif args.static_profile:
        label = str(args.static_profile)
        report = validate_static_profile(args.static_profile.resolve())
    else:
        path = args.path
        if path is None:
            p.error("path is required")
        label = str(path)
        report = validate_content_file(path.resolve())
    print(format_report(label, report))
    return 0 if report.valid else 1


def _run_validate_script(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="ott-adapter validate-script",
        description="静态验证抓取脚本；--run 会在本机显式运行真实抓取",
    )
    p.add_argument("path", type=Path)
    p.add_argument("--run", action="store_true")
    args = p.parse_args(argv)
    path = args.path.resolve()
    report = validate_script_file(path)
    print(format_report(str(path), report))
    if not report.valid:
        return 1
    if not args.run:
        return 0
    success, output = run_script(path)
    print(("PASS" if success else "FAIL") + f" run {path}")
    if output:
        print(output)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
