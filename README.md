# open-typing-texts

> 开源中文打字文本工具集。**本仓库不提供任何现成文本内容**，仅提供抓取脚本模板，用户须在本地自行运行脚本生成文本。

---

## 重要声明 / Disclaimer

**本仓库不提供、不分发、不托管任何文本内容。** `content/` 目录和相关工具使用用户自行抓取的数据。

使用者应自行确保其抓取行为符合目标网站的 robots.txt 协议、服务条款以及当地法律法规。使用本脚本产生的任何法律责任均由使用者自行承担，本仓库作者及贡献者概不负责。如不同意上述条款，请勿运行本脚本。

本仓库已禁用 GitHub Actions 自动抓取。所有脚本须在本地手动执行。

---

## 使用方式

### 1. 准备环境

```bash
pip install httpx
```

### 2. 运行脚本生成文本

```bash
python scripts/fetch_daily.py      # 抓取每日一文 → content/daily.json
python scripts/fetch_jisubei.py    # 抓取极速杯文本 → content/jisubei.py
```

### 3. 重建索引

```bash
python scripts/gen_index.py        # 扫描 content/ 生成 registry_index.json
```

### 4. 接入打字练习应用

客户端配置 CDN 地址指向本仓库（需要用户自行提供托管服务）：

```
primary_url = https://cdn.jsdelivr.net/gh/<your-username>/open-typing-texts@main
```

---

## 已包含的脚本

| 脚本 | 说明 | 目标源 |
|:---|:---|:---|
| `fetch_daily.py` | 每日短篇文本抓取 | 公开 API |
| `fetch_jisubei.py` | 极速杯文本抓取 | 赛文 API（需逆向加密协议） |
| `gen_index.py` | 索引生成器 | 读取 content/ 重建索引 |

---

## 如何添加新文本源

参见 [docs/SCRIPT_GUIDE.md](docs/SCRIPT_GUIDE.md)。

---

## 仓库结构

```
open-typing-texts/
├── scripts/
│   ├── fetch_daily.py         # 每日抓取脚本（用户本地运行）
│   ├── fetch_jisubei.py       # 极速杯抓取脚本
│   └── gen_index.py           # 索引生成工具
├── docs/
│   ├── SCRIPT_GUIDE.md        # 脚本编写教程
│   └── WORKFLOW_GUIDE.md      # 脚本运行指南
└── README.md                  # 本文件
```

---

## 许可证

代码：MIT

内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
