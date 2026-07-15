# OTT Legacy Compatibility Format

> 状态：compatibility | 范围：旧 `registry_index.json` / `content/{source_key}.json` 布局

本文档记录 reference adapter 继续支持的历史输入/兼容格式。新客户端应优先使用 [OTT_SPEC.md](OTT_SPEC.md) 定义的 OTT Core v1 Service Profile 或 Static Profile。

`registry_index.json version: 2` 是历史 adapter index schema，不是 OTT v2。本仓库当前公开协议版本是 OTT Core `1.0`。

## 文件布局

```text
<repository_root>/
├── registry_index.json
└── content/
    ├── {source_key_1}.json
    └── {source_key_2}.json
```

`source_key` 只含字母、数字、下划线（`[a-zA-Z0-9_]+`），不得包含 `/`、`.`、`..` 或 `\`。

## `registry_index.json`

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `version` | integer | 是 | 历史 index schema 版本 |
| `updated_at` | string | 是 | ISO 8601 时间戳 |
| `sources` | array | 是 | 文本来源列表 |

### `sources[]`

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | string | 是 | 唯一标识，匹配 `content/{source_key}.json` |
| `label` | string | 是 | 显示名称 |
| `description` | string | 否 | 描述 |
| `charCount` | integer | 否 | 最新正文字符数 |
| `category` | string | 否 | 分类 |
| `update_freq` | string | 否 | 更新频率 |

## `content/{source_key}.json`

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | string | 是 | 必须与文件名一致 |
| `title` | string | 是 | 最新条目标题 |
| `content` | string | 是 | 最新条目正文 |
| `metadata` | object | 否 | 最新条目元数据 |
| `entries` | array | 否 | 历史条目列表 |

### `entries[]`

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `entry_id` | string | 否 | 建议持久化的稳定文本身份 |
| `revision_id` | string | 否 | 当前文本修订身份 |
| `title` | string | 是 | 条目标题 |
| `content` | string | 是 | 条目正文 |
| `metadata` | object | 否 | 条目元数据 |
| `fetched_at` | string | 否 | 抓取时间 |

如果未提供 `entries[]`，adapter 会从顶层 `title` / `content` 构建一个条目。顶层 `title` / `content` 继续指向最新条目，以兼容旧客户端。

## Normalization

reference adapter 会将 legacy content file 规范化为 OTT Core v1 entry：

- `entry_id` 缺失时从显式元数据、来源、标题或内容 hash 派生。
- `revision_id` 缺失时从 `entry_id` 与 `content_hash` 派生。
- `content_hash` 使用 `sha256:<hex>`。
- `char_count <= 4096` 时生成 inline entry。
- `char_count > 4096` 时生成 segmented entry，并写入 `segments/{revision_id}/{index}.txt`。
- `/ott/v1/entries` 与 `/entries.json` 只返回 summary，不返回正文。
- segmented detail 不返回全文正文。

## 示例

```json
{
  "source_key": "daily",
  "title": "春日偶成",
  "content": "云淡风轻近午天，傍花随柳过前川。",
  "metadata": {
    "description": "宋代程颢的诗作",
    "category": "poem",
    "tags": ["诗词"],
    "license": "user-provided"
  }
}
```
