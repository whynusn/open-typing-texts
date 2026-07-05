# 适配器使用指南

> 本指南面向：希望在本地运行 OTT 文本服务，为 typetype 等跟打器提供文本的用户。

---

## 1. 安装

```bash
# 1. 克隆仓库
git clone https://github.com/<your-username>/open-typing-texts.git
cd open-typing-texts

# 2. 安装适配器（开发模式）
pip install -e .

# 3. 安装抓取依赖
pip install httpx pycryptodome
```

---

## 2. 生成文本

```bash
# 抓取所有文本源
python scripts/fetch_daily.py
python scripts/fetch_jisubei.py

# 生成索引
python scripts/gen_index.py
```

文本文件将生成在 `content/` 目录中：
```
content/
├── daily.json       ← 每日一文
├── jisubei.json     ← 极速杯每日挑战
└── ...              ← 其他文本源
```

---

## 3. 启动适配器

```bash
# 前台运行（默认端口 18888）
ott-adapter

# 指定端口
ott-adapter --port 19999

# 启用每日自动刷新
ott-adapter --refresh daily

# 指定数据目录
ott-adapter --data-dir /path/to/open-typing-texts
```

启动后将输出：
```
OTT adapter listening on http://127.0.0.1:18888
Data directory: /home/user/open-typing-texts
Press Ctrl+C to stop.
```

---

## 4. 配置 typetype

在 typetype 配置文件（`~/.config/typetype/config.json`）中设置：

```json
{
  "registry": {
    "primary_url": "http://127.0.0.1:18888",
    "cache_ttl_seconds": 86400,
    "max_content_bytes": 1048576
  }
}
```

重启 typetype 后，"开源文库"页面将显示 OTT 文本目录。

---

## 5. 添加自定义文本源

1. 在 `scripts/` 下新建 `fetch_xxx.py`（参考 `fetch_daily.py` 模板）
2. 运行 `python scripts/fetch_xxx.py` 抓取文本
3. 运行 `python scripts/gen_index.py` 更新索引
4. 适配器会自动提供新的文本（无需重启）

---

## 6. 命令行参数

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--port` | `18888` | 监听端口 |
| `--data-dir` | `.` | OTT 仓库根目录 |
| `--refresh` | `once` | 刷新频率：`once` / `hourly` / `daily` |

---

## 7. 常见问题

**Q: 端口被占用怎么办？**
A: 使用 `--port <其他端口>` 指定未使用的端口，并同步修改 typetype 配置中的 `primary_url`。

**Q: 如何后台运行？**
A: 使用 `nohup ott-adapter &` 或 `systemd` 服务（见下方）。

**Q: 支持 Windows 吗？**
A: 支持。Python 3.12+ 环境下 `ott-adapter` 可直接运行。

---

## 8. systemd 服务示例（Linux）

```ini
# ~/.config/systemd/user/ott-adapter.service
[Unit]
Description=OTT Local Adapter
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/<user>/open-typing-texts
ExecStart=/home/<user>/.local/bin/ott-adapter --port 18888 --refresh daily
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable ott-adapter
systemctl --user start ott-adapter
```
