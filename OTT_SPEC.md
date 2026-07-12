# OTT Core v1 Specification

> Status: draft | Scope: read-only text distribution protocol

OTT Core v1 defines a client-facing protocol for typing text discovery and
delivery. Fetch scripts, local storage engines, admin APIs, and Web UI behavior
are reference implementation concerns; clients such as typetype should depend
only on this read-only protocol.

## Version Vocabulary

| Name | Current | Meaning |
|:---|:---|:---|
| OTT Core | `1.0` | Data model and client-facing distribution contract |
| Service Profile path | `/ott/v1` | HTTP routing namespace for Core v1 |
| Adapter package | `0.5.0` | Reference implementation release version |
| Legacy index | `registry_index.json` `version: 2` | Historical adapter index schema, not the OTT Core version |

There is no public "OTT v2" protocol in this repository. Old adapter UI/API
text that used "v2" referred to the local adapter implementation generation,
not the OTT Core protocol.

## Profiles

| Profile | Purpose |
|:---|:---|
| Core v1 | Shared data model: source, entry summary, entry detail, segment |
| Service Profile | Read-only HTTP API under `/ott/v1` |
| Static Profile | Static files that expose the same model without a server process |
| Admin Profile | Optional reference-adapter management API under `/ott-admin/v1` |

Existing `/api/*` endpoints are adapter-private / legacy aliases. They are not
the long-term client protocol and should not be used by typing clients.

## Core Objects

### Source

```json
{
  "source_key": "poem",
  "label": "诗句",
  "description": "用户本地生成的诗句来源",
  "tags": ["poem"],
  "rights_summary": "user-provided"
}
```

### EntrySummary

Entry lists are summary-only by default. They must not include full text.

```json
{
  "entry_id": "ent_...",
  "source_key": "poem",
  "title": "标题",
  "preview": "前 100 字左右的预览",
  "char_count": 1200,
  "content_mode": "inline",
  "current_revision_id": "rev_...",
  "updated_at": "2026-07-09T10:00:00+08:00",
  "tags": ["诗句"]
}
```

### EntryDetail

Inline text may include full content:

```json
{
  "entry_id": "ent_...",
  "source_key": "poem",
  "title": "短文标题",
  "content_mode": "inline",
  "char_count": 420,
  "current_revision_id": "rev_...",
  "content_hash": "sha256:...",
  "content": "完整正文"
}
```

Segmented text declares segment metadata and always omits full content:

```json
{
  "entry_id": "ent_...",
  "source_key": "novel",
  "title": "长文标题",
  "content_mode": "segmented",
  "char_count": 180000,
  "current_revision_id": "rev_...",
  "content_hash": "sha256:...",
  "segment_count": 180,
  "segment_size_hint": 1000
}
```

### Segment

```json
{
  "entry_id": "ent_...",
  "revision_id": "rev_...",
  "index": 1,
  "start_char": 0,
  "end_char": 1000,
  "char_count": 1000,
  "content_hash": "sha256:...",
  "content": "本段正文"
}
```

Character positions are typing-oriented character offsets, not byte offsets.
Core v1 intentionally does not define arbitrary range reads.

## Error Envelope

OTT Service Profile errors use a stable JSON envelope:

```json
{
  "error": {
    "code": "entry_not_found",
    "message": "entry not found: ent_..."
  }
}
```

Clients should branch on `error.code`, not on localized `message` text.

## Service Profile

```http
GET /ott/v1/capabilities
GET /ott/v1/sources
GET /ott/v1/entries?source_key=&page=&limit=&q=
GET /ott/v1/entries/{entry_id}
GET /ott/v1/entries/{entry_id}/revisions/{revision_id}/segments/{index}
```

## Static Profile

```text
/ott.json
/sources.json
/entries.json
/entries/{entry_id}.json
/segments/{revision_id}/{index}.txt
```

`/entries.json` is the static discovery manifest containing `EntrySummary`
objects. `/entries/{entry_id}.json` returns one `EntryDetail`. For segmented
entries, the detail omits full content and clients read segment text from
`/segments/{revision_id}/{index}.txt`.

## Identity Rules

- `entry_id` identifies the stable text entity.
- `current_revision_id` identifies the current text revision.
- `content_hash` verifies the current full content or segment content.
- Clients should key progress as `ott:{authority}:{entry_id}@{revision_id}`.

Reference implementations may derive missing `entry_id` values from legacy
content files, but published content should persist explicit IDs whenever
possible. `revision_id` changes when the content hash changes.

Entry summary lists are discovery data. Service implementations should serve
them from an index or manifest and avoid returning or building responses from
full text bodies on every list request.

## Admin Profile

The Admin Profile is optional and belongs to the adapter reference
implementation, not OTT Core. It may create sources, run fetch scripts, rebuild
indexes, manage schedules, and serve the embedded Web UI.

```http
GET /ott-admin/v1/status
GET /ott-admin/v1/sources
POST /ott-admin/v1/sources
DELETE /ott-admin/v1/sources/{source_key}
GET /ott-admin/v1/scripts
GET /ott-admin/v1/scripts/{source_key}
POST /ott-admin/v1/scripts
POST /ott-admin/v1/scripts/{source_key}/test
POST /ott-admin/v1/scripts/{source_key}/run
POST /ott-admin/v1/scripts/{source_key}/save
POST /ott-admin/v1/scripts/{source_key}/rename
GET /ott-admin/v1/scripts/{source_key}/cron
POST /ott-admin/v1/scripts/{source_key}/cron
GET /ott-admin/v1/entries
GET /ott-admin/v1/entries/recent
POST /ott-admin/v1/entries
DELETE /ott-admin/v1/entries/{source_key}
POST /ott-admin/v1/refresh
```

The adapter keeps legacy `/api/*` aliases for compatibility, but new Web UI and
tooling code should call `/ott-admin/v1/*`.
