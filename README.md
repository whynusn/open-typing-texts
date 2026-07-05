# open-typing-texts

> 开源中文打字文本工具集。**本仓库不提供任何现成文本内容**，仅提供抓取脚本模板，用户须在本地自行运行脚本生成文本。

---

## 重要声明 / Disclaimer

**本仓库不提供、不分发、不托管任何文本内容。** `content/` 目录和相关工具使用用户自行抓取的数据。

使用者应自行确保其抓取行为符合目标网站的 robots.txt 协议、服务条款以及当地法律法规。使用本脚本产生的任何法律责任均由使用者自行承担，本仓库作者及贡献者概不负责。如不同意上述条款，请勿运行本脚本。

本仓库已禁用 GitHub Actions 自动抓取。所有脚本须在本地手动执行。

---

## 使用方式

### 方式一：本地适配器（推荐）

安装适配器后，typetype 等跟打器可直接通过 `http://127.0.0.1:18888` 读取本地文本，无需任何外部 CDN。

```bash
# 1. 克隆仓库
git clone https://github.com/<your-username>/open-typing-texts.git
cd open-typing-texts

# 2. 安装适配器
pip install -e .

# 3. 安装抓取依赖
pip install httpx pycryptodome

# 4. 生成文本
python scripts/fetch_daily.py
python scripts/fetch_jisubei.py
python scripts/gen_index.py

# 5. 启动适配器（默认端口 18888）
ott-adapter

# 或启用每日自动刷新
ott-adapter --refresh daily
```

typetype 配置（`~/.config/typetype/config.json`）：
```json
{
  "registry": {
    "primary_url": "http://127.0.0.1:18888"
  }
}
```

详见 [docs/ADAPTER_GUIDE.md](docs/ADAPTER_GUIDE.md)。

---

### 方式二：自行托管（高级）

将生成的 JSON 文件 push 到自己的 GitHub 仓库，通过 CDN 提供访问。

```bash
python scripts/fetch_daily.py
python scripts/fetch_jisubei.py
python scripts/gen_index.py
git add content/ registry_index.json
git commit -m "update"
git push
```

typetype 配置：
```json
{
  "registry": {
    "primary_url": "https://cdn.jsdelivr.net/gh/<your-username>/open-typing-texts@main"
  }
}
```

---

## 适配器命令行参数

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--port` | `18888` | 监听端口 |
| `--data-dir` | `.` | OTT 仓库根目录 |
| `--refresh` | `once` | 刷新频率：`once` / `hourly` / `daily` |

---

## 已包含的脚本

| 脚本 | 说明 | 目标源 |
|:---|:---|:---|
| `fetch_daily.py` | 每日短篇文本抓取 | 公开 API |
| `fetch_jisubei.py` | 极速杯文本抓取 | jsxiaoshi.com API |
| `gen_index.py` | 索引生成器 | 读取 content/ 重建索引 |

---

## 如何添加新文本源

参见 [docs/SCRIPT_GUIDE.md](docs/SCRIPT_GUIDE.md)。

---

## 仓库结构

```
open-typing-texts/
├── pyproject.toml             ← 适配器包配置
├── src/ott_adapter/           ← 适配器源码
│   ├── __main__.py            ← CLI 入口
│   ├── server.py              ← HTTP 服务
│   └── scheduler.py           ← 定时调度
├── scripts/
│   ├── fetch_daily.py         ← 每日抓取脚本（用户本地运行）
│   ├── fetch_jisubei.py       ← 极速杯抓取脚本
│   └── gen_index.py           ← 索引生成工具
├── docs/
│   ├── ADAPTER_GUIDE.md       ← 适配器使用指南
│   └── SCRIPT_GUIDE.md        ← 脚本编写教程
└── README.md                  ← 本文件
```

---

## 许可证

代码：MIT

内容：本仓库不托管任何内容，用户自行抓取的数据由其自行负责。
