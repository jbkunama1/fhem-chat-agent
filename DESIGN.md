# Home Studio: Design und Abfragemenü

## Web

Bunte dunkle Oberfläche mit Mint-, Indigo- und Apricot-Akzenten, eigener SVG-Hausgrafik, mobilen Vorlagenkarten, Chatblasen und einklappbaren Werkzeugdetails. Keine externen Fonts, CDNs oder Bilddienste. Keine vorgetäuschten Live-Messwerte.

Vorlage wählen, exakten FHEM-Gerätenamen eintragen, In den Chat übernehmen anklicken, Text prüfen und Senden. Die Vorlagen sind im Modul menu.py zentral definiert und werden über den geschützten Endpunkt /api/menu geladen. Keine automatische Abfrage beim bloßen Anklicken einer Web-Vorlage.

## Telegram

/start zeigt ein lokal erzeugtes PNG-Hausbanner und Inline-Menü. /menu öffnet die Vorlagen ohne neues Banner, /cancel verwirft nur die laufende Vorlageneingabe, nicht eine separate Ausführungsfreigabe. Das Menü steht nach Antworten erneut zur Verfügung. Die Darstellung nativer Telegram-Buttons richtet sich nach dem Telegram-Client; das bunte Branding steckt im Banner und in den Emoji-Labels.

Vorlage anklicken und danach den exakten Gerätenamen senden. Die Vorlage Geräte finden wird direkt als reine Leseanfrage gestartet. Andere Vorlagen fragen Status, Isttemperatur, Schalterzustand, Feuchte, Batterie, Erreichbarkeit oder alle Readings ab. Namen werden nicht ausgedacht; Geräte finden hilft bei der Suche. Aktuell keine dynamische Geräteliste und keine echten historischen Messwertdiagramme.

Gerätenamen-Eingabe läuft nach zehn Minuten ab und geht bei Neustart verloren. Normale freie Textnachrichten bleiben möglich. Ein ausstehender Schreibauftrag blockiert weitere Vorlagen bis zur separaten Freigabe oder Ablehnung. Das Menü verwendet dieselben Backend-Freigaben wie bisher; Inline-Menüaktionen umgehen sie nicht.

## Betrieb

Der Docker-Einstiegspunkt lautet jetzt ui_app:app. ui_app erweitert die vorhandene FastAPI-App und setzt deren Telegram-Lebenszyklus; keine zweite Bot-Polling-Schleife. Manuell starten: uvicorn ui_app:app --host 0.0.0.0 --port 8080. Stack-Variablen und Datenvolume bleiben unverändert. Nach erfolgreichem Imagebau in Portainer das neue Image ziehen und Container aktualisieren.

Tests: python -m unittest discover -s tests -v. Neue Tests prüfen Vorlagen-IDs, Callback-Längen, Pflicht-Gerätenamen, Quotierung und PNG-Erzeugung. Keine Live-Telegram-/MCP-/LLM-Tests ohne Zugangsdaten. Browserdarstellung und vollständiger Containerstart müssen im Deployment geprüft werden.
