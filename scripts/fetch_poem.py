#!/usr/bin/env python3
"""fetch_poem.py — 每日诗句抓取脚本（用户本地运行）。

DISCLAIMER: 本脚本仅供技术学习，请确保抓取行为符合目标网站 robots.txt
及当地版权法，使用者自负全责。

数据源：Hitokoto 中文句子 API（公开免费）
GET https://v1.hitokoto.cn/?c=i
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_URL = "https://v1.hitokoto.cn"
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
OUTPUT_PATH = CONTENT_DIR / "poem.json"
SOURCE_KEY = "poem"


def _load_data():
    if not OUTPUT_PATH.exists():
        return {"source_key": SOURCE_KEY, "entries": []}
    d = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    if "entries" not in d and "content" in d:
        d["entries"] = [{
            "title": d.pop("title", ""),
            "content": d.pop("content", ""),
            "metadata": d.pop("metadata", {}),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
        }]
    d.setdefault("entries", [])
    return d


def _append_entry(d, entry):
    entry["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())
    content = entry.get("content", "")
    for i, e in enumerate(d["entries"]):
        if e.get("content") == content:
            d["entries"][i] = entry
            d["title"] = entry["title"]
            d["content"] = content
            d["metadata"] = entry.get("metadata", {})
            tmp = OUTPUT_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(OUTPUT_PATH)
            print(f"[fetch_poem] 已更新（重复内容）— 共 {len(d['entries'])} 篇")
            return
    d["entries"].append(entry)
    d["title"] = entry["title"]
    d["content"] = content
    d["metadata"] = entry.get("metadata", {})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    print(f"[fetch_poem] 已追加 — 共 {len(d['entries'])} 篇")


def fetch_poem(date_str: str, dry_run: bool = False) -> bool:
    try:
        with httpx.Client(timeout=10.0, trust_env=False) as client:
            resp = client.get(API_URL, params={"c": "i"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[fetch_poem] 抓取失败: {e}")
        return False

    content = data.get("hitokoto", "")
    if not content:
        print("[fetch_poem] 源站未返回有效文本")
        return False

    from_who = data.get("from_who") or ""
    from_source = data.get("from") or "每日文本"
    description = from_source
    if from_who:
        description = f"《{from_source}》{from_who}"

    entry = {
        "title": from_source,
        "content": content,
        "metadata": {
            "description": description,
            "category": "诗句",
            "tags": ["每日诗句"],
            "author": from_who,
            "date": date_str,
            "source_url": "https://hitokoto.cn",
        },
    }

    if dry_run:
        print(f"[fetch_poem] dry_run: {content[:30]}... ({len(content)} 字)")
        print(f"[fetch_poem] 描述: {description}")
        return True

    d = _load_data()
    _append_entry(d, entry)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="每日诗句抓取")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if fetch_poem(args.date, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())
