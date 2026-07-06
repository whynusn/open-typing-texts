# open-typing-texts

> 开源打字文本源标准。**本仓库不提供任何文本内容**，仅提供抓取脚本模板和本地适配器，用户自行运行生成文本。

---

## 重要声明

本仓库不提供、不分发、不托管任何文本内容。

使用者应自行确保其抓取行为符合目标网站的 robots.txt 协议、服务条款以及当地法律法规。使用本脚本产生的任何法律责任均由使用者自行承担，本仓库作者及贡献者概不负责。如不同意上述条款，请勿运行本脚本。

---

## 快速开始

```bash
# 克隆
git clone https://github.com/whynusn/open-typing-texts.git
cd open-typing-texts

# 安装（二选一）
pip install -e .          # pip 方式
# 或
uv sync                   # uv 方式

# 一键启动（自动抓取 + WEB 服务 + 热更新）
ott-adapter               # pip 入口
# 或
uv run ott-adapter        # uv 入口

# 浏览器打开 http://127.0.0.1:18888
```

typetype 配置（`~/.config/typetype/config.json`）：
```json
{"registry": {"primary_url": "http://127.0.0.1:18888"}}
```

---

## 核心特性

- **一键启动** — 自动抓取、建立索引、启动 WEB 服务
- **热更新** — 新增 `fetch_xxx.py` 自动检测运行（watchdog 事件驱动）
- **Web UI** — 浏览器直接浏览文本
- **JSON API** — RESTful 接口，任何 HTTP 客户端均可调用
- **幂等安全** — 重复运行无副作用，失败不覆盖已有内容

---

## 向本地添加新文本源

```bash
# 复制模板并编辑
cp scripts/fetch_daily.py scripts/fetch_mysource.py
vim scripts/fetch_mysource.py

# 验证输出
python scripts/fetch_mysource.py

# 重启适配器即可看到新文本
ott-adapter
```

输出 JSON 格式：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文（必填）",
  "metadata": {"description": "描述", "category": "daily", "tags": ["标签"]}
}
```

**必填字段**：`source_key`（字母数字下划线）、`content`（字符串）

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 向 OTT 贡献新脚本

```bash
git checkout -b add-mysource
git add scripts/fetch_mysource.py
git commit -m "feat: 添加 mysource 文本源"
git push origin add-mysource
# → 发起 Pull Request
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

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

## API 参考

Base URL: `http://127.0.0.1:18888`

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/` | Web UI（浏览器浏览） |
| `GET` | `/registry_index.json` | 文本来源目录 |
| `GET` | `/content/{source_key}.json` | 单篇正文 |

---

## 仓库结构

```
open-typing-texts/
├── ott_adapter/             ← 适配器 Python 包
│   ├── __init__.py
│   ├── __main__.py          ← CLI 入口：ott-adapter
│   ├── server.py            ← HTTP 服务 + Web UI
│   └── scheduler.py         ← 抓取调度 + 热更新
├── scripts/
│   ├── fetch_daily.py       ← 每日文本
│   ├── fetch_jisubei.py     ← 极速杯
│   └── gen_index.py         ← 索引生成
├── CONTRIBUTING.md          ← 贡献指南
├── SPEC.md                  ← 数据格式规范
└── pyproject.toml
```

---

## 许可证

代码：MIT  
内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
