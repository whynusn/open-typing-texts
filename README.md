# open-typing-texts

> 开源打字文本源标准。**本仓库不提供任何文本内容**，仅提供抓取脚本模板和本地适配器，用户自行运行生成文本。

---

## 目录

- [重要声明](#重要声明)
- [快速开始](#快速开始)
- [核心特性](#核心特性)
- [添加文本源](#添加文本源)
- [依赖](#依赖)
- [贡献](#贡献)
- [仓库结构](#仓库结构)
- [许可证](#许可证)

---

## 重要声明

本仓库不提供、不分发、不托管任何文本内容。

使用者应自行确保其抓取行为符合目标网站的 robots.txt 协议、服务条款以及当地法律法规。使用本脚本产生的任何法律责任均由使用者自行承担，本仓库作者及贡献者概不负责。如不同意上述条款，请勿运行本脚本。

---

## 快速开始

```bash
git clone https://github.com/whynusn/open-typing-texts.git
cd open-typing-texts

pip install -e ".[fetch,watch]"

ott-adapter    # 一键启动：自动抓取 + WEB 服务 + 热更新
```

浏览器打开 <http://127.0.0.1:18888> 即可浏览文本。

任何支持"配置文本源 HTTP 地址"的打字练习应用均可接入：

```json
{"registry": {"primary_url": "http://127.0.0.1:18888"}}
```

---

## 核心特性

- **一键启动** — `ott-adapter` 一条命令完成抓取、索引、服务
- **热更新** — 新增 `fetch_xxx.py` 脚本无需重启，自动检测运行（watchdog 事件驱动）
- **Web UI** — 浏览器访问 `http://127.0.0.1:18888` 直接浏览
- **JSON API** — `GET /registry_index.json` 获取目录，`GET /content/{key}.json` 获取正文
- **幂等安全** — 重复运行不产生副作用，失败不覆盖已有内容

---

## 添加文本源

```bash
# 复制模板并编辑
cp scripts/fetch_daily.py scripts/fetch_mysource.py
vim scripts/fetch_mysource.py

# 验证输出格式
python scripts/fetch_mysource.py
# → 生成 content/mysource.json

# 重启适配器即可看到新文本
ott-adapter
```

输出 JSON 格式：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文内容（必填）",
  "metadata": {"description": "描述", "category": "daily", "tags": ["标签"]}
}
```

**必填字段**：`source_key`、`content`

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 依赖

```bash
pip install -e .              # 仅适配器
pip install -e ".[fetch]"     # + 抓取脚本依赖
pip install -e ".[watch]"     # + watchdog 事件驱动热更新
pip install -e ".[fetch,watch]"  # 全部
```

| 依赖 | 用途 |
|:---|:---|
| `httpx` | HTTP 客户端（抓取脚本需要） |
| `pycryptodome` | AES 加密（极速杯脚本需要） |
| `watchdog` | 热更新事件驱动（推荐） |

---

## 贡献

欢迎贡献新文本源！详见 [CONTRIBUTING.md](CONTRIBUTING.md)，包含：
- 编写和测试脚本的完整步骤
- 输出格式规范
- 从 fork 到 PR 的提交流程

```bash
git checkout -b add-mysource
git add scripts/fetch_mysource.py
git commit -m "feat: 添加 mysource 文本源"
git push origin add-mysource
# → 发起 Pull Request
```

---

## 仓库结构

```
open-typing-texts/
├── ott_adapter/             ← WEB 服务器包
│   ├── __init__.py
│   ├── __main__.py          ← CLI 入口：ott-adapter
│   ├── server.py            ← HTTP 服务 + Web UI
│   └── scheduler.py         ← 抓取调度 + 热更新
├── scripts/
│   ├── fetch_daily.py       ← 每日文本（公开 API）
│   ├── fetch_jisubei.py     ← 极速杯
│   └── gen_index.py         ← 生成 registry_index.json
├── CONTRIBUTING.md          ← 贡献指南
└── pyproject.toml
```

### CLI 参数

```
ott-adapter [--port 18888] [--data-dir .] [--no-fetch] [--refresh once|hourly|daily]
```

### JSON API

| 端点 | 说明 |
|:---|:---|
| `GET /` | Web UI（浏览器浏览） |
| `GET /registry_index.json` | 文本来源目录 |
| `GET /content/{key}.json` | 单篇正文 |

---

## 许可证

代码：MIT  
内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
