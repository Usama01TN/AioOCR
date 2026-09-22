# Deployment

## Local

```bash
pip install -e ".[api,local]"
export OCRROUTE_HOME=/var/lib/ocrroute
ocrroute setup
ocrroute serve --host 0.0.0.0 --port 20256
```

## Docker

```bash
docker compose up -d
```

Image runs API + panel on port **20256**. Volume mounts `OCRROUTE_HOME`.

## SQLite notes

- `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`
- Backup with `ocrroute db backup ./backup.db` (safe while running)
- Nightly maintenance: cache expiry, retention rollup, `PRAGMA optimize`

## Reverse proxy

Point TLS terminator at `:20256`. Panel sessions need sticky cookies.
Optional trusted-header auth: `OCRROUTE_TRUSTED_HEADER_AUTH=1`.
