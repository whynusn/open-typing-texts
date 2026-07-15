# Release Checklist

## Protocol

- [ ] `OTT_SPEC.md` still names OTT Core `1.0` as the public protocol.
- [ ] `SPEC.md` remains only a pointer to `OTT_SPEC.md` and `LEGACY_SPEC.md`.
- [ ] `registry_index.json version: 2` is described only as legacy adapter schema, not OTT v2.

## Compatibility

- [ ] `uv run pytest -q`
- [ ] `uv run ott-adapter validate tests/fixtures/ott/valid-inline-content.json`
- [ ] `uv run ott-adapter validate --data-dir <fixture-or-local-data-dir>`
- [ ] Service Profile still serves `/ott/v1/capabilities`, `/ott/v1/sources`, `/ott/v1/entries`, entry detail, and segment endpoints.
- [ ] Static Profile can be generated from a fresh data dir and serves `ott.json`, `sources.json`, `entries.json`, `entries/{entry_id}.json`, and `segments/{revision_id}/{index}.txt`.
- [ ] Legacy `/registry_index.json`, `/content/{source_key}.json`, and `/api/*` aliases remain compatibility paths.

## Contributor Safety

- [ ] CI does not run real fetch scripts and does not use `validate-script --run`.
- [ ] New scripts pass `uv run ott-adapter validate-script scripts/fetch_<source>.py`.
- [ ] Contributor PR includes local `validate-script --run` and `validate content/<source>.json` summaries when real crawling is required.
