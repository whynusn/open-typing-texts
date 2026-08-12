# 签名密钥管理（Repo v1 / 适配器包）

<!-- 状态: active | 创建: 2026-08-12 | 关联: docs/repo-manifest-spec.md §Trust, docs/adapter-package.md -->

> 本文是签名密钥的协议侧操作指引。canonical 定义与信任状态机见
> `repo-manifest-spec.md` §Trust；适配器包签名见 `adapter-package.md` §签名与校验。
> typetype 客户端的 TOFU 交互流程是其内部实现，不在此重复。

## 1. 密钥生成

```bash
python -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
key = Ed25519PrivateKey.generate()
pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
priv = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()
print('pubkey:', pub)
print('privkey:', priv)
"
```

- 公钥写入 manifest `trust.pubkey`（裸 64 hex 或 `ed25519:` 前缀均可）。
- **私钥绝不提交任何仓库、不进 GitHub Secret 以外的任何共享环境**；只保存在签名者本地（建议 `chmod 600`），丢失即需重新生成并更新公钥。

## 2. 对 canonical manifest 字节签名

签名对象 = 剔除 `trust` 键后的 manifest，UTF-8、键按字节序排序、无空白（`separators=(",", ":")`）：

```python
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

manifest = json.load(open("ott-repo.json"))
canonical = {k: v for k, v in manifest.items() if k != "trust"}
canonical_bytes = json.dumps(
    canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
).encode("utf-8")
priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(PRIVKEY_HEX))
sig = priv.sign(canonical_bytes)
manifest["trust"] = {
    **manifest.get("trust", {}),
    "signature": sig.hex(),
    "pubkey": PUBKEY_HEX,
}
json.dump(manifest, open("ott-repo.json", "w"), ensure_ascii=False, indent=2)
```

## 3. 验证

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

canonical = {k: v for k, v in manifest.items() if k != "trust"}
canonical_bytes = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(manifest["trust"]["pubkey"].split(":")[-1]))
pub.verify(bytes.fromhex(manifest["trust"]["signature"].split(":")[-1]), canonical_bytes)
print("signature OK")
```

## 4. 轮换

密钥轮换 = 用新私钥重新签名 + 更新 `trust.pubkey`。客户端检测到 pubkey 与 pinned 不一致时重置为 `pending`（信任降级），要求用户显式重新确认。

## 5. 适配器包签名

`adapter.json` 的 canonical 剔除 `signature` 键（见 `adapter-package.md` §签名与校验），同一对密钥可用。私钥存 GitHub 仓库级 Secret（如 `ADAPTER_SIGNING_SECRET_KEY`），CI `workflow_dispatch` 签名后提交回仓库。
