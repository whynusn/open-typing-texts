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
| OTT Repo | `1.0` | Source manifest / subscription contract (this document) |
| Repo manifest file | `ott-repo.json` | Conventional filename; any URL serving the manifest is valid |

## Concepts

```text
Directory (optional)        repo-of-repos; discovery layer; never nested
  └─ Repository             a subscribable manifest listing sources
       └─ Source            ott-instance | ott-rule | ott-bridge
            └─ Entry        OTT Core v1 data plane
```

- A **Repository** is a JSON manifest served at a URL. It distributes *pointers
  to sources*, never text content itself.
- A **Directory** is a manifest with `type: "directory"` whose `sources` list
  contains only `repository-ref` entries. Directories MUST NOT reference other
  directories.
- Every layer is pure data. No executable content is ever distributed through
  Repo v1.

## Repo Manifest

```json
{
  "protocol": "ott-repo",
  "version": "1.0",
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
    "signature": "minisign:...",
    "pubkey": "ed25519:...",
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

### `ott-bridge`

A real-time API bridge (e.g. an authenticated "random text" service).

- `bridge_kind` (required): names the bridge protocol (e.g. `"wenlai"`).
- `endpoint` (required): base URL of the service.
- `requires_credentials` (optional, default `false`): when true, credentials
  are entered by the user and stored only in the local OS keyring; Repo v1
  manifests MUST NOT carry credentials.

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

- Signatures are **optional** and use minisign / ed25519 over the canonical
  manifest bytes. `trust.required: true` is reserved for curated directories
  and SHOULD NOT be used by general repos.
- Clients pin the pubkey on first use (TOFU) and MUST surface an explicit
  warning when the key changes.
- Signature status is a UI badge (`verified` / `unverified` / `failed`), never
  an admission gate.
- Content integrity within an instance remains Core v1 `content_hash`
  (sha256); Repo v1 adds no content-level duties.

Capability tiers (informative, enforced by clients):

| Tier | Form | Execution surface | Distribution |
|:---|:---|:---|:---|
| L0 | OTT data instance | none | allowed |
| L1 | Declarative rule | restricted interpreter | allowed |
| L2 | Bridge (real-time API) | protocol adapter, local credentials | allowed |
| L3 | Fetch script (e.g. Python) | full code execution | **MUST NOT be distributed via Repo v1**; local adapter `scripts/` only |

Invariant: nothing a client obtains through network subscription has an
arbitrary code execution surface.

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

## Security Considerations

- A malicious repo can only supply data: no code execution at L0/L1, no
  credential access at L2, and L3 is undistributable by rule.
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
| Source discovery, subscription, mirrors, trust, directories | Repo v1 (this document) |
| Scripts, storage, admin APIs | Reference adapter (unchanged, out of protocol) |

## Future Work (explicitly out of v1)

- Content-addressed distribution (`by-hash` endpoints, multihash) for
  cross-instance dedup / CDN / P2P.
- Arbitrary range reads; Collection objects; full revision history
  (already deferred by Core v1).
- Client SDK once a second client exists.
