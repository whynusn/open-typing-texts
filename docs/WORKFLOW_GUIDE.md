# Workflow 配置指南

> 本指南面向：需要在 OTT 仓库添加或修改定时抓取任务的贡献者。
> 读完本指南后，你将能够正确配置 cron 定时、手动触发和容错机制。

---

## 1. 仓库只有一个 workflow

所有动态抓取统一由 `.github/workflows/daily.yml` 调度。

```
GitHub Actions 每日 0:00 UTC 自动触发
  │
  ├─ pip install 依赖
  │
  ├─ python scripts/fetch_jisubei.py    ← 极速杯（每日）
  ├─ python scripts/fetch_daily.py      ← 每日一文（每日）
  ├─ python scripts/fetch_xxx.py        ← 你的脚本（频率自定）
  │
  ├─ python scripts/gen_index.py        ← 重建索引
  │
  └─ git-auto-commit                    ← 自动提交
```

---

## 2. 添加新的脚本调用

只需在 `daily.yml` 的 `steps:` 中添加一步：

```yaml
- name: 抓取 XXX 文本
  run: python scripts/fetch_xxx.py
  continue-on-error: true              # 失败不中断后续步骤
```

**注意**：脚本自身的更新频率由脚本内部控制（见 [SCRIPT_GUIDE.md](SCRIPT_GUIDE.md) §2），CI 只负责每日调用。

---

## 3. cron 语法

GitHub Actions 使用标准 cron 表达式：

```
┌───────────── 分 (0-59)
│ ┌───────────── 时 (0-23)
│ │ ┌───────────── 日 (1-31)
│ │ │ ┌───────────── 月 (1-12)
│ │ │ │ ┌───────────── 周 (0-7, 0 和 7 都是周日)
│ │ │ │ │
* * * * *
```

### 常用示例

| 频率 | cron | 说明 |
|:---|:---|:---|
| 每日 0:00 UTC | `0 0 * * *` | 每天午夜 |
| 每日 8:00 北京时间 | `0 0 * * *` | UTC 0:00 = 北京 8:00 |
| 每周一 0:00 | `0 0 * * 1` | 每周一 |
| 每月1号 0:00 | `0 0 1 * * *` | 每月1号 |
| 每3天 0:00 | `0 0 */3 * *` | 每3天（1号、4号、7号...） |

**注意**：GitHub Actions cron 不支持 `*/3` 在"日"字段的语义是"每3天从1号开始"，不是"每3天一次"。如需精确的"每3天"，请在脚本内部通过文件 mtime 判断。

---

## 4. 手动触发

配置 `workflow_dispatch` 后，可在 GitHub Actions 页面手动点击 "Run workflow"：

```yaml
on:
  schedule: [{cron: "0 0 * * *"}]      # 定时触发
  workflow_dispatch:                    # 手动触发（无输入参数）
```

如需手动触发时传入参数（如指定日期）：

```yaml
  workflow_dispatch:
    inputs:
      date:
        description: "目标日期 YYYY-MM-DD"
        required: false
        default: ""
```

脚本中通过 `argparse` 接收：

```yaml
- name: 抓取极速杯
  run: python scripts/fetch_jisubei.py
    ${{ github.event.inputs.date && format('--date {0}', github.event.inputs.date) || '' }}
```

---

## 5. 完整 workflow 模板

```yaml
name: registry-daily
on:
  schedule: [{cron: "0 0 * * *"}]      # 每日 0:00 UTC
  workflow_dispatch:                    # 手动触发

concurrency:
  group: registry-daily
  cancel-in-progress: false             # 让正在跑的跑完

permissions:
  contents: write                       # git-auto-commit 需要 push 权限

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: actions/cache@v4
        with:
          path: content/
          key: registry-daily-${{ github.run_id }}
          restore-keys: registry-daily-

      - run: pip install httpx pycryptodome

      # === 动态抓取脚本（各脚本自行判断更新频率）===
      - name: 抓取极速杯每日文本
        run: python scripts/fetch_jisubei.py
        continue-on-error: true          # 失败不中断后续步骤

      # 添加新脚本只需复制上面一步，改名称和路径

      - name: 重生成索引
        run: python scripts/gen_index.py

      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: daily registry refresh"
          branch: main
```

---

## 6. 各字段说明

| 字段 | 说明 |
|:---|:---|
| `concurrency.group` | 防止同一 workflow 多个实例并发运行 |
| `concurrency.cancel-in-progress: false` | 不取消正在跑的旧实例（避免半写） |
| `permissions: contents: write` | `git-auto-commit-action` 需要 push 权限 |
| `continue-on-error: true` | 单个脚本失败不中断后续步骤 |
| `actions/cache` | 复用上次 `content/`，加速增量抓取 |

---

## 7. 常见问题

**Q: 脚本失败会影响其他脚本吗？**
A: 不会。每个脚本都配了 `continue-on-error: true`，失败只跳过自己。

**Q: 如何确认 workflow 配置正确？**
A: 推送后在 GitHub Actions 页面手动触发一次，观察运行日志。

**Q: 如何临时禁用某个脚本？**
A: 在 `daily.yml` 中注释掉对应步骤，不需要删除脚本文件。

**Q: 时区是哪个？**
A: GitHub Actions cron 使用 UTC。北京时间 = UTC+8，所以 `0 0 * * *` = 北京每天 8:00。
