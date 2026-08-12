# 如何向 OTT 贡献新脚本

本文档描述如何贡献一个本地抓取脚本，以及如何发布一个去中心化 OTT Repo 源。OTT Core v1 的权威协议见 [OTT_SPEC.md](OTT_SPEC.md)，OTT Repo v1（源分发控制面）见 [docs/repo-manifest-spec.md](docs/repo-manifest-spec.md)。贡献脚本时，你只提交 `scripts/fetch_xxx.py`；不要提交 `content/` 下真实抓取内容。

## 0. 快速路径：想发布一个"源"而不是脚本？

大多数文本源不需要写 Python 脚本。若目标源是简单的 JSON API 或需加密/编码的动态请求体，优先把它声明为 **OTT Repo `ott-rule` 源**（L1/L1.5），发布到一个外部源仓库（如 `ott-source-hub`），而不是本仓库的 `scripts/`。指引见文末 [7. 发布一个 Repo 源](#7-发布一个-repo-源)。

## 1. 准备工作

- GitHub 账号
- Git
- Python 3.12+
- `uv`
- 一个你有权在本地抓取或转换的文本来源

```bash
git clone https://github.com/你的用户名/open-typing-texts.git
cd open-typing-texts
uv sync
```

## 2. 输出模型

脚本可以输出 legacy-compatible content file，adapter 会把它规范化为 OTT Core v1 entry：

```json
{
  "source_key": "mysource",
  "title": "显示名称",
  "content": "正文内容",
  "metadata": {
    "description": "正文摘要或来源说明",
    "category": "daily",
    "tags": ["标签"],
    "date": "2026-07-05"
  }
}
```

如果一个来源包含多篇文本，使用 `entries[]`：

```json
{
  "source_key": "mysource",
  "title": "最新标题",
  "content": "最新正文",
  "metadata": {"category": "daily"},
  "entries": [
    {
      "entry_id": "ent_mysource_20260705",
      "title": "标题",
      "content": "正文内容",
      "metadata": {"tags": ["标签"]},
      "fetched_at": "2026-07-05T10:00:00+08:00"
    }
  ]
}
```

字段约束：

- `source_key` 只能包含字母、数字、下划线。
- `content` 必须是非空字符串。
- 发布后建议持久化显式 `entry_id`，避免标题调整导致身份变化。
- `revision_id` 可省略；adapter 会随 `content_hash` 派生。
- 小文本会成为 `content_mode: "inline"`，长文本会成为 `content_mode: "segmented"`。
- summary 列表不得包含全文；segmented detail 不得包含全文。

## 3. 编写脚本

先复制现有脚本作为起点：

```bash
cp scripts/fetch_poem.py scripts/fetch_mysource.py
```

推荐脚本结构：

```python
#!/usr/bin/env python3
"""fetch_mysource.py - 我的文本源抓取脚本。

DISCLAIMER: 请确保抓取行为符合目标网站 robots.txt、服务条款及当地版权法。
"""

import json
from pathlib import Path

import httpx

SOURCE_KEY = "mysource"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "content" / f"{SOURCE_KEY}.json"


def fetch_raw() -> dict:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        response = client.get("https://example.com/api/text")
        response.raise_for_status()
        return response.json()


def transform(raw: dict) -> dict:
    return {
        "source_key": SOURCE_KEY,
        "title": raw.get("title", SOURCE_KEY),
        "content": raw["text"],
        "metadata": {
            "description": "你的文本源描述",
            "category": "daily",
            "tags": ["标签"],
        },
    }


def main() -> int:
    output = transform(fetch_raw())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(OUTPUT_PATH)
    return 0
```

`fetch_raw()` 可以访问真实网络，只能在贡献者本机运行；CI 只应使用 fake raw 数据测试 `transform()`。

## 4. 本地验证

```bash
python scripts/fetch_mysource.py
uv run ott-adapter validate-script scripts/fetch_mysource.py
uv run ott-adapter validate content/mysource.json
uv run ott-adapter validate --data-dir .
uv run ott-adapter --data-dir .
```

浏览器打开 <http://127.0.0.1:18888>，确认文本可见。

如果验证失败，先修复字段格式，再重新运行脚本。不要把真实 `content/` 文件加入 PR。

## 5. 提交贡献

```bash
git checkout -b add-mysource
git add scripts/fetch_mysource.py
git commit -m "feat: add mysource fetch script"
git push origin add-mysource
```

PR 描述请包含：

- 数据来源和合规说明。
- 本地运行命令。
- `ott-adapter validate ...` 与 `ott-adapter validate-script ...` 的 PASS/FAIL 摘要。
- 是否需要账号、cookie、token 或特殊环境变量。

## 6. CI 边界

项目 CI 不运行真实抓取脚本，不访问第三方文本来源。CI 可以检查：

- `transform()` 对 fake raw 数据的输出。
- schema/validator 是否通过。
- 脚本是否包含高风险调用，例如 `eval`、`exec`、`subprocess`、`os.system`、`socket`、`pty`、`ctypes`。
- 是否误提交 `content/` 真实内容。

法律、版权、robots.txt、服务条款仍由贡献者和维护者人工确认。

## 7. 发布一个 Repo 源

去中心化源通过 **OTT Repo v1 manifest** 分发（`ott-repo.json`），客户端（如 typetype）订阅 manifest URL 后即可发现源。协议细节见 [docs/repo-manifest-spec.md](docs/repo-manifest-spec.md)，权威 schema 为 `schemas/ott-repo.schema.json`。

### 7.1 选择源类型

| 层级 | `type` | 适用场景 | 签名要求 |
|:---|:---|:---|:---|
| L0 | `ott-instance` | 已有 OTT Core v1 部署（Static/Service Profile） | 可选（UI 徽章） |
| L1 | `ott-rule` | 简单 JSON API，固定提取路径 | 可选（UI 徽章） |
| L1.5 | `ott-rule`（含 `steps`） | 需加密/编码/动态构造请求体 | 可选（UI 徽章） |
| L2 | `ott-bridge` | 实时 API 桥（可为带凭据服务） | 可选（UI 徽章） |
| L3 | `ott-script` | 复杂抓取逻辑，声明式无法表达 | **必须**（签名门槛） |

**优先选择低层级**：能用 L1 不用 L1.5，能用 L1.5 不用 L3。低层级更安全、更易维护、无需签名。

### 7.2 最小 manifest

```json
{
  "protocol": "ott-repo",
  "version": "1.1",
  "type": "repository",
  "repo_id": "io.github.you.your-texts",
  "name": "你的文本源集",
  "mirrors": [
    { "url": "https://raw.githubusercontent.com/you/your-texts/main/ott-repo.json", "priority": 1 }
  ],
  "sources": [
    {
      "type": "ott-rule",
      "rule_id": "hitokoto",
      "label": "一言",
      "rule": {
        "kind": "json-api",
        "request": { "url": "https://v1.hitokoto.cn/?c=i", "method": "GET" },
        "extract": { "title": "$.from", "content": "$.hitokoto" },
        "permissions": { "network": ["v1.hitokoto.cn"] },
        "rights": { "min_api_level": 1 }
      },
      "tags": ["quote", "chinese"]
    }
  ]
}
```

### 7.3 本地验证

```bash
# 1. 安装 jsonschema
uv pip install jsonschema

# 2. 校验你的 manifest 通过权威 schema
python -c "
import json, jsonschema
m = json.load(open('ott-repo.json'))
s = json.load(open('schemas/ott-repo.schema.json'))
jsonschema.validate(m, s)
print('manifest OK, sources:', len(m['sources']))
"

# 3. L1.5 规则（含 steps）单独过 v2 schema
python -c "
import json, jsonschema
m = json.load(open('ott-repo.json'))
s = json.load(open('schemas/ott-rule-v2.schema.json'))
for src in m['sources']:
    if src.get('type') == 'ott-rule':
        jsonschema.validate(src['rule'], s)
print('rule fields OK')
"
```

### 7.4 L3 脚本签名（可选但必须）

若含 `ott-script` 源，仓库必须携带签名（`trust.signature` + `trust.pubkey`），客户端在信任确认后才执行脚本。签名流程：

```bash
# 生成 ed25519 密钥对（cryptography）
python -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
key = Ed25519PrivateKey.generate()
pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
priv = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()
print('pubkey:', pub)
print('privkey:', priv)  # 私钥绝不提交，只保存在签名者本地
"

# 对 canonical manifest 字节签名（去 trust 键 + sort_keys + 无空白）
python - <<'PY'
import json, hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

manifest = json.load(open('ott-repo.json'))
canonical = {k: v for k, v in manifest.items() if k != 'trust'}
canonical_bytes = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(open('privkey.txt').read().strip()))
sig = priv.sign(canonical_bytes)
manifest['trust'] = {**manifest.get('trust', {}), 'signature': sig.hex(), 'pubkey': pubkey_hex}
json.dump(manifest, open('ott-repo.json', 'w'), ensure_ascii=False, indent=2)
PY
```

### 7.5 发布与声明

- manifest 托管在 GitHub Pages / raw.githubusercontent / 任意静态主机，保证 HTTPS 与 CORS。
- 在 `mirrors` 中声明 ≥1 个镜像 URL（按 priority 升序 failover）。
- 在 README 或社区目录中公布你的 manifest URL，供客户端订阅。
- 更新 `updated_at` 字段为当前时间，保持与内容同步。
