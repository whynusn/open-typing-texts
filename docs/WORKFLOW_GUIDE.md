# Workflow 指南

> OTT 仓库只有一个 `daily.yml`，每日 0:00 UTC 自动运行。贡献者只需关注自己的抓取脚本，无需修改 workflow 定时配置。

---

## 1. 仓库只有一个 workflow

```
GitHub Actions 每日 0:00 UTC 自动触发
  │
  ├─ pip install 依赖
  │
  ├─ python scripts/fetch_jisubei.py    ← 极速杯（脚本内部判断频率）
  ├─ python scripts/fetch_daily.py      ← 每日一文（脚本内部判断频率）
  ├─ python scripts/fetch_xxx.py        ← 你的脚本（脚本内部判断频率）
  │
  ├─ python scripts/gen_index.py        ← 重建索引
  │
  └─ git-auto-commit                    ← 自动提交
```

**你只需要在 `daily.yml` 中添加一行调用**，定时统一由仓库维护。详见 [SCRIPT_GUIDE.md](SCRIPT_GUIDE.md)§2 频率控制。

---

## 2. 添加脚本调用

在 `.github/workflows/daily.yml` 的 `steps:` 中添加一步：

```yaml
- name: 抓取 XXX 文本
  run: python scripts/fetch_xxx.py
  continue-on-error: true              # 失败不中断后续步骤
```

---

## 3. 手动触发

GitHub Actions 页面 → `daily.yml` → Run workflow，无需配置任何输入参数。

---

## 4. 常见问题

**Q: 我的脚本想每周更新一次怎么办？**
A: 在脚本内部通过文件 mtime 判断（见 [SCRIPT_GUIDE.md](SCRIPT_GUIDE.md)§2），不需要改 workflow。

**Q: 脚本失败会影响其他人吗？**
A: 不会。每个脚本都配了 `continue-on-error: true`，失败只跳过自己。

**Q: 如何临时禁用某个脚本？**
A: 在 `daily.yml` 中注释掉对应步骤，不需要删除脚本文件。
