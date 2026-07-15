def script_safety_payload(report):
    return {
        "ok": False,
        "error": "脚本安全检查失败",
        "validation": report.to_dict(),
    }


def script_template(source_key):
    return f'''#!/usr/bin/env python3
"""fetch_{source_key}.py — {{description}}。

DISCLAIMER: 请确保抓取行为符合目标网站 robots.txt 及当地版权法，使用者自负全责。
"""

import json
import time
from pathlib import Path
import httpx

SOURCE_KEY = "{source_key}"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "content" / f"{{SOURCE_KEY}}.json"


def _load_data():
    """读取已有数据，兼容旧格式自动迁移。"""
    if not OUTPUT_PATH.exists():
        return {{"source_key": SOURCE_KEY, "entries": []}}
    d = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    if "entries" not in d and "content" in d:
        d["entries"] = [{{
            "title": d.pop("title", ""),
            "content": d.pop("content", ""),
            "metadata": d.pop("metadata", {{}}),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
        }}]
    d.setdefault("entries", [])
    return d


def _append_entry(d, entry):
    """追加一条记录，顶层保留最新内容以兼容旧客户端。"""
    entry["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())
    content = entry.get("content", "")
    for i, e in enumerate(d["entries"]):
        if e.get("content") == content:
            d["entries"][i] = entry
            d["title"] = entry["title"]
            d["content"] = content
            d["metadata"] = entry.get("metadata", {{}})
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = OUTPUT_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(OUTPUT_PATH)
            print(f"[{{SOURCE_KEY}}] 已更新（重复内容）— 共 {{len(d['entries'])}} 篇")
            return
    d["entries"].append(entry)
    d["title"] = entry["title"]
    d["content"] = entry["content"]
    d["metadata"] = entry.get("metadata", {{}})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    print(f"[{{SOURCE_KEY}}] 已追加 — 共 {{len(d['entries'])}} 篇")


def fetch():
    with httpx.Client(timeout=20, trust_env=False) as client:
        resp = client.get("https://example.com/api/text")
        resp.raise_for_status()
        return resp.json()


def main():
    data = fetch()
    entry = {{
        "title": data.get("title", SOURCE_KEY),
        "content": data["text"],
        "metadata": {{
            "description": "你的文本描述",
            "category": "static",
            "tags": ["标签1", "标签2"],
        }}
    }}
    d = _load_data()
    _append_entry(d, entry)


if __name__ == "__main__":
    main()
'''
