# open-typing-texts

> 开源中文打字文本库。为中文跟打器提供每日更新的练习文本，由 GitHub Actions 自动抓取、客户端只读使用。

任何打字练习应用均可接入：配置一个 CDN 地址，即可获取全部文本。

---

## 1. 快速开始（使用者）

在你的跟打器配置中添加：

```json
{
  "registry": {
    "primary_url": "https://cdn.jsdelivr.net/gh/whynusn/open-typing-texts@main",
    "mirror_url": "https://raw.githubusercontent.com/whynusn/open-typing-texts/main",
    "cache_ttl_seconds": 3600,
    "max_content_bytes": 1048576
  }
}
```

客户端发起两次 HTTP GET 即可使用：

| 请求 | 说明 |
|:---|:---|
| `GET /registry_index.json` | 获取文本目录（含标题、字数等元数据） |
| `GET /content/{source_key}.json` | 获取单篇正文 |

### 客户端接入示例

```python
from backend.integration.registry_text_provider import RegistryTextProvider
from backend.config.runtime_config import RegistryConfig

provider = RegistryTextProvider(
    config=RegistryConfig(
        primary_url="https://cdn.jsdelivr.net/gh/whynusn/open-typing-texts@main",
        mirror_url="https://raw.githubusercontent.com/whynusn/open-typing-texts/main",
    ),
    cache_dir=Path.home() / ".cache" / "typetype" / "registry",
)

# 获取文本源目录
catalog = provider.get_catalog()

# 获取单篇文本
text = provider.fetch_text_by_key("jisubei")
```

---

## 2. 数据架构

```
用户跟打器
  │  HTTP GET（只读）
  ▼
┌─────────────────────────────────────────────────────┐
│  CDN（jsDelivr / GitHub raw）                       │
│  registry_index.json  ← 文本目录（轻量）             │
│  content/{key}.json   ← 单篇正文（按需加载）         │
└─────────────────────────────────────────────────────┘
         ↑
         │  GitHub Actions CI（每日自动抓取）
         │
┌─────────────────────────────────────────────────────┐
│  scripts/fetch_*.py   ← 各文本源抓取脚本             │
│  scripts/gen_index.py ← 索引生成器                   │
└─────────────────────────────────────────────────────┘
```

**设计原则**：CI 是唯一的写入者，客户端只读不写。

---

## 3. 数据规格

### 3.1 文本文件 `content/{source_key}.json`

```json
{
  "source_key": "jisubei",
  "title": "大模型内容同质化",
  "content": "正文内容...",
  "text_id": null,
  "metadata": {
    "description": "极速杯每日挑战",
    "category": "daily",
    "tags": ["极速杯"]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | `string` | ✅ | 唯一标识，与文件名一致（不含 `.json`） |
| `content` | `string` | ✅ | 正文内容，支持 `\n` 换行 |
| `title` | `string` | ❌ | 显示标题（索引缺省时用 `source_key`，正文缺省为空） |
| `metadata` | `object` | ❌ | 扩展元数据（描述、分类、标签等） |

### 3.2 索引文件 `registry_index.json`

由 `gen_index.py` 自动扫描 `content/` 生成，贡献者无需手动维护：

```json
{
  "version": 1,
  "updated_at": "2026-07-05T00:00:00Z",
  "sources": [
    {
      "id": 0,
      "source_key": "jisubei",
      "label": "极速杯每日挑战",
      "description": "...",
      "category": "daily",
      "charCount": 437,
      "update_freq": "daily",
      "has_ranking": false
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `source_key` | `string` | 唯一标识，匹配 `content/{key}.json` |
| `label` | `string` | 显示标题 |
| `description` | `string` | 详细描述 |
| `category` | `string` | 分类（`static`/`daily`/`jisubei` 等） |
| `charCount` | `number` | 正文字符数（自动计算） |
| `update_freq` | `string` | 更新频率（`static`/`weekly`/`daily`） |

### 3.3 文件体积限制

| 限制 | 值 | 说明 |
|:---|:---|:---|
| 建议单文件上限 | **1 MB** | 超过 1 MB `gen_index.py` 打印警告 |
| 绝对单文件上限 | **100 MB** | 超过 100 MB 跳过该文件（GitHub 硬性限制） |
| `text_id` | `number \| null` | 用于成绩提交排行榜（纯文本源留 `null`） |

---

## 4. 贡献指南

### 4.1 添加静态文本（无代码）

1. 在 `content/` 目录下创建 `{source_key}.json`，遵循 §3.1 schema
2. 本地运行 `python scripts/gen_index.py` 验证格式正确
3. 提交 PR，等待合并后 CDN 自动生效

### 4.2 添加动态抓取脚本

适合需要定期从外部源拉取最新文本的场景（如每日一文、极速杯）。

详见 **[docs/SCRIPT_GUIDE.md](docs/SCRIPT_GUIDE.md)**，包含：
- 脚本契约（函数签名、输出格式、错误处理）
- 完整示例模板（带注释，可直接复制修改）
- 频率控制（脚本内部通过文件 mtime 判断是否需要跳过）
- 本地测试方法
- PR 提交清单

### 4.3 配置 workflow 定时任务

所有动态脚本统一在 `.github/workflows/daily.yml` 中调度。CI 每日 0:00 UTC 自动运行，各脚本内部判断是否需要真正更新。

详见 **[docs/WORKFLOW_GUIDE.md](docs/WORKFLOW_GUIDE.md)**，包含：
- cron 语法详解（每日/每周/每 N 天）
- 如何添加新的脚本调用
- 手动触发配置（`workflow_dispatch`）
- 容错与防并发

---

## 5. 安全模型

- 抓取脚本**仅在 GitHub Actions CI 运行**，输出纯 JSON
- 客户端只通过 `HTTP GET` 拉取 JSON，**从不执行任何远程代码**
- `source_key` 有白名单验证（`RegistryTextProvider._validate_source_key`），禁止 `..` 路径穿越
- 客户端有文件大小限制（`max_content_bytes`，默认 1 MB）
- 写入使用原子操作（`tmp + replace`），避免半写状态

---

## 6. 许可证

- 文本内容：[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/)
- 代码/脚本：MIT
