# Security

- API keys: SHA-256 at rest, shown once (`ocrr_` prefix)
- Provider secrets: Fernet (`OCRROUTE_SECRET_KEY` or `~/.ocrroute/secret.key` mode 0600)
- Log redaction on every structlog record
- **SSRF guard** on user URLs: block private/loopback/link-local/metadata, cap redirects & size
- Upload limits: bytes, pixels, page count; MIME sniff by content
- Artifact paths never influenced by user input
- CORS closed by default; security headers; panel CSRF; login rate-limit; optional TOTP
- `privacy_mode`: no input persistence, memory-only cache, API engines refused unless allow-listed
