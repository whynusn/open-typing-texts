#!/usr/bin/env python3
"""fetch_daily.py — 每日文本抓取脚本（用户本地运行）。

DISCLAIMER: 本脚本仅供技术学习，请确保抓取内容符合目标网站的 robots.txt
及当地版权法，使用者自负全责。

数据源：Hitokoto 中文句子 API（公开免费）
GET https://v1.hitokoto.cn/?c=i
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_URL = "https://v1.hitokoto.cn"
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
OUTPUT_PATH = CONTENT_DIR / "daily.json"


def fetch_daily(date_str: str, dry_run: bool = False) -> bool:
    try:
        with httpx.Client(timeout=10.0, trust_env=False) as client:
            resp = client.get(API_URL, params={"c": "i"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[fetch_daily] 抓取失败: {e}")
        return False

    content = data.get("hitokoto", "")
    if not content:
        print("[fetch_daily] 源站未返回有效文本")
        return False

    # 有意义描述：来源 + 作者
    from_who = data.get("from_who") or ""
    from_source = data.get("from") or "每日文本"
    description = f"{from_source}"
    if from_who:
        description = f"《{from_source}》{from_who}"

    output = {
        "source_key": "daily",
        "label": from_source,
        "title": from_source,
        "content": content,
        "metadata": {
            "description": description,
            "category": "daily",
            "tags": ["每日文本"],
            "author": from_who,
            "date": date_str,
            "source_url": "https://hitokoto.cn",
        },
    }

    if dry_run:
        print(f"[fetch_daily] dry_run: {content[:30]}... ({len(content)} 字)")
        print(f"[fetch_daily] 描述: {description}")
        return True

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    print(f"[fetch_daily] 已写入 {OUTPUT_PATH}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="每日文本抓取")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if fetch_daily(args.date, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())
