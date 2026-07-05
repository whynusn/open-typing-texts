# 动态脚本编写指南

> 本指南面向：需要为 OTT 添加新动态文本源的 Python 开发者。
> 读完本指南后，你将能够独立编写、测试并提交一个新的抓取脚本。

---

## 1. 脚本契约

每个动态脚本必须遵守以下约定：

### 函数签名

```python
def fetch_xxx(date_str: str, dry_run: bool = False) -> bool:
    ...
```

| 参数 | 说明 |
|:---|:---|
| `date_str` | 日期字符串 `YYYY-MM-DD`（用于日志和内容标记） |
| `dry_run` | `True` 时仅测试连接不写入文件 |
| **返回值** | `True` 表示成功，`False` 表示失败 |

### 输出路径

```python
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
OUTPUT_PATH = CONTENT_DIR / "{source_key}.json"  # 固定文件名，单文件覆盖
```

### 输出格式

```json
{
  "source_key": "你的source_key",
  "title": "显示标题",
  "content": "正文内容...",
  "metadata": {
    "description": "文本源描述",
    "category": "daily",
    "tags": ["标签1", "标签2"],
    "date": "2026-07-05"
  }
}
```

### 错误处理

- 网络失败 → `print` 错误信息，`return False`
- 源站返回空内容 → `print` 警告，`return False`
- **失败时不写入文件**，保留上一次成功的内容

### 幂等性

脚本每次运行结果相同。失败不覆盖已有内容，成功则完整覆盖。

---

## 2. 频率控制

CI 统一每日运行。各脚本自行判断是否需要真正更新：

```python
from datetime import datetime, timezone, timedelta

def _should_skip(output_path: Path, interval_days: int = 1) -> bool:
    """判断是否需要跳过更新"""
    if not output_path.exists():
        return False
    mtime = datetime.fromtimestamp(output_path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < timedelta(days=interval_days)
```

| 更新频率 | `interval_days` | 说明 |
|:---|:---|:---|
| 每日 | `1` | 每次都抓 |
| 每3天 | `3` | 3天内不重复抓取 |
| 每周 | `7` | 7天内不重复抓取 |

---

## 3. 完整示例模板

复制以下模板，替换 `xxx` 为你的文本源标识：

```python
#!/usr/bin/env python3
"""fetch_xxx.py — XXX 文本抓取脚本（CI 运行）"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

# ── 配置 ──────────────────────────────────────────────────────────────
SOURCE_KEY = "xxx"                          # 唯一标识（与文件名一致）
API_URL = "https://example.com/api/text"    # 目标 API 地址
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
OUTPUT_PATH = CONTENT_DIR / f"{SOURCE_KEY}.json"

# ── 抓取逻辑 ─────────────────────────────────────────────────────────

def fetch_xxx(date_str: str, dry_run: bool = False) -> bool:
    """抓取当日文本。"""

    # 1. 频率控制（可选）
    # if _should_skip(OUTPUT_PATH, interval_days=1):
    #     print(f"[{SOURCE_KEY}] 跳过：未到更新间隔")
    #     return True

    # 2. 请求数据
    try:
        with httpx.Client(timeout=20.0, trust_env=False) as client:
            resp = client.get(API_URL)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[{SOURCE_KEY}] 抓取失败: {e}")
        return False

    # 3. 解析内容
    content = data.get("text", "")
    if not isinstance(content, str) or not content:
        print(f"[{SOURCE_KEY}] 源站未返回有效文本")
        return False

    title = data.get("title", SOURCE_KEY)

    if dry_run:
        print(f"[{SOURCE_KEY}] dry_run: 获取到 {len(content)} 字符")
        return True

    # 4. 写入文件
    output = {
        "source_key": SOURCE_KEY,
        "title": title,
        "content": content,
        "metadata": {
            "description": f"XXX 文本（最后更新 {date_str}）",
            "category": "daily",
            "tags": ["xxx"],
            "date": date_str,
        },
    }
    _write_content(OUTPUT_PATH, output)
    print(f"[{SOURCE_KEY}] 已写入 {OUTPUT_PATH}")
    return True

# ── 工具函数 ─────────────────────────────────────────────────────────

def _write_content(path: Path, data: dict) -> None:
    """原子写入（tmp + replace）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def _should_skip(output_path: Path, interval_days: int = 1) -> bool:
    """判断是否跳过更新。"""
    if not output_path.exists():
        return False
    mtime = datetime.fromtimestamp(output_path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < timedelta(days=interval_days)

# ── 入口 ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="XXX 文本抓取脚本")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true", help="仅测试不写入")
    args = parser.parse_args()

    ok = fetch_xxx(args.date, dry_run=args.dry_run)
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
```

---

## 4. 本地测试

```bash
# 1. 安装依赖
pip install httpx

# 2. 干跑测试（不写入文件）
python scripts/fetch_xxx.py --dry-run

# 3. 实际运行（写入 content/xxx.json）
python scripts/fetch_xxx.py

# 4. 验证索引生成
python scripts/gen_index.py
cat registry_index.json | python3 -m json.tool
```

---

## 5. 提交清单

提交 PR 前逐项确认：

- [ ] 脚本放在 `scripts/fetch_xxx.py`
- [ ] `source_key` 只含字母、数字、下划线、连字符（不含 `/` `..` `\\`）
- [ ] 失败时 `return False`，不写入文件
- [ ] `--dry-run` 只测试不写入
- [ ] 本地运行 `gen_index.py` 生成正确的索引条目
- [ ] 在 `.github/workflows/daily.yml` 中添加一行调用（参见 [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md)）
- [ ] 已在 PR 描述中说明文本源和更新频率

---

## 6. 示例参考

- `scripts/fetch_jisubei.py` — API 加密调用（赛文极速杯）
- `scripts/fetch_daily.py` — 公开 API 直接调用（Hitokoto）
