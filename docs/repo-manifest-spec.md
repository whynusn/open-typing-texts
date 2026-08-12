# OTT Repo v1 Specification

> Status: stable | Scope: decentralized source distribution control plane
> Companion: `OTT_SPEC.md` (OTT Core v1, stable) — this document changes nothing in Core v1.
> JSON Schema: [`schemas/ott-repo.schema.json`](../schemas/ott-repo.schema.json) (normative).

OTT Repo v1 defines the **control plane** of the open typing texts ecosystem:
how clients discover, subscribe to, trust, and refresh collections of text
sources. OTT Core v1 remains the **data plane** (source, entry, segment,
revision). A client that only implements Core v1 keeps working; Repo v1 is an
additive, independently versioned component.

Design lineage: mihon extension repositories (repo-as-URL, multi-repo,
explicit trust), Kazumi rule hubs (declarative JSON rules, API-level
negotiation), legado subscriptions (refreshable source lists anyone can host).

## Version Vocabulary

| Name | Current | Meaning |
|:---|:---|:---|
| OTT Core | `1.0` | Data model and read-only distribution contract (unchanged) |
| OTT Repo | `1.1` | Source manifest / subscription contract (this document) |
| Repo manifest file | `ott-repo.json` | Conventional filename; any URL serving the manifest is valid |

> v1.0 → v1.1 (2026-08-10): additive. Adds the `ott-script` source type (L3
> fetch scripts distributed under a signature gate, see §Source Types /
> §Trust). No v1.0 manifest becomes invalid; clients that do not execute L3
> scripts simply ignore `ott-script` sources. v1.1 also folds the L1.5 DSL
> rule fields (`steps` / `permissions` / `rights` / `request.body`) into the
> `ott-rule` source definition (see §Source Types `ott-rule`); L1 rules
> written against v1.0 remain valid.
>
> New manifests SHOULD declare `"version": "1.1"`; the schema accepts any
> valid semver, so a `1.0` manifest is still legal. The minimum supported
> Repo contract version is `1.0` (a `1.1` client reads `1.0` manifests), and
> the maximum is the schema's `ott-script` capability (`1.1`).

## Concepts

```text
Directory (optional)        repo-of-repos; discovery layer; never nested
  └─ Repository             a subscribable manifest listing sources
       └─ Source            ott-instance | ott-rule | ott-bridge | ott-script
            └─ Entry        OTT Core v1 data plane
```

- A **Repository** is a JSON manifest served at a URL. It distributes *pointers
  to sources*, never text content itself.
- A **Directory** is a manifest with `type: "directory"` whose `sources` list
  contains only `repository-ref` entries. Directories MUST NOT reference other
  directories.
- L0/L1/L2 sources are pure data: declarative rules and endpoint pointers, no
  executable content. The only executable content distributed through Repo v1
  is `ott-script` (L3), which is gated by a mandatory signature check and a
  restricted sandbox (see §Source Types `ott-script` and §Trust).

## Repo Manifest

```json
{
  "protocol": "ott-repo",
  "version": "1.1",
  "type": "repository",
  "repo_id": "texts.example.org",
  "name": "Example Chinese Library",
  "description": "Curated Chinese typing texts",
  "maintainer": { "name": "someone", "homepage": "https://example.org" },
  "license": "CC-BY-SA-4.0",
  "updated_at": "2026-08-01T00:00:00+08:00",
  "mirrors": [
    { "url": "https://texts.example.org/ott-repo.json", "priority": 1 },
    { "url": "https://cdn.example.net/user/repo/ott-repo.json", "priority": 2 }
  ],
  "trust": {
    "signature": "ed25519:<128 hex>",
    "pubkey": "ed25519:<64 hex>",
    "required": false
  },
  "requires": {
    "ott_core": ">=1.0",
    "client_features": ["segmented_content"]
  },
  "sources": [
    {
      "type": "ott-instance",
      "authority": "texts.example.org",
      "label": "Example Static Library",
      "endpoints": [
        { "url": "https://texts.example.org/ott/", "profile": "static", "priority": 1 },
        { "url": "http://127.0.0.1:18888/", "profile": "service", "priority": 2 }
      ],
      "tags": ["chinese", "curated"],
      "default_enabled": true
    }
  ]
}
```

### Field rules

| Field | Required | Rule |
|:---|:---:|:---|
| `protocol` | ✅ | MUST be `"ott-repo"` |
| `version` | ✅ | Semver string of the Repo contract the manifest follows |
| `type` | ✅ | `"repository"` or `"directory"` |
| `repo_id` | ✅ | Stable identity; reverse-domain or `key:ed25519:<24-hex fingerprint>` |
| `name` | ✅ | Human display name |
| `mirrors` | ✅ | ≥1 URL serving this same manifest; clients try ascending `priority` |
| `trust` | optional | See §Trust. `required: false` by default and SHOULD stay so |
| `requires` | optional | Client capability negotiation (Kazumi API-level style); unmet ⇒ mark whole repo incompatible, never silently degrade |
| `sources` | ✅ (`repository`) | See §Source Types |
| `sources` | ✅ (`directory`) | Only `repository-ref` entries (see §Directories) |

## Source Types

### `ott-instance`

Points at an OTT Core v1 deployment (Static and/or Service Profile).

- `authority` (required): the instance's stable identity (see §Authority).
- `endpoints` (required, ≥1): `{url, profile, priority}`; `profile` is
  `"static"` or `"service"`. Clients fail over by priority, then by endpoint
  health (exponential backoff on repeated failures).
- `default_enabled` (optional, default `true`): whether the instance is active
  immediately after repo subscription.

### `ott-rule`

An inline **declarative** fetch rule executed by the client's restricted
interpreter. Rules are data, not code.

- `rule_id` (required, unique within the repo): stable rule identity.
- `rule` (required):

```json
{
  "kind": "json-api",
  "request": {
    "url": "https://v1.hitokoto.cn/?c=i",
    "method": "GET",
    "headers": { "Accept": "application/json" }
  },
  "extract": { "title": "$.from", "content": "$.hitokoto" },
  "transform": ["trim"],
  "schedule": { "mode": "daily", "cache_ttl_seconds": 86400 },
  "pagination": { "param": "page", "start": 1, "step": 1, "max_pages": 5 }
}
```

Interpreter constraints (MUST):

- `extract` values are exactly one of: JSON path (`$.a.b`), regex with named
  groups, or CSS selector. No embedded scripting language.
- `transform` is a fixed pipeline of named operations (`trim`, `replace`,
  `truncate`); no arbitrary computation.
- `request.url` MUST be `http(s)`: no `file:`, no loopback/private/reserved
  address ranges.
- Fetched items become client-local entries under authority
  `rule:{repo_id}:{rule_id}`, so progress keys remain uniform
  (`ott:rule:{repo_id}:{rule_id}:{entry_id}@{revision_id}`).

#### L1.5: DSL rule fields (v1.1)

Rules MAY add the L1.5 DSL pipeline (`steps`) for flows a fixed L1 rule
cannot express (encryption, encoding, dynamic request bodies). The full
definition lives in [`schemas/ott-rule-v2.schema.json`](../schemas/ott-rule-v2.schema.json).

- `steps` (max 8): sequential `{fn, args}` pipeline executed by the client's
  whitelist evaluator; `args` may contain `{"ref": "body"}` to reference
  `request.body` literal. The last step's output becomes the POST body.
  Unknown fns, step/arg overflow, or mixing `transform` with `steps` reject
  the whole rule.
- `permissions.network` (optional): domain whitelist; a request URL outside
  the whitelist rejects the rule. When absent, the baseline URL policy
  applies.
- `rights.min_api_level` (optional): client API level required; lower
  clients skip the rule as incompatible.
- `request.body` (optional): literal body (str/dict/list/int/bool) or `null`
  when constructed via `steps`; float and other types reject the rule.

A v1.0 L1 rule (no `steps`) is a valid subset; both are governed by the
`ott-rule` source definition in the manifest schema.

### `ott-bridge`

A real-time API bridge (e.g. an authenticated "random text" service).

- `bridge_kind` (required): names the bridge protocol (e.g. `"wenlai"`).
- `endpoint` (required): base URL of the service.
- `requires_credentials` (optional, default `false`): when true, credentials
  are entered by the user and stored only in the local OS keyring; Repo v1
  manifests MUST NOT carry credentials.

#### Bridge response contract (`bridge_kind: "generic-http"`)

The first built-in bridge protocol is `generic-http`: an unauthenticated
`GET` request to `endpoint`. The response MUST be HTTP 200 with
`Content-Type: application/json` and one of two shapes:

1. **Single entry** — a flat object with OTT Core v1 entry fields:
   ```json
   { "title": "示例标题", "content": "正文内容", "source_key": "demo" }
   ```
2. **Entry list** — an object with an `entries` array:
   ```json
   { "entries": [ { "title": "...", "content": "..." } ] }
   ```

Recognized entry fields (Core v1 additive): `entry_id`, `title`, `content`
(required), `preview`, `source_key`, `char_count`, `tags`, `category`.
`title` and `source_key` are optional; when `entry_id` is absent clients
derive a stable id from the content hash so repeated fetches of the same
content deduplicate. Fetched items become client-local entries under
authority `bridge:{sha256(endpoint)[:12]}`, so progress keys remain uniform
(`ott:bridge:{authority}:{entry_id}@{revision_id}`).

Future bridge kinds (e.g. authenticated protocols) extend this contract;
clients MUST skip `bridge_kind` values they do not implement rather than
guessing at the wire format.

### `ott-script`

A fetch script (e.g. Python) distributed through Repo v1 and executed in the
client's restricted sandbox (L3). Unlike L0/L1/L2 — which are pure data —
`ott-script` carries executable code, so it is the only source type subject to
a **mandatory signature gate**: clients MUST NOT execute an `ott-script` from a
repo whose `trust_state` is not `verified` (see §Trust).

- `url` (required): public `http(s)` URL of the script payload (`.py`).
- `checksum` (optional): `sha256:<64 hex>` of the payload; clients verify before
  execution and reject on mismatch.
- `permissions` (optional): capability allowlist enforced by the sandbox.
  - `network` (optional): list of hostnames the script may contact; when
    declared it is enforced at runtime, when absent the client falls back to
    its URL validation policy. Subdomain matching applies.
  - `secrets` (optional): list of keyring credential names the script may read
    (e.g. `"wenlai_token"`); credentials are entered by the user and stored only
    in the local OS keyring, never in the manifest.
- `rights.min_api_level` (optional): the client API level required to run this
  script; if the client's `CLIENT_API_LEVEL` is lower, the source is skipped as
  incompatible.
- Fetched items become client-local entries under authority
  `script`, so progress keys remain uniform
  (`ott:script:{entry_id}@{revision_id}`).

Execution MUST happen in a restricted sandbox: subprocess isolation with
resource limits (memory/CPU/process count/file write budget) plus a filesystem
allowlist (Landlock or equivalent on Linux). Scripts escape only into a
resource-bounded, network-visible subprocess — never into the client's own
process. A client that cannot provide such a sandbox (e.g. Windows without
job-object/AppContainer equivalents) SHOULD disable L3 by default.

### `repository-ref` (directories only)

```json
{ "type": "repository-ref", "url": "https://example.org/ott-repo.json", "label": "...", "tags": [] }
```

## Authority Identity

`authority` is a first-class identity with three legal forms:

| Form | Use | Example |
|:---|:---|:---|
| Reverse domain | publishers with a domain or GitHub Pages | `org.example.texts`, `io.github.user.repo` |
| Key fingerprint | signed publishers without a domain | `key:ed25519:a1b2c3...` (first 24 hex) |
| `local` | the machine-local adapter default | `local` |

Core v1 additive fields (backward compatible; old clients ignore them):

- An instance MAY declare `"authority_id"` in `ott.json` (Static Profile) and
  in `GET /ott/v1/capabilities` (Service Profile). When absent, clients fall
  back to the primary endpoint host.
- An instance MAY declare `"repo_url"` pointing back to the Repo manifest that
  distributes it, enabling deep-link-driven repo discovery.

Entry URN (normative across progress, bookmarks, history, sharing):

```text
ott:{authority}:{entry_id}@{revision_id}
ott://{authority}/{entry_id}        (deep link form)
```

On an `ott://` deep link for an unsubscribed authority, clients resolve the
instance, read `repo_url`, and offer to subscribe to the containing repo.

## Trust

- Signatures are **optional** and use bare Ed25519 over the canonical manifest
  bytes. The signature is `ed25519:<128 hex>` or bare 128 hex; the pubkey is
  `ed25519:<64 hex>` or bare 64 hex. minisign is not supported.
- **Canonical manifest bytes** (normative; must match the reference client
  byte-for-byte): the manifest with the `trust` key removed, serialized as
  UTF-8 JSON with keys sorted bytewise and no whitespace between tokens
  (`json.dumps(canonical, sort_keys=True, ensure_ascii=False,
  separators=(",", ":"))`), no trailing commas. Signers sign exactly these
  bytes and clients verify exactly these bytes; any other serialization fails
  verification.
- `trust.required: true` is reserved for curated directories and SHOULD NOT be
  used by general repos.
- Clients pin the pubkey on first use (TOFU) and MUST surface an explicit
  warning when the key changes.
- For L0/L1/L2 sources, signature status is a UI badge (`verified` /
  `unverified` / `failed`), never an admission gate.
- For `ott-script` (L3) sources the signature **is** an admission gate: a repo
  whose `trust_state` is not `verified` MUST NOT have its scripts executed
  (see §Source Types `ott-script`). A fresh signature transitions the repo to
  `pending`; the user explicitly confirms trust before it becomes `verified`.
  Key rotation resets the repo to `pending` for re-confirmation.
- Content integrity within an instance remains Core v1 `content_hash`
  (sha256); Repo v1 adds no content-level duties.

Capability tiers (informative, enforced by clients):

| Tier | Form | Execution surface | Distribution |
|:---|:---|:---|:---|
| L0 | OTT data instance | none | allowed |
| L1 | Declarative rule | restricted interpreter | allowed |
| L2 | Bridge (real-time API) | protocol adapter, local credentials | allowed |
| L3 | Fetch script (e.g. Python) | restricted subprocess sandbox | allowed, signature-gated (`trust_state=verified` required) |

Invariant: nothing a client obtains through network subscription executes
outside a signature-gated, restricted sandbox.

## Client Behavior

- **Refresh**: pull-based; honor HTTP `ETag` / `Last-Modified`; default TTL
  86400 s, overridable per subscription; offline ⇒ serve cached manifest
  regardless of TTL (stale-while-revalidate mirroring the Core client cache).
- **Failover**: mirrors ascending `priority`; unhealthy mirrors back off
  exponentially and recover automatically.
- **Aggregation**: sources from all enabled repos are namespaced by authority;
  the same `entry_id` under different authorities is a different entry.
- **Incompatibility**: unmet `requires` marks the repo incompatible with a
  human-readable reason; no silent partial activation.

## JSON Schema

The normative schema lives in [`schemas/ott-repo.schema.json`](../schemas/ott-repo.schema.json)
(draft 2020-12). It includes per-source-type `allOf` / `if-then` refinements that
this prose summary does not repeat. Clients SHOULD validate manifests against
this schema before caching. Canonical fixtures live in
[`tests/fixtures/ott/repo-manifests/`](../../tests/fixtures/ott/repo-manifests/).

Supporting schemas (same draft, each validated by its own fixture pack):

| Schema | Scope |
|:---|:---|
| [`schemas/ott-repo.schema.json`](../schemas/ott-repo.schema.json) | Manifest contract; `ott-rule` sources fold in the L1.5 DSL fields (`steps`/`permissions`/`rights`/`request.body`) |
| [`schemas/ott-rule-v2.schema.json`](../schemas/ott-rule-v2.schema.json) | L1.5 DSL rule field validation (45-primitive whitelist, step limits, transform/steps mutual exclusion) |
| [`schemas/ott-bridge-response.schema.json`](../schemas/ott-bridge-response.schema.json) | `ott-bridge` `generic-http` response body (single entry or `entries` list) |
| [`schemas/ott-adapter-v1.schema.json`](../schemas/ott-adapter-v1.schema.json) | Adapter package format (see `docs/adapter-package.md`) |

## Security Considerations

- A malicious repo can only supply data: no code execution at L0/L1, no
  credential access at L2. L3 scripts execute only under a signature gate
  (`trust_state=verified`) inside a restricted subprocess sandbox; the
  worst-case escape is a resource-bounded, network-visible child process, not
  the client's own process.
- Rule URLs are restricted to public http(s) targets to prevent internal
  network probing.
- Authority collisions between unsigned repos are displayed side-by-side,
  grouped by repo, letting the user choose; signed authorities bind to keys.
- Clients should offer one-click repo disable/removal; any client-side
  blocklist is local policy, not protocol enforcement.

## Relationship to Core v1

| Concern | Owner |
|:---|:---|
| Entry/segment/revision/hash model | Core v1 (unchanged) |
| Static/Service distribution | Core v1 (unchanged) |
| Optional `authority_id` / `repo_url` instance fields | Core 1.1 candidate, additive |
| Source discovery, subscription, mirrors, trust, directories, signature-gated L3 scripts | Repo v1 (this document) |
| Script authoring, storage, admin APIs | Reference adapter (unchanged, out of protocol) |

## Future Work (explicitly out of v1)

- Content-addressed distribution (`by-hash` endpoints, multihash) for
  cross-instance dedup / CDN / P2P.
- Arbitrary range reads; Collection objects; full revision history
  (already deferred by Core v1).
- Client SDK once a second client exists.
