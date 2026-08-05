# TAM — Financial Due Diligence Engine

A local proof-of-concept M&A due-diligence tool: FastAPI backend (Python) +
Next.js frontend (TypeScript). See `backend/README.md`-equivalent notes in
`backend/.env.example` for backend configuration, and `frontend/README.md`
for the frontend.

## Security

This is a local POC, but it's designed to handle real financial documents
(general ledgers, income statements, credit agreements), so a few things are
worth understanding before running it anywhere beyond your own machine:

- **Authentication**: real accounts (Argon2id-hashed passwords, JWT session
  cookies) — see `backend/app/api/v1/auth.py`. There is no email service, so
  password-reset returns the reset link directly in the API response instead
  of emailing it; replace that with a real provider (SES, SendGrid, etc.)
  before this ever serves real users.
- **Authorization**: every deal is owned by exactly one user; every
  deal-scoped endpoint checks ownership (`app/api/v1/deps.py::require_deal_owner`)
  before returning anything. A user cannot access another user's deal by
  guessing or altering a deal ID in the URL.
- **At-rest encryption**: every file this app writes — deal/user records,
  uploaded documents, processed pipeline output — is encrypted with
  AES-256-GCM before it touches disk (`app/security/file_crypto.py`,
  `app/storage/json_io.py`). The master key is a single `FILE_ENCRYPTION_KEY`
  env var for now; **move it to a real KMS/Vault (AWS KMS, GCP KMS, HashiCorp
  Vault, etc.) before any production use** — the key-loading is isolated to
  one settings field (`app/config.py`) specifically so that swap is clean.
- **Transport security**: the backend does **not** terminate TLS itself. It
  sends a `Strict-Transport-Security` header on every response, but you must
  put a reverse proxy or load balancer in front of it for any deployment
  reachable over a network you don't fully trust (plain `localhost` dev is
  fine without one). Two examples below.
- **Access logging**: every document read/download/decrypt is appended as one
  JSON line to `backend/data/access.log` (`app/security/access_log.py`) —
  who accessed what, when. Useful for a due-diligence audit trail.

### Local HTTPS via a reverse proxy

**Caddy** (simplest — auto-provisions a locally-trusted cert via its internal CA):

```caddyfile
# Caddyfile
localhost {
    reverse_proxy localhost:8000
}
```

```bash
caddy run
# now hit https://localhost instead of http://localhost:8000
```

**nginx + mkcert** (if you already run nginx):

```bash
# One-time: install a locally-trusted CA and issue a cert for localhost
mkcert -install
mkcert localhost
```

```nginx
# nginx.conf
server {
    listen 443 ssl;
    server_name localhost;

    ssl_certificate     localhost.pem;
    ssl_certificate_key localhost-key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

In either case, the reverse proxy is what makes the `Strict-Transport-Security`
header meaningful — browsers only start enforcing HSTS after seeing it over an
actual HTTPS connection.
