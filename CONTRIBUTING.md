# 如何向 OTT 贡献新脚本

本文档描述如何贡献一个本地抓取脚本。OTT Core v1 的权威协议见 [OTT_SPEC.md](OTT_SPEC.md)。贡献脚本时，你只提交 `scripts/fetch_xxx.py`；不要提交 `content/` 下真实抓取内容。

## 1. 准备工作

- GitHub 账号
- Git
- Python 3.12+
- `uv`
- 一个你有权在本地抓取或转换的文本来源

```bash
git clone https://github.com/你的用户名/open-typing-texts.git
cd open-typing-texts
uv sync
```

## 2. 输出模型

脚本可以输出 legacy-compatible content file，adapter 会把它规范化为 OTT Core v1 entry：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文内容",
  "metadata": {
    "description": "正文摘要或来源说明",
    "category": "daily",
    "tags": ["标签"],
    "date": "2026-07-05"
  }
}
```

如果一个来源包含多篇文本，使用 `entries[]`：

```json
{
  "source_key": "mysource",
  "title": "最新标题",
  "content": "最新正文",
  "metadata": {"category": "daily"},
  "entries": [
    {
      "entry_id": "ent_mysource_20260705",
      "title": "标题",
      "content": "正文内容",
      "metadata": {"tags": ["标签"]},
      "fetched_at": "2026-07-05T10:00:00+08:00"
    }
  ]
}
```

字段约束：

- `source_key` 只能包含字母、数字、下划线。
- `content` 必须是非空字符串。
- 发布后建议持久化显式 `entry_id`，避免标题调整导致身份变化。
- `revision_id` 可省略；adapter 会随 `content_hash` 派生。
- 小文本会成为 `content_mode: "inline"`，长文本会成为 `content_mode: "segmented"`。
- summary 列表不得包含全文；segmented detail 不得包含全文。

## 3. 编写脚本

先复制现有脚本作为起点：

```bash
cp scripts/fetch_poem.py scripts/fetch_mysource.py
```

推荐脚本结构：

```python
#!/usr/bin/env python3
"""fetch_mysource.py - 我的文本源抓取脚本。

DISCLAIMER: 请确保抓取行为符合目标网站 robots.txt、服务条款及当地版权法。
"""

import json
from pathlib import Path

import httpx

SOURCE_KEY = "mysource"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "content" / f"{SOURCE_KEY}.json"


def fetch_raw() -> dict:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        response = client.get("https://example.com/api/text")
        response.raise_for_status()
        return response.json()


def transform(raw: dict) -> dict:
    return {
        "source_key": SOURCE_KEY,
        "title": raw.get("title", SOURCE_KEY),
        "content": raw["text"],
        "metadata": {
            "description": "你的文本源描述",
            "category": "daily",
            "tags": ["标签"],
        },
    }


def main() -> int:
    output = transform(fetch_raw())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(OUTPUT_PATH)
    return 0
```

`fetch_raw()` 可以访问真实网络，只能在贡献者本机运行；CI 只应使用 fake raw 数据测试 `transform()`。

## 4. 本地验证

```bash
python scripts/fetch_mysource.py
uv run ott-adapter validate-script scripts/fetch_mysource.py
uv run ott-adapter validate content/mysource.json
uv run ott-adapter validate --data-dir .
uv run ott-adapter --data-dir .
```

浏览器打开 <http://127.0.0.1:18888>，确认文本可见。

如果验证失败，先修复字段格式，再重新运行脚本。不要把真实 `content/` 文件加入 PR。

## 5. 提交贡献

```bash
git checkout -b add-mysource
git add scripts/fetch_mysource.py
git commit -m "feat: add mysource fetch script"
git push origin add-mysource
```

PR 描述请包含：

- 数据来源和合规说明。
- 本地运行命令。
- `ott-adapter validate ...` 与 `ott-adapter validate-script ...` 的 PASS/FAIL 摘要。
- 是否需要账号、cookie、token 或特殊环境变量。

## 6. CI 边界

项目 CI 不运行真实抓取脚本，不访问第三方文本来源。CI 可以检查：

- `transform()` 对 fake raw 数据的输出。
- schema/validator 是否通过。
- 脚本是否包含高风险调用，例如 `eval`、`exec`、`subprocess`、`os.system`、`socket`、`pty`、`ctypes`。
- 是否误提交 `content/` 真实内容。

法律、版权、robots.txt、服务条款仍由贡献者和维护者人工确认。
