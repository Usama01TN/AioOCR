# Decisions

## Rejected: Vite + React SPA panel

**Decision:** Server-rendered Jinja2 + HTMX + Alpine + Tailwind (CLI build committed).

**Why:** Ships inside the Python wheel, no Node.js runtime, works fully offline, live
partials without a SPA. The `/v1` API remains usable by any SPA if an operator prefers one.

## Open questions (v0.1 defaults)

1. **Multi-tenancy:** per-API-key isolation only (no `tenants` table).
2. **Panel auth:** local users table + optional trusted-header mode.
3. **VLM weights:** on-demand download with explicit confirm + disk-size estimate (UI later).
4. **Queue:** in-process asyncio queue persisted via SQLite job rows (single node).
5. **Cost data:** bundled starter price table in `engines.toml`, marked editable / estimates only.

## Engine-layer changes

Engine files under `ocrroute/engines/` are vendored from AioOCR with minimal touch:
dual-import path bootstrap in `ocrroute/engines/__init__.py` so legacy
`from engines.ocrplugin import …` shims resolve. No hard-coded demo keys added.

## Non-overlap with OmniRoute

This milestone uses ports 20256/20257, glossary Route/Attempt/Engine, pure Python,
no chat endpoints, no OmniRoute assets or namespaces.
