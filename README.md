# open-typing-texts

> 开源中文打字文本库。为中文跟打器提供每日更新的练习文本，由 GitHub Actions 自动抓取、客户端只读使用。

## 仓库结构

```
open-typing-texts/
├── registry_index.json       ← 文本目录（含标题、字数等）
├── content/                  ← 各文本正文 JSON
│   ├── static-classic-sentences.json  ← 经典中文短句（静态）
│   ├── jisubei.json                   ← 极速杯每日挑战（每日更新）
│   └── ...
├── scripts/                  ← CI 抓取脚本
│   ├── fetch_daily.py
│   ├── fetch_jisubei.py
│   └── gen_index.py          ← 自动扫描 content/ 生成索引
└── .github/workflows/
    ├── daily.yml             ← 每日 0 点 + 手动触发
    └── weekly-static.yml     ← 每周全量刷新
```

## 接入方式

配置你的客户端指向 CDN 即可使用：

```
primary_url = https://cdn.jsdelivr.net/gh/whynusn/open-typing-texts@main
```

客户端发起 HTTP GET：
- `/registry_index.json` — 获取文本目录
- `/content/{source_key}.json` — 获取单篇正文

## 文本文件 schema

```json
{
  "source_key": "static-classic-sentences",
  "title": "经典中文短句练习",
  "content": "春风又绿江南岸...",
  "metadata": {
    "description": "精选经典中文短句",
    "category": "static",
    "tags": ["经典", "短句"]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | `str` | ✅ | 唯一标识，与文件名一致（不含 `.json`） |
| `content` | `str` | ✅ | 正文内容 |
| `title` | `str` | ❌ | 显示标题 |
| `metadata` | `dict` | ❌ | 描述、分类、标签等扩展信息 |

## 索引文件 schema

`registry_index.json` 由 `gen_index.py` 自动生成：

```json
{
  "version": 1,
  "updated_at": "2026-07-05T00:00:00Z",
  "sources": [
    {
      "id": 1001,
      "source_key": "static-classic-sentences",
      "label": "经典中文短句",
      "description": "精选经典中文短句，适合中文打字练习",
      "category": "static",
      "charCount": 350,
      "update_freq": "static",
      "has_ranking": false
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `source_key` | `str` | 唯一标识，匹配 `content/{key}.json` |
| `label` | `str` | 显示标题 |
| `description` | `str` | 详细描述 |
| `category` | `str` | 分类（`static`/`daily`/`jisubei` 等） |
| `charCount` | `int` | 正文字符数（从 `content` 自动计算） |
| `update_freq` | `str` | 更新频率（`static`/`weekly`/`daily`） |
| `has_ranking` | `bool` | 是否支持排行榜 |

## 贡献方式

1. **添加新文本**：往 `content/` 放入 `{key}.json`，运行 `python scripts/gen_index.py` 更新索引，提交 PR
2. **添加自动抓取**：在 `scripts/` 写抓取脚本，在 `.github/workflows/` 配置定时任务，提交 PR
3. **手动触发**：GitHub Actions 页面 → `daily.yml` → Run workflow

## 安全模型

抓取脚本仅在 GitHub Actions CI 运行，输出纯 JSON。客户端只读不执行远程代码，无安全风险。

## 许可证

内容：[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/)
代码：MIT
