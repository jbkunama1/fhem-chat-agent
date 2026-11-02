# fhem-chat-agent

Self-hosted FHEM-KI-Chatassistent (deutsch, mobilfreundliche Web-UI) mit optionalem Telegram-Textbot. Beide nutzen denselben Agent-Backend-Workflow mit persistenter SQLite-Historie und Audit-Log in `/data`.

## Sicherheits- und Betriebsgrenzen

- **Keine automatische Live-Steuerung ohne Freigabe**: Jede Mutation (`set`, `attr`, `define`, `delete`, `raw`, `set_multiple`) braucht **einzeln** menschliche Freigabe im Backend.
- Direkter FHEMWEB-Rohbefehl (`fhemweb_raw_command`) braucht **immer** Freigabe, auch bei scheinbar read-only Befehlen.
- Es gibt **keine** automatische Freigabe via LLM-Text („ja/nein“) oder LLM-Tool.
- Bei Timeout bei Mutationen gibt es **keinen Retry** und **kein stilles Fallback** zwischen MCP/FHEMWEB.
- Unklare Ergebnisse werden als **unsicher** gemeldet.
- UI rendert Tool-/Chat-Inhalt als Text (XSS-Schutz).
- Geheimnisse werden nicht geloggt (keine Ausgabe von API-Keys, Authorization, Credential-URLs).

## Anforderungen an FHEM

- Direkte FHEMWEB-Requests gehen an `FHEM_URL` (inkl. `/fhem`) als `?cmd=<urlencoded>&XHR=1`.
- Basic Auth optional via `FHEM_USERNAME`/`FHEM_PASSWORD`.
- `FHEM_VERIFY_TLS` steuert Zertifikatsprüfung.
- **Bewusst kein fwcsrf/csrf-Token-Handling** (explizite Anforderung). Falls FHEM ablehnt, wird das als Fehler gemeldet.
- FHEM-Schutzmechanismen werden durch die App **nicht** deaktiviert.

## OpenAI-/MCP-Konfiguration

- Modell: `all_coding`
- `OPENAI_BASE_URL` default: `https://9router.arbeitermili.eu/v1`
  - Wichtig: kompatible Endpunkte meist mit `/v1`.
- `OPENAI_API_KEY` nur über Environment.
- `MCP_SERVER_URL` default: `https://haimcp.arbeitermili.eu/mcp/cms1vfcpi00042bs248msptyv`
- `MCP_API_KEY` nur über Environment.
- Header/Schema konfigurierbar mit:
  - `MCP_AUTH_HEADER` (default `Authorization`)
  - `MCP_AUTH_SCHEME` (default `Bearer`, leer für `X-API-Key`-Stil)
- Transport:
  - `MCP_TRANSPORT=streamable_http` (default)
  - `MCP_TRANSPORT=sse`

## Tooling-Regeln

- MCP-Tool-Discovery mit Pagination.
- Exponiert werden nur FHEM-Tools (Prefix-Filter `fhem*`) plus `fhemweb_raw_command`.
- JSON-Schemas der entdeckten Tools werden unverändert übernommen und serverseitig validiert.
- Read-only-Toolfreigabe ist auf bekannte Listen-/Such-/Reading-Tools begrenzt.
- Unbekannte Tools benötigen Freigabe.

## Web-Auth / API-Schutz

- `APP_USERNAME` und `APP_PASSWORD` sind Pflicht (kein Default-Passwort).
- Alle Chat-/History-/Approval-APIs sind geschützt.
- JSON-Mutationsrequests unter `/api/*` nutzen Same-Origin-Prüfungen (`Origin`/`Referer`).

## Telegram (optional)

- Optionales Long-Polling/Webhook-Handling (hier Webhook-Endpoint + Policy).
- Nur private Chats.
- `TELEGRAM_ALLOWED_USER_IDS` fail-closed.
- Callback-Sender/Chat-Zuordnung wird geprüft.

## Schnellstart lokal

1. `.env.example` nach `.env` kopieren und Variablen setzen.
2. Starten:

```bash
docker compose up --build
```

App auf `http://localhost:${PORT:-8088}`.

## Portainer Web Editor (exakt)

1. **Stacks** → **Add stack**
2. Name vergeben, Inhalt von `portainer-stack.yml` in den Web Editor kopieren.
3. Unter **Environment variables** mindestens setzen:
   - `APP_USERNAME`, `APP_PASSWORD`
   - `OPENAI_API_KEY`
   - `MCP_API_KEY` (falls MCP gesichert)
   - optional `FHEM_*`, `TELEGRAM_*`
4. `IMAGE=ghcr.io/jbkunama1/fhem-chat-agent:latest` (oder festen Tag)
5. **Deploy the stack**

## GHCR initialer Build / private Registry

Repository ist privat; bei Pull Requests wird kein Publishing mit Secrets ausgeführt.

- Workflow: `.github/workflows/ci-image.yml`
- Publish nur bei Push auf Default-Branch + `workflow_dispatch`
- Rechte minimal: `contents: read`, `packages: write` nur im Image-Job.

Für private GHCR-Nutzung in Portainer:

1. In GitHub einen PAT mit `read:packages` erstellen.
2. In Portainer unter **Registries** `ghcr.io` hinzufügen.
3. Username = GitHub-User, Password = PAT.
4. Stack deployen.

## Git-basierter Build (Alternative)

- Möglich über lokale/CI-Builds mit Dockerfile.
- Einschränkung: kein direktes Auto-Deploy in dieser App; Deploy bleibt manuell.

## Reverse Proxy / HTTPS

- App selbst liefert HTTP auf internem Port (`8088` default).
- HTTPS via Reverse Proxy (z. B. Caddy/Traefik/Nginx) terminieren.
- Basic Auth der App bleibt zusätzlich aktiv.

## Backup / Update

- Persistenz liegt in Docker-Volume (`/data`).
- Backup: Volume sichern.
- Update: neues Image ziehen, Stack neu deployen, Volume behalten.

## Troubleshooting MCP Header/Transport

- `401/403` am MCP:
  - `MCP_AUTH_HEADER`, `MCP_AUTH_SCHEME`, `MCP_API_KEY` prüfen.
  - Für API-Key-Header ohne Prefix: `MCP_AUTH_SCHEME=` (leer).
- Transportprobleme:
  - `MCP_TRANSPORT=streamable_http` oder `sse` wechseln.

## Health / Readiness

- `GET /health` → Basisstatus
- `GET /ready` → Konfigdiagnose ohne Secrets

## Tests

```bash
pytest -q
```

Tests mocken LLM/MCP/FHEM/Telegram für:

- Discovery-Filter
- Read/Write-Gating + Freigabepflicht
- Kein Execute vor Approval
- Falscher User/Konversation
- Expired/Replayed/Nonce-Manipulation
- Denial-Flow
- Direkter Raw-Command (Encoding + Basic Auth, ohne fwcsrf)
- Timeout ohne Retry
- Auth + Telegram-Allowlist
- Chat-Fortsetzung nach Approval

## Wichtiger Hinweis

Diese Anwendung führt **kein** automatisches Deployment und **keine** automatische Live-Haussteuerung ohne Freigabe durch.
