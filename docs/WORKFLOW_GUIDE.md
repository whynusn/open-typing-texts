# 脚本运行指南

> 本仓库不提供任何现成文本内容，也不运行 CI 自动抓取。所有脚本须在本地手动执行。

---

## 1. 所有脚本均为本地运行

```bash
# 安装依赖
pip install httpx pycryptodome

# 运行抓取脚本
python scripts/fetch_daily.py
python scripts/fetch_jisubei.py

# 重建索引
python scripts/gen_index.py
```

## 2. 手动触发

直接执行脚本即可，无需任何 CI 配置。

## 3. 常见问题

**Q: 脚本失败怎么办？**
A: 检查网络连接和目标网站状态。失败时不写入文件，保留上一次成功的内容。

**Q: 如何确认脚本配置正确？**
A: 使用 `--dry-run` 参数测试：
```bash
python scripts/fetch_xxx.py --dry-run
```
