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
git clone https://github.com/<your-username>/open-typing-texts.git
cd open-typing-texts

# 2. 安装
pip install -e ".[fetch]"

# 3. 一键启动（自动抓取 + WEB 服务 + 热更新）
ott-adapter

# 4. 浏览器打开 http://127.0.0.1:18888 查看文本
```

typetype 配置：
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
| `--self-host` | 无 | 自托管：`hourly` / `daily`（自动 pull + fetch + push） |
| `--hot-reload-interval` | `30` | 脚本目录热更新检测间隔（秒） |

---

## 核心特性

### 热更新

适配器每 30 秒扫描 `scripts/` 目录一次。新增 `fetch_xxx.py` 脚本后自动抓取并重建索引，无需重启。

```bash
# 新增脚本后无需任何操作，适配器自动发现并运行
cp my_fetcher.py scripts/fetch_mytext.py
# → 适配器自动检测 → 运行 → 更新索引
```

### 自托管模式

自动拉取最新脚本 → 抓取 → 提交 → 推送，无需手动 git 操作。

```bash
# 初始化（仅需一次）
git init
git remote add origin https://github.com/<you>/open-typing-texts.git

# 启动自托管
ott-adapter --self-host daily
```

每次循环：`git pull --rebase` → 运行所有 `fetch_*.py` → `git add` → `git commit` → `git push`

### Web UI

浏览器访问 `http://127.0.0.1:18888` 可直接浏览所有文本，无需安装 typetype。

---

## 添加自定义文本源

1. 在 `scripts/` 下新建 `fetch_xxx.py`（参考 `fetch_daily.py` 模板）
2. 适配器自动检测并运行（约 30 秒内）

输出格式：
```json
{
  "source_key": "mytext",
  "title": "我的文本",
  "content": "正文内容...",
  "metadata": {"description": "描述", "category": "daily", "tags": ["标签"]}
}
```

---

## 仓库结构

```
open-typing-texts/
├── ott_adapter/             ← WEB 服务器包
│   ├── __main__.py          ← CLI 入口
│   ├── server.py            ← HTTP 服务 + Web UI
│   └── scheduler.py         ← 抓取调度 + 热更新 + 自托管
├── scripts/
│   ├── fetch_daily.py       ← 每日一文
│   ├── fetch_jisubei.py     ← 极速杯
│   └── gen_index.py         ← 索引生成（可选，scheduler 内置）
└── pyproject.toml
```

---

## 许可证

代码：MIT  
内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
