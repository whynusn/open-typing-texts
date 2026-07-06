# 如何向 OTT 贡献新脚本

> 感谢你愿意为开源打字文本库贡献力量！本文档将一步步带你完成新脚本的编写和提交。

---

## 1. 准备工作

### 1.1 你需要什么

- 一个 **GitHub 账号**（如果没有，可以在 [github.com](https://github.com/signup) 免费注册）
- **Git** 已安装（用于提交代码）
- **Python 3.12+** 环境
- 一个你想抓取的**文本来源**（需要有公开 API 或网页）

### 1.2 Fork 仓库

1. 打开 <https://github.com/whynusn/open-typing-texts>
2. 点击右上角 **Fork** 按钮
3. 等待仓库复制完成

### 1.3 克隆你的 Fork

```bash
git clone https://github.com/你的用户名/open-typing-texts.git
cd open-typing-texts
```

---

## 2. 编写抓取脚本

### 2.1 复制模板

```bash
cp scripts/fetch_daily.py scripts/fetch_mysource.py
```

### 2.2 编辑脚本

打开 `scripts/fetch_mysource.py`，修改以下部分：

```python
#!/usr/bin/env python3
"""fetch_mysource.py — 我的文本源抓取脚本。

DISCLAIMER: 请确保抓取行为符合目标网站 robots.txt 及当地版权法，使用者自负全责。
"""

import json
from pathlib import Path

# ── 配置 ───────────────────────────────────────
SOURCE_KEY = "mysource"          # 唯一标识（英文，不含特殊字符）
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "content" / f"{SOURCE_KEY}.json"

# 抓取逻辑（替换为你自己的 API 调用或网页解析）
import httpx

def fetch():
    with httpx.Client(timeout=20, trust_env=False) as client:
        resp = client.get("https://example.com/api/text")
        resp.raise_for_status()
        return resp.json()

# ── 入口 ───────────────────────────────────────
def main():
    data = fetch()

    # 格式转换（确保字段符合 OTT 内容标准）
    output = {
        "source_key": SOURCE_KEY,
        "title": data.get("title", SOURCE_KEY),
        "content": data["text"],        # 必填：正文字符串
        "metadata": {
            "description": "你的文本源描述",
            "category": "daily",        # daily / static / ...
            "tags": ["标签1", "标签2"],
        }
    }

    # 写入文件
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)  # 原子写

    print(f"[{SOURCE_KEY}] 已写入 {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
```

### 2.3 内容文件格式

你的脚本必须生成如下 JSON：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文内容（必填，字符串）",
  "metadata": {
    "description": "《出处》作者（必有意义，禁止 YYYY-MM-DD 模板）",
    "category": "daily",
    "tags": ["标签"],
    "date": "2026-07-05"
  }
}
```

**必填字段**：`source_key`、`content`

---

## 3. 本地测试

### 3.1 安装依赖

```bash
pip install -e ".[fetch,watch]"
```

### 3.2 运行你的脚本

```bash
python scripts/fetch_mysource.py
```

### 3.3 验证输出

```bash
# 检查文件是否生成
cat content/mysource.json | python3 -m json.tool
```

### 3.4 启动适配器测试

```bash
ott-adapter --no-fetch    # 不重新抓取，服务现有内容
```

浏览器打开 <http://127.0.0.1:18888>，你应该能看到新文本出现在列表中。

---

## 4. 提交贡献

### 4.1 创建分支

```bash
git checkout -b add-mysource
```

### 4.2 添加文件

```bash
git add scripts/fetch_mysource.py
```

不需要提交 `content/` 目录（脚本运行时自动生成，已加入 .gitignore）。

### 4.3 提交

```bash
git commit -m "feat: 添加 mysource 文本源"
```

### 4.4 推送到你的 Fork

```bash
git push origin add-mysource
```

### 4.5 发起 Pull Request

1. 打开 <https://github.com/whynusn/open-typing-texts>
2. 点击 **Compare & pull request**
3. 填写说明：
   - 文本源名称和网址
   - 抓取逻辑简述
   - 是否已测试通过
4. 点击 **Create pull request**

维护者审核后会合并你的贡献。

---

## 5. 注意事项

- **法律合规**：确保你的抓取行为允许（检查 robots.txt）
- **幂等性**：脚本应可重复运行，覆盖旧文件
- **错误处理**：网络失败时优雅退出，不写入损坏文件
- **原子写入**：使用 `tmp + replace` 避免半写状态
- **source_key**：只用字母、数字、下划线，不含 `/` `.` `..`
- **描述必须有意义**：`metadata.description` 应说明文本来源、作者或主题（如 `《唐诗三百首》李白`）。**禁止** `每日精选 {date}` 等无意义模板字符串
