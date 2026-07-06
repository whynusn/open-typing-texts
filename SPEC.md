# OTT 数据格式规范

> 版本：v1 | 状态：stable

本文档定义了 Open Typing Texts (OTT) 仓库中 JSON 文件的结构规范。
任何兼容 OTT 标准的仓库或适配器均应遵循此格式。

---

## 目录

- [概述](#概述)
- [文件布局](#文件布局)
- [索引文件 `registry_index.json`](#索引文件-registry_indexjson)
- [内容文件 `content/{source_key}.json`](#内容文件-contentsource_keyjson)
- [字段定义](#字段定义)
- [扩展规则](#扩展规则)
- [示例](#示例)

---

## 概述

OTT 使用两个层级的 JSON 文件：

| 层级 | 文件 | 用途 |
|:---|:---|:---|
| **索引** | `registry_index.json` | 声明所有可用文本源及其元数据 |
| **内容** | `content/{source_key}.json` | 单篇文本的正文和元数据 |

客户端（如打字练习应用）先获取索引，再按需获取内容。

---

## 文件布局

```
<repository_root>/
├── registry_index.json       ← 索引（必须）
└── content/
    ├── {source_key_1}.json   ← 内容文件
    ├── {source_key_2}.json
    └── ...
```

- `source_key` 只含字母、数字、下划线（`[a-zA-Z0-9_]+`）
- 不含 `/` `.` `..` `\\`（防止路径穿越）
- 索引中声明的每个 `source_key` 必须对应一个 `content/{source_key}.json`

---

## 索引文件 `registry_index.json`

### 顶层结构

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `version` | `integer` | ✅ | 规范版本号，当前为 `1` |
| `updated_at` | `string` | ✅ | ISO 8601 UTC 时间戳 |
| `sources` | `array` | ✅ | 文本来源列表 |

### `sources[]` 条目

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | `string` | ✅ | 唯一标识，匹配文件名 |
| `label` | `string` | ✅ | 显示名称 |
| `description` | `string` | ❌ | 详细描述 |
| `charCount` | `integer` | ❌ | 正文字符数（用于 UI 展示） |
| `category` | `string` | ❌ | 分类（`daily`/`static`/`jisubei` 等） |
| `update_freq` | `string` | ❌ | 更新频率（`hourly`/`daily`/`weekly`/`static`） |

### 示例

```json
{
  "version": 1,
  "updated_at": "2026-07-06T00:00:00+00:00",
  "sources": [
    {
      "source_key": "daily",
      "label": "每日一文",
      "description": "每天更新的短篇中文文本",
      "charCount": 350,
      "category": "daily",
      "update_freq": "daily"
    },
    {
      "source_key": "classic_poems",
      "label": "经典诗词",
      "description": "唐诗宋词精选",
      "charCount": 560,
      "category": "static",
      "update_freq": "static"
    }
  ]
}
```

---

## 内容文件 `content/{source_key}.json`

### 顶层结构

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | `string` | ✅ | 必须与文件名一致 |
| `title` | `string` | ✅ | 文本标题 |
| `content` | `string` | ✅ | 正文内容（支持 `\n` 换行） |
| `metadata` | `object` | ❌ | 扩展元数据 |

### `metadata` 子字段

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `description` | `string` | ❌ | 描述（自由格式，建议使用正文摘要、来源信息或其他有助于理解文本的内容） |
| `category` | `string` | ❌ | 分类 |
| `tags` | `array[string]` | ❌ | 标签列表 |
| `date` | `string` | ❌ | 文本日期（ISO 8601） |
| `author` | `string` | ❌ | 原作者 |
| `source_url` | `string` | ❌ | 原始来源 URL |
| `license` | `string` | ❌ | 许可证（如 `CC0-1.0`） |

### 示例

```json
{
  "source_key": "daily",
  "title": "春日偶成",
  "content": "云淡风轻近午天，傍花随柳过前川。\n时人不识余心乐，将谓偷闲学少年。",
  "metadata": {
    "description": "宋代程颢的诗作",
    "category": "daily",
    "tags": ["古诗", "春天", "宋诗"],
    "date": "2026-07-06",
    "author": "程颢",
    "license": "CC0-1.0"
  }
}
```

---

## 字段定义

### `source_key`

- **类型**：`string`
- **必填**：是
- **约束**：`^[a-zA-Z0-9_]+$`
- **用途**：唯一标识，同时作为文件名（不含 `.json` 后缀）
- **示例**：`"daily"` `"classic_poems"` `"jisubei"`

### `content`

- **类型**：`string`
- **必填**：是
- **约束**：非空字符串
- **用途**：打字练习的正文
- **注意**：支持 `\n` 换行符；客户端应保留换行

### `title`

- **类型**：`string`
- **必填**：是
- **用途**：在 UI 中显示的标题

### `charCount`

- **类型**：`integer`
- **必填**：否
- **约束**：≥ 0
- **用途**：正文字符数，用于 UI 展示
- **注意**：应为 `content.length`（字符数，非字节数）

### `category`

- **类型**：`string`
- **必填**：否
- **用途**：文本分类，便于 UI 分组
- **推荐值**：`daily` / `weekly` / `static` / `jisubei` / `custom`

### `update_freq`

- **类型**：`string`
- **必填**：否
- **用途**：提示客户端更新频率
- **推荐值**：`hourly` / `daily` / `weekly` / `static`

---

## 扩展规则

### 自定义字段

`metadata` 对象内可添加任意自定义字段，客户端应忽略不认识的字段。

```json
{
  "metadata": {
    "difficulty": "medium",
    "language": "zh-CN",
    "custom_field": "任意值"
  }
}
```

### 版本演进

- `version: 1` — 当前版本
- 未来版本保持向后兼容：新增字段均为可选，不删除现有字段

### 编码

- 所有 JSON 文件使用 **UTF-8** 编码
- 换行符使用 `\n`（LF），不使用 `\r\n`（CRLF）
- JSON 格式化使用 2 空格缩进

### 原子写入

脚本写入文件时应使用"临时文件 + 重命名"模式，避免客户端读到半写状态：

```python
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
tmp.replace(path)
```

---

## 示例

### 最小可用示例

索引：
```jsonc
{
  "version": 1,
  "updated_at": "2026-07-06T00:00:00+00:00",
  "sources": [{
    "source_key": "hello",
    "label": "你好",
    "charCount": 5
  }]
}
```

内容：
```jsonc
{
  "source_key": "hello",
  "title": "示例",
  "content": "你好世界"
}
```

### 完整示例

索引：
```jsonc
{
  "version": 1,
  "updated_at": "2026-07-06T00:00:00+00:00",
  "sources": [
    {
      "source_key": "tang_poems",
      "label": "唐诗三百首",
      "description": "精选唐代诗歌",
      "charCount": 12000,
      "category": "static",
      "update_freq": "static"
    }
  ]
}
```

内容：
```jsonc
{
  "source_key": "tang_poems",
  "title": "静夜思",
  "content": "床前明月光，疑是地上霜。\n举头望明月，低头思故乡。",
  "metadata": {
    "description": "李白五言绝句",
    "category": "static",
    "tags": ["唐诗", "李白", "思乡"],
    "author": "李白",
    "license": "CC0-1.0"
  }
}
```
