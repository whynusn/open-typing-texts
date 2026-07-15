# OTT Compatibility Matrix

## Current Matrix

| Component | Version / Branch | Service Profile | Static Profile | Legacy |
|:---|:---|:---:|:---:|:---:|
| OTT Core | `1.0` | yes | yes | compatibility only |
| ott-adapter | `0.5.0` | `/ott/v1/*` | `ott.json`, `sources.json`, `entries.json`, `entries/*`, `segments/*` | `/registry_index.json`, `/content/*`, `/api/*` |
| typetype | `feature/unified-text-load-center` | entries, sources, details, segments | entries, sources, details, segments | registry/content fallback |

## Canonical Fixtures

`tests/fixtures/ott/` is the canonical compatibility pack. Other clients should be able to consume:

- `valid-inline-content.json`
- `valid-entries-content.json`
- `valid-explicit-ids-content.json`
- `valid-duplicate-title-content.json`
- `valid-entry-summary.json`
- `valid-segment.json`
- `valid-segmented-entry-detail.json`
- `expected-normalized-entries.json`
- `expected-segmented-entry.json`
- `static-profile/ott.json`
- `static-profile/sources.json`
- `static-profile/entries.json`
- `static-profile/entries/ent_static_fixture.json`
- `static-profile/segments/rev_static_fixture/*.txt`
- invalid fixtures that must fail validator checks

The expected normalized outputs are generated from `ott_adapter.ott_core` and are intentionally checked into the repository so client implementations can detect field-level protocol drift.

## Client Contract

- Clients use `/ott/v1` Service Profile first.
- Clients use Static Profile when a server process is not available.
- Clients may keep legacy registry/content fallback for compatibility, but must not treat `/api/*` as the public client protocol.
- Entry progress keys should include `entry_id` and `current_revision_id`.
- Segmented entries must be consumed through server-defined segments; clients must not fetch full long-form content to split locally.
