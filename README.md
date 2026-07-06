# open-typing-texts

> 开源中文打字文本工具集。**本仓库不提供任何现成文本内容**，仅提供抓取脚本模板，用户须在本地自行运行脚本生成文本。

---

## 重要声明 / Disclaimer

**本仓库不提供、不分发、不托管任何文本内容。**

使用者应自行确保其抓取行为符合目标网站的 robots.txt 协议、服务条款以及当地法律法规。使用本脚本产生的任何法律责任均由使用者自行承担，本仓库作者及贡献者概不负责。如不同意上述条款，请勿运行本脚本。

---

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/whynusn/open-typing-texts.git
cd open-typing-texts

# 2. 安装
pip install -e ".[fetch,watch]"

# 3. 一键启动（自动抓取 + WEB 服务 + 热更新）
ott-adapter

# 4. 浏览器打开 http://127.0.0.1:18888 查看文本
```

typetype 配置（`~/.config/typetype/config.json`）：
```json
{"registry": {"primary_url": "http://127.0.0.1:18888"}}
```

---

## CLI 参数

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--port` | `18888` | 监听端口 |
| `--data-dir` | `.` | 数据目录 |
| `--no-fetch` | false | 跳过首次抓取 |
| `--refresh` | `once` | 定时抓取：`once` / `hourly` / `daily` |

---

## 核心特性

### 一键启动

`ott-adapter` 一条命令完成全部操作：
1. 运行所有 `fetch_*.py` 脚本抓取文本
2. 扫描 `content/` 目录生成索引
3. 启动 HTTP 服务（JSON API + Web UI）
4. 监控 `scripts/` 目录，发现新脚本自动运行

### 热更新

新增 `fetch_xxx.py` 脚本后无需重启，适配器自动检测并运行：

```bash
# 新增脚本后无需任何操作
cp my_fetcher.py scripts/fetch_mytext.py
# → 适配器自动检测 → 运行 → 更新索引
```

使用 [watchdog](https://pypi.org/project/watchdog/) 事件驱动（零延迟），未安装时自动回退轮询。

### Web UI

浏览器访问 `http://127.0.0.1:18888` 可直接浏览所有文本，无需安装 typetype。

### JSON API

| 端点 | 说明 |
|:---|:---|
| `GET /registry_index.json` | 获取文本来源目录 |
| `GET /content/{key}.json` | 获取单篇正文 |

---

## 添加自定义文本源

### 快速开始

```bash
# 1. 复制模板
cp scripts/fetch_daily.py scripts/fetch_mysource.py

# 2. 编辑脚本（修改 SOURCE_KEY 和抓取逻辑）
vim scripts/fetch_mysource.py

# 3. 测试
python scripts/fetch_mysource.py

# 4. 启动适配器（自动检测新脚本）
ott-adapter
```

### 内容文件格式

脚本输出 JSON 格式：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文内容（必填）",
  "metadata": {
    "description": "描述",
    "category": "daily",
    "tags": ["标签"]
  }
}
```

**必填字段**：`source_key`、`content`

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 仓库结构

```
open-typing-texts/
├── ott_adapter/             ← WEB 服务器包
│   ├── __init__.py
│   ├── __main__.py          ← CLI 入口
│   ├── server.py            ← HTTP 服务 + Web UI
│   └── scheduler.py         ← 抓取调度 + 热更新
├── scripts/
│   ├── fetch_daily.py       ← 每日一文
│   ├── fetch_jisubei.py     ← 极速杯
│   └── gen_index.py         ← 索引生成（可选）
├── CONTRIBUTING.md          ← 贡献指南
└── pyproject.toml
```

---

## 依赖

```bash
# 基础（仅适配器）
pip install -e .

# 抓取依赖（运行 fetch 脚本需要）
pip install -e ".[fetch]"

# watchdog（热更新事件驱动，推荐）
pip install -e ".[watch]"

# 全部
pip install -e ".[fetch,watch]"
```

| 依赖 | 必需 | 说明 |
|:---|:---|:---|
| `httpx` | 抓取时需要 | HTTP 客户端 |
| `pycryptodome` | 极速杯需要 | AES 加密 |
| `watchdog` | 推荐 | 热更新事件驱动 |

---

## 许可证

代码：MIT  
内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
