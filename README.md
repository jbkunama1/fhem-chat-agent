# FHEM Chat Agent

Eigene Implementierung: deutscher mobiler Web-Chat und optionaler Telegram-Textbot, OpenAI-kompatibles Tool Calling, FHEM-MCP und direkter FHEMWEB-Zugang. Ein Container mit SQLite-Volume. Audio ist noch nicht enthalten.

## Portainer (Docker Standalone)

1. GitHub Actions: erfolgreichen Lauf von Test and publish abwarten. Erst dann existiert das GHCR-Image (amd64/arm64).
2. Bei privatem Paket ghcr.io als Registry in Portainer eintragen: GitHub-Benutzer und PAT mit read:packages. Keine Schlüssel ins Repository schreiben.
3. Stacks > Add stack > Web editor: portainer-stack.yml einfügen.
4. Stack-Variablen anhand .env.example setzen. APP_PASSWORD, OPENAI_API_KEY und für deinen Server MCP_API_KEY setzen. Optional direkten Zugang mit FHEM_URL inklusive /fhem sowie FHEM_USERNAME/FHEM_PASSWORD konfigurieren.
5. Optional TELEGRAM_BOT_TOKEN und TELEGRAM_ALLOWED_USER_IDS (numerische IDs, kommagetrennt) setzen. Nur private Chats; leere Liste sperrt alle. Kein paralleler Telegram-Webhook.
6. Deploy. Web-Chat unter http://SERVER:8088 mit APP_USERNAME (daniel) und APP_PASSWORD öffnen. Öffentlich nur hinter HTTPS-Reverse-Proxy/VPN; Basic Auth nicht über ungeschütztes Internet verwenden.

APP_IMAGE überschreibt das Image; APP_PORT den Hostport. Reproduzierbare Updates: Commit-SHA-Tag statt latest. In Portainer Image neu ziehen und Stack aktualisieren. Volume nicht löschen. Private GitHub-Git-Anmeldung ersetzt keine GHCR-Registry-Anmeldung. localhost in FHEM_URL bezeichnet den Container, nicht deinen FHEM-Server.

## Alternative: lokal bauen

```sh
git clone https://github.com/jbkunama1/fhem-chat-agent.git
cd fhem-chat-agent
cp .env.example .env
joe .env
chmod 600 .env
docker compose up -d --build
```

Private Repositories benötigen Git-Anmeldung. Lokal auf dem Docker-Host gebautes Image kann mit APP_IMAGE=fhem-chat-agent:local im Portainer-Stack verwendet werden. compose.yaml braucht Checkout und .env; für Web Editor portainer-stack.yml verwenden. Swarm nicht unterstützt. Git-Stack-Builds hängen von Portainer-Version und Checkout-Unterstützung ab; empfohlen ist der Image-Stack.

## Einstellungen

Vollständige Variablen: .env.example und portainer-stack.yml.

- OPENAI_BASE_URL: https://9router.arbeitermili.eu/v1; /v1 bei abweichendem Router-Pfad anpassen. OPENAI_MODEL=all_coding muss Function Tool Calling unterstützen.
- MCP_AUTH_HEADER=Authorization und MCP_AUTH_SCHEME=Bearer sind konfigurierbare Defaults, nicht live verifiziert. Für X-API-Key Header ändern und Scheme explizit leer setzen.
- MCP_TRANSPORT=streamable-http oder sse. Kein automatisches Raten von Headern/Transport.
- FHEM_URL leer deaktiviert direkte Befehle. Vollständiger HTTP(S)-Pfad inklusive /fhem, ohne Query oder Zugangsdaten. FHEM_VERIFY_TLS=true belassen, false nur für bewusst akzeptierte interne Zertifikate.
- APPROVAL_TTL_SECONDS=120. DATA_DIR intern /data. Schlüssel bleiben im Backend.

## Freigaben

Nur MCP-Namen mit fhem_ werden angeboten. Bekannte Lese-Tools dürfen direkt laufen. Alle anderen Aufrufe, insbesondere set, attr, define, delete, freie Kommandos, Mehrfach-Set und alle direkten Webbefehle, benötigen eine einmalige Button-Freigabe. Backend bindet unveränderte Argumente und Ziel an deinen Benutzer/Privatchat. Freigaben laufen ab, werden vor Ausführung atomar verbraucht und bei Neustart storniert. Ein Klick genehmigt genau einen Toolaufruf; Mehrfach-Tools und freie Kommandos können mehrere enthaltene Aktionen auslösen, daher vollständig prüfen.

Keine automatische Wiederholung bei Timeout und kein stiller Transportwechsel. Ausgang kann unklar bleiben: zuerst Gerätestatus prüfen. HTTP 200 oder leere Antwort ist allein kein Erfolgsnachweis. MCP-Fehler und FHEM-Textantworten erscheinen im Chat.

Auf Nutzerwunsch kein FHEM-CSRF-Handling: kein Tokenabruf, kein fwcsrf. Direkte Befehle senden POST-Formulardaten cmd und XHR=1 mit HTTP Basic Auth. Ziel-FHEM muss solche Requests akzeptieren. Anwendung verändert keine FHEM-Sicherheitseinstellungen und behandelt Ablehnungen nicht als Erfolg. FHEMWEB ohne diesen Schutz nicht öffentlich exponieren. Die Chatoberfläche hat davon unabhängig geschützte JSON-Endpunkte.

## Betrieb und Grenzen

Ein Web-Benutzer, je Telegram-Nutzer eigener Verlauf; nur ein Worker/Container pro Datenvolume und Bot. Web: Neuer Chat leert Verlauf und verwirft offene Freigaben. Ab etwa 400 Nachrichten keine neuen Chat-Aufträge; Telegram-Verlauf derzeit durch gesichertes Umbenennen der Datenbank bei gestopptem Dienst zurücksetzen (betrifft alle). Neustart markiert unaufgelöste Toolaufrufe als unterbrochen; keine automatische Ausführung.

Backup: Dienst stoppen, Volume chat-data sichern. Verläufe enthalten Geräte-/Personendaten; kein automatisches Löschkonzept. /health prüft nur den Prozess. Diagnose: MCP 401 -> Header/Key; KI 404 -> /v1; keine Tools -> Transport/fhem_-Namen; FHEM-Ablehnung -> Auth, Netzwerk, Rechte und CSRF-Konfiguration der Zielinstanz.

## Tests / Validierungsstand

```sh
python -m unittest discover -s tests -v
python -m compileall -q app.py guard.py
```

Sieben lokale Policy-/Persistenztests: Lese-Whitelist, unveränderte Argumente, Einmaligkeit, fremde Benutzer, Ablauf, Ablehnung und Neustart-Wiederherstellung. CI installiert zusätzlich Abhängigkeiten und prüft App-Import vor Imagebau. Live-MCP, FHEM, 9router und Telegram sind ohne Schlüssel nicht end-to-end getestet; lokaler Docker-Build nicht verifiziert. Erst erfolgreichen CI-/Image-Build prüfen und mit ungefährlichen Geräteabfragen beginnen.
