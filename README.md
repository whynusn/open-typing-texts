# open-typing-texts

> OTT Core v1 标准与参考适配器。**本仓库不提供、不分发、不托管任何文本内容**；用户在本地运行脚本生成数据，并通过只读 OTT 协议供打字客户端读取。

## 重要声明

本仓库不提供、不分发、不托管任何文本内容。

使用者应自行确保其抓取行为符合目标网站的 robots.txt 协议、服务条款以及当地法律法规。使用本脚本产生的任何法律责任均由使用者自行承担，本仓库作者及贡献者概不负责。如不同意上述条款，请勿运行本脚本。

## 快速开始

```bash
git clone https://github.com/whynusn/open-typing-texts.git
cd open-typing-texts
uv sync
uv run ott-adapter
```

浏览器打开 <http://127.0.0.1:18888> 查看本地管理界面。

typetype 配置（`~/.config/typetype/config.json`）：

```json
{"registry": {"primary_url": "http://127.0.0.1:18888"}}
```

## 标准边界

OTT Core v1 只定义客户端只读分发协议：source、entry summary、entry detail、segment。抓取脚本、本地存储、管理 API、Web UI 都是参考适配器能力，不是打字客户端必须依赖的核心协议。

| 文档 | 职责 |
|:---|:---|
| [OTT_SPEC.md](OTT_SPEC.md) | OTT Core v1 权威规范：Service Profile、Static Profile、Admin Profile |
| [LEGACY_SPEC.md](LEGACY_SPEC.md) | 旧 `registry_index.json` / `content/{source_key}.json` 兼容格式 |
| [COMPATIBILITY.md](COMPATIBILITY.md) | 兼容矩阵与 canonical fixture pack |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 脚本贡献与本地验证流程 |
| [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) | 发布前兼容与 CI 边界检查 |

`registry_index.json version: 2` 是历史 adapter index schema，不是 OTT v2。本仓库当前公开协议版本是 OTT Core `1.0`，HTTP 服务路径为 `/ott/v1`。

## 核心特性

- OTT Core v1 Service Profile：`/ott/v1/*`
- OTT Static Profile：`/ott.json`、`/sources.json`、`/entries.json`、`/entries/{entry_id}.json`、`/segments/{revision_id}/{index}.txt`
- 本地 adapter Admin Profile：`/ott-admin/v1/*`
- 大文本自动按 server-defined segment 分发，小文本以内联正文分发
- 热更新、定时抓取、本地 Web UI
- legacy registry/content 路径继续兼容旧客户端

## 向本地添加新文本源

脚本可以先生成 legacy-compatible content file；adapter 会把它规范化为 OTT Core v1 entry，并生成 Service/Profile 与 Static Profile。

```bash
cp scripts/fetch_poem.py scripts/fetch_mysource.py
vim scripts/fetch_mysource.py
python scripts/fetch_mysource.py
uv run ott-adapter validate-script scripts/fetch_mysource.py
uv run ott-adapter validate content/mysource.json
uv run ott-adapter
```

最小可规范化输入：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文",
  "metadata": {
    "description": "描述",
    "category": "daily",
    "tags": ["标签"]
  }
}
```

发布内容建议持久化显式 `entry_id`；未提供时 reference adapter 会从来源、标题或正文 hash 派生稳定 ID。长文本不需要手工分段，adapter 会根据 Core v1 规则生成 segmented entry 和 segment 文件。

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## CLI 参考

```bash
ott-adapter [--port 18888] [--data-dir .] [--fetch] [--refresh once|hourly|daily]
ott-adapter validate content/mysource.json
ott-adapter validate --data-dir .
ott-adapter validate --static-profile .
ott-adapter validate-script scripts/fetch_mysource.py [--run]
```

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--port` | `18888` | HTTP 监听端口 |
| `--data-dir` | `.` | OTT 数据目录 |
| `--fetch` | false | 启动时运行所有 `scripts/fetch_*.py` |
| `--refresh` | `daily` | 后台刷新频率 |

## API 参考

Base URL: `http://127.0.0.1:18888`

### 推荐：OTT Core v1 Service Profile

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/ott/v1/capabilities` | 协议与能力发现 |
| `GET` | `/ott/v1/sources` | 来源列表 |
| `GET` | `/ott/v1/entries?source_key=&page=&limit=&q=` | summary-only 条目列表 |
| `GET` | `/ott/v1/entries/{entry_id}` | 条目详情 |
| `GET` | `/ott/v1/entries/{entry_id}/revisions/{revision_id}/segments/{index}` | 单个服务端定义分段 |

### 推荐：OTT Static Profile

| 路径 | 说明 |
|:---|:---|
| `/ott.json` | 静态 profile manifest |
| `/sources.json` | 静态来源列表 |
| `/entries.json` | summary-only 条目列表 |
| `/entries/{entry_id}.json` | 条目详情 |
| `/segments/{revision_id}/{index}.txt` | 分段正文 |

### Adapter 管理面

| 路径 | 说明 |
|:---|:---|
| `/` | 本地 Web UI |
| `/ott-admin/v1/*` | adapter 管理 API：脚本、调度、刷新、Web UI 数据 |

### Legacy 兼容路径

| 路径 | 状态 |
|:---|:---|
| `/registry_index.json` | 兼容旧客户端，不是推荐 Core v1 入口 |
| `/content/{source_key}.json` | 兼容旧客户端，可能包含全文 |
| `/api/*` | adapter-private / legacy alias，新客户端不要依赖 |

## 仓库结构

```text
open-typing-texts/
├── ott_adapter/             # adapter Python 包
│   ├── __main__.py          # CLI 入口：ott-adapter
│   ├── ott_core.py          # Core v1 normalize/static profile helpers
│   ├── server.py            # HTTP 服务 + Web UI
│   └── scheduler.py         # 抓取调度 + 热更新
├── scripts/
│   ├── fetch_poem.py        # 示例脚本
│   ├── fetch_jisubei.py     # 示例脚本
│   └── gen_index.py         # legacy index 生成
├── OTT_SPEC.md              # Core v1 权威规范
├── LEGACY_SPEC.md           # legacy 兼容格式
├── CONTRIBUTING.md          # 贡献指南
└── pyproject.toml
```

## CI 与抓取边界

项目 CI 不运行真实抓取脚本，不访问第三方文本来源。CI 只验证无网络 fixtures、schema/validator、转换函数和静态安全规则。`validate-script --run` 只能由使用者或贡献者在本机主动运行。

## 许可证

代码：MIT  
内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
