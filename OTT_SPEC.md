# OTT Core v1 Specification

> Status: draft | Scope: read-only text distribution protocol

OTT Core v1 defines a client-facing protocol for typing text discovery and
delivery. Fetch scripts, local storage engines, admin APIs, and Web UI behavior
are reference implementation concerns; clients such as typetype should depend
only on this read-only protocol.

## Profiles

| Profile | Purpose |
|:---|:---|
| Core v1 | Shared data model: source, entry summary, entry detail, segment |
| Service Profile | Read-only HTTP API under `/ott/v1` |
| Static Profile | Static files that expose the same model without a server process |

Existing `/api/*` endpoints are adapter-private / legacy endpoints. They are
not the long-term client protocol.

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
/entries/{entry_id}.json
/segments/{revision_id}/{index}.txt
```

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
