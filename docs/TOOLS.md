# Tools (reserved)

The Tools subsystem is a complete, wired, **empty** scaffold for future
post-processing extensions. v0.1 ships **no working tool**.

- Package: `ocrroute/tools/` with abstract `ToolPlugin` and auto-discovery
- DB tables `tools` / `tool_runs` exist and stay empty
- `GET /v1/tools` → `{ "tools": [], "reserved": true }`
- `POST /v1/tools/{id}/run` → `501` / `tools_reserved`
- Panel `/panel/tools` and desktop Tools page: empty state only
- Pipeline hook `postprocess.apply_tools` is an identity function today

See `ocrroute/tools/README.md` for the plugin contract and idea list.
