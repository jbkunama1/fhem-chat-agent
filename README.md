<div align="center">

# 🏠🤖 hAI.FHEMChatAgent

**Dein Zuhause. Dein Assistent.** – Deutscher Mobil-Chat und Telegram-Bot für FHEM mit KI-Tool-Calling, MCP-Anbindung und Einzelfreigabe für jede Schreibaktion.

[![Projektseite](https://img.shields.io/badge/Projektseite-GitHub%20Pages-78e8cc?style=for-the-badge&logo=github&logoColor=white)](https://jbkunama1.github.io/hAI.FHEMChatAgent/)
[![Docker](https://img.shields.io/badge/Docker-amd64%20%7C%20arm64-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://github.com/jbkunama1/hAI.FHEMChatAgent/actions)
[![Portainer](https://img.shields.io/badge/Portainer-Stack-13BEF9?style=for-the-badge&logo=portainer&logoColor=white)](portainer-stack.yml)

![Python](https://img.shields.io/badge/Python-FastAPI-3776AB?logo=python&logoColor=white)
![FHEM](https://img.shields.io/badge/FHEM-Smart%20Home-E4572E)
![MCP](https://img.shields.io/badge/MCP-streamable--http%20%7C%20sse-8299ff)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Volume-003B57?logo=sqlite&logoColor=white)
![Status](https://img.shields.io/badge/Status-Prototyp-ffbc78)
[![Last Commit](https://img.shields.io/github/last-commit/jbkunama1/hAI.FHEMChatAgent?logo=github)](https://github.com/jbkunama1/hAI.FHEMChatAgent/commits/main)

</div>

---

## ✨ Features

| | Feature | Beschreibung |
|---|---|---|
| 💬 | **Web-Chat** | Mobile-first, dunkles Design „Home Studio“ mit Vorlagenkarten |
| 🤖 | **Telegram-Bot** | Inline-Menü, nur private Chats, Whitelist per User-ID |
| 🧠 | **KI-Tool-Calling** | OpenAI-kompatible API (`OPENAI_BASE_URL`, `OPENAI_MODEL`) |
| 🔌 | **FHEM-MCP** | Nur Tools mit Präfix `fhem_`; `streamable-http` oder `sse` |
| 🌐 | **FHEMWEB direkt** | Optional per HTTP Basic Auth (`FHEM_URL` inkl. `/fhem`) |
| 🔐 | **Einzelfreigabe** | `set`, `attr`, `define`, `delete`, freie Kommandos: ein Klick = ein Aufruf |
| 🗄️ | **SQLite-Volume** | Verlauf pro Telegram-Nutzer, Freigaben laufen ab |
| 🐳 | **Ein Container** | Portainer-Stack, GHCR-Image für amd64 und arm64 |

## 🧭 Architektur

```text
 📱 Web-Chat ──┐
               ├──▶ FastAPI (ui_app:app) ──▶ 🧠 LLM (Tool Calling)
 ✈️ Telegram ──┘            │
                            ├──▶ 🔌 FHEM-MCP  (fhem_*)
                            ├──▶ 🌐 FHEMWEB   (optional)
                            └──▶ 🗄️ SQLite    (/data)
```

## 🚀 Schnellstart mit Portainer

1. ✅ In [Actions](https://github.com/jbkunama1/hAI.FHEMChatAgent/actions) den Lauf *Test and publish* abwarten.
2. 🔑 Bei privatem Paket `ghcr.io` als Registry in Portainer eintragen (PAT mit `read:packages`).
3. 📦 *Stacks → Add stack → Web editor*: Inhalt von [`portainer-stack.yml`](portainer-stack.yml) einfügen.
4. ⚙️ Variablen nach [`.env.example`](.env.example) setzen – Pflicht: `APP_PASSWORD`, `OPENAI_API_KEY`, ggf. `MCP_API_KEY`.
5. ▶️ Deploy und `http://SERVER:8088` öffnen.

> ⚠️ Öffentlich nur hinter HTTPS-Reverse-Proxy oder VPN. Keine Schlüssel ins Repository.

```sh
git clone https://github.com/jbkunama1/hAI.FHEMChatAgent.git
cd hAI.FHEMChatAgent
cp .env.example .env
joe .env && chmod 600 .env
docker compose up -d --build
```

## 🔧 Konfiguration

| Variable | Standard | Zweck |
|---|---|---|
| `APP_USERNAME` / `APP_PASSWORD` | `daniel` / Pflicht | Login Web-Chat |
| `OPENAI_BASE_URL` / `OPENAI_MODEL` | Router-URL / `all_coding` | LLM mit Function Calling |
| `MCP_SERVER_URL` / `MCP_API_KEY` | – | FHEM-MCP-Server |
| `MCP_AUTH_HEADER` / `MCP_AUTH_SCHEME` | `Authorization` / `Bearer` | Für `X-API-Key` Scheme leer setzen |
| `MCP_TRANSPORT` | `streamable-http` | oder `sse` |
| `FHEM_URL` | leer | leer = direkte Befehle aus |
| `FHEM_VERIFY_TLS` | `true` | nur bewusst `false` |
| `APPROVAL_TTL_SECONDS` | `120` | Gültigkeit einer Freigabe |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ALLOWED_USER_IDS` | leer | leere Liste sperrt alle |
| `APP_IMAGE` / `APP_PORT` | GHCR latest / `8088` | Image und Hostport |

## 🔐 Sicherheitsmodell

- 🟢 Bekannte Lese-Tools laufen direkt.
- 🟠 Alles andere braucht eine einmalige Button-Freigabe, gebunden an Benutzer, Ziel und Argumente.
- ⏱️ Freigaben verfallen und werden bei Neustart storniert.
- 🚫 Keine automatische Wiederholung, kein stiller Transportwechsel.
- ⚠️ Kein FHEM-CSRF-Handling. FHEMWEB nicht öffentlich exponieren.

## 🧪 Tests

```sh
python -m unittest discover -s tests -v
python -m compileall -q app.py guard.py
```

Live-MCP, FHEM, LLM-Router und Telegram sind ohne Schlüssel nicht End-to-End getestet.

## 🗺️ Roadmap

- [x] Web-Chat, Telegram-Menü, Einzelfreigabe
- [ ] Audio / Sprachnachrichten
- [ ] Dynamische Geräteliste
- [ ] Verlaufsdiagramme
- [ ] Mehrere Web-Benutzer
- [ ] Löschkonzept für Verläufe

## 🩺 Troubleshooting

| Symptom | Ursache |
|---|---|
| MCP 401 | Header, Scheme oder Key |
| KI 404 | `/v1` im Pfad prüfen |
| Keine Tools | Transport oder `fhem_`-Namen |
| FHEM lehnt ab | Auth, Netz, Rechte, CSRF der Zielinstanz |

---

<div align="center">

*Gebaut mit ❤️ von Daniel · hAI.FHEMChatAgent © 2026*

</div>
