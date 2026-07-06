# open-typing-texts

> 开源打字文本源标准。**本仓库不提供任何文本内容**，仅提供抓取脚本模板和本地适配器，用户自行运行生成文本。

---

## 目录

- [重要声明](#重要声明)
- [快速开始](#快速开始)
- [核心特性](#核心特性)
- [向本地添加新文本源](#向本地添加新文本源)
- [向 OTT 贡献新脚本](#向-ott-贡献新脚本)
- [依赖](#依赖)
- [仓库结构](#仓库结构)
- [API 参考](#api-参考)
- [CLI 参考](#cli-参考)
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

ott-adapter
```

浏览器打开 <http://127.0.0.1:18888> 即可浏览文本。

---

## 核心特性

- **一键启动** — 自动抓取、建立索引、启动 WEB 服务
- **热更新** — 新增 `fetch_xxx.py` 自动检测运行（watchdog 事件驱动）
- **Web UI** — 浏览器直接浏览文本
- **JSON API** — RESTful 接口，任何 HTTP 客户端均可调用
- **幂等安全** — 重复运行无副作用，失败不覆盖已有内容

---

## 向本地添加新文本源

只需三步，仅你自己使用：

```bash
# 1. 复制模板
cp scripts/fetch_daily.py scripts/fetch_mysource.py

# 2. 编辑（修改 SOURCE_KEY 和抓取逻辑）
vim scripts/fetch_mysource.py

# 3. 运行并启动
python scripts/fetch_mysource.py
ott-adapter
```

输出 JSON 由脚本写入 `content/mysource.json`：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文（必填）",
  "metadata": {"description": "描述", "category": "daily", "tags": ["标签"]}
}
```

**必填字段**：`source_key`（字母数字下划线）、`content`（字符串）

---

## 向 OTT 贡献新脚本

希望让更多人使用你的文本源？提交 Pull Request：

### 快速提交

```bash
# 1. Fork 本仓库后克隆
# 2. 创建分支
git checkout -b add-mysource

# 3. 提交脚本（不需要提交 content/）
git add scripts/fetch_mysource.py
git commit -m "feat: 添加 mysource 文本源"
git push origin add-mysource

# 4. 在 GitHub 发起 Pull Request
```

### 贡献要求

- 脚本须含 `#!/usr/bin/env python3` 和 `def main()` 入口
- `source_key` 只含字母、数字、下划线，不含 `/` `.` `..` `\\`
- 失败时不写入文件，保留旧内容
- 输出 JSON 须包含 `source_key` 和 `content` 字段

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 依赖

```bash
pip install -e .                 # 仅适配器（无网络功能）
pip install -e ".[fetch]"        # + 抓取脚本所需的 httpx/pycryptodome
pip install -e ".[watch]"        # + watchdog 事件驱动热更新
pip install -e ".[fetch,watch]"  # 全部安装
```

---

## 仓库结构

```
open-typing-texts/
├── ott_adapter/             ← 适配器 Python 包
│   ├── __init__.py
│   ├── __main__.py          ← CLI 入口
│   ├── server.py            ← HTTP 服务 + Web UI
│   └── scheduler.py         ← 抓取调度 + 热更新
├── scripts/
│   ├── fetch_daily.py
│   ├── fetch_jisubei.py
│   └── gen_index.py
├── CONTRIBUTING.md
└── pyproject.toml
```

---

## API 参考

Base URL: `http://127.0.0.1:18888`

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/` | Web UI（浏览器浏览） |
| `GET` | `/registry_index.json` | 文本来源目录 |
| `GET` | `/content/{source_key}.json` | 单篇正文 |

`registry_index.json` 响应：

```json
{
  "version": 1,
  "updated_at": "2026-07-06T00:00:00Z",
  "sources": [
    {
      "source_key": "daily",
      "label": "每日一文",
      "description": "...",
      "charCount": 350,
      "category": "daily",
      "update_freq": "daily"
    }
  ]
}
```

`content/{key}.json` 响应：

```json
{
  "source_key": "daily",
  "title": "每日一文",
  "content": "正文内容...",
  "metadata": {"description": "...", "category": "daily", "tags": ["..."]}
}
```

---

## CLI 参考

```
ott-adapter [--port 18888] [--data-dir .] [--no-fetch] [--refresh once|hourly|daily]
```

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--port` | `18888` | HTTP 监听端口 |
| `--data-dir` | `.` | OTT 仓库根目录 |
| `--no-fetch` | false | 跳过首次抓取 |
| `--refresh` | `once` | 定时抓取频率 |

---

## 许可证

代码：MIT  
内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
