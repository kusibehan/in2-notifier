# IN2 Noten-Notifier – vorbereitete Version

Stündlicher Abruf des BZU-Notenbuchs, Vergleich mit dem letzten Stand und generische Push-Mitteilung über ntfy. Noch NICHT live in GitHub getestet. Die Navigation und Notentabelle wurden im angemeldeten Browser geprüft; der eigenständige Scraper braucht einen echten Testlauf.

## Einrichtung

1. Privates GitHub-Repository `in2-notifier` mit README erstellen und für ChatGPT freigeben. Dateien dieses Pakets ins Repository übernehmen (inklusive `.github`). Keine Zugangsdaten hochladen.
2. Auf deinem eigenen Computer Python 3.12 installieren. Im Projektordner:
   ```sh
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   python login.py
   ```
   Im geöffneten Browser selbst anmelden. Passwort wird nicht vom Script gespeichert. Die Sitzung in `.auth/state.json` ermöglicht Kontozugriff und muss geheim bleiben.
3. ntfy-App auf dem iPhone installieren. Einen zufälligen Topic-Namen erzeugen, z.B. mit `python -c "import secrets; print(secrets.token_hex(24))"`. Diesen Namen in der App auf `https://ntfy.sh` abonnieren. Kostenlose Topics sind nicht zugriffsgeschützt: Name geheim halten. Es wird nur eine allgemeine Meldung gesendet, keine Note und kein Name.
4. Unter Repository → Settings → Secrets and variables → Actions → Secrets hinterlegen:
   - `IN2_STORAGE_STATE`: kompletter Inhalt der lokalen `.auth/state.json`.
   - `NTFY_TOPIC`: zufälliger Topic-Name.
   - `STATE_HMAC_KEY`: separat erzeugter zufälliger Wert (gleicher Befehl wie oben). Dauerhaft beibehalten.
   Keine Secrets hier im Chat posten. Die aktuelle Chat-Browsersitzung wird nicht exportiert.
5. GitHub Actions Workflow manuell mit `test_push=true` starten. Danach ohne Test-Push starten. Erster erfolgreicher Abruf legt nur den Vergleichsstand an.
6. Kostenpflichtige Actions-Nutzung im GitHub-Billing ausschliessen (kein Zahlungsmittel oder passendes hartes Budget mit Stop-Nutzung aktivieren; bestehende andere Projekte berücksichtigen). GitHub Free hat laut geprüfter Dokumentation 12 USD enthaltenes Rechenkontingent/Monat, entsprechend etwa 2000 Minuten auf dem Standard-Linux-Runner. Dieses Kontingent kann mit anderer Nutzung geteilt sein. Speicher ebenfalls beachten.
7. Erst nach zwei erfolgreichen Testläufen und Kostenprüfung unter Actions → Variables `NOTIFIER_ENABLED=true` setzen. Ohne diese Variable läuft kein geplanter Job.

## Betrieb und Grenzen

- Stündlich zur Minute 23, UTC; GitHub-Zeitpläne können verspätet starten. Kein Echtzeitversprechen.
- Joblimit zwei Minuten: höchstens ca. 1488 Runner-Minuten für 744 stündliche Läufe im 31-Tage-Monat, zusätzliche manuelle Läufe und andere Nutzung nicht enthalten. Installation kann das Limit überschreiten; dann erst optimieren und Kontingent neu berechnen, nicht blind erhöhen.
- Ablauf der IN2-Sitzung: Job schlägt fehl; GitHub-Fehlerbenachrichtigungen aktivieren. `login.py` erneut ausführen und Secret ersetzen. Ob IN2 eine von einem anderen Rechner gespeicherte Sitzung auf GitHub akzeptiert und wie lange sie hält, ist noch ungetestet.
- Vergleichsstand enthält nur HMAC-Fingerprints, keine Klartextnoten; bleibt im privaten Repository. Titel-/Datumsänderungen zählen als neue Prüfung. Leere zukünftige Noten ignoriert. Gelöschte Noten werden nicht gemeldet.
- Scheitert Push, bleibt der alte Stand erhalten. Scheitert das Speichern nach erfolgreichem Push, kann die Meldung beim nächsten Lauf nochmals kommen (keine Exactly-once-Garantie).
- Sitzung, HTML, Screenshots und Noten werden weder als Artefakt noch in Logs ausgegeben.
- Deaktivieren: `NOTIFIER_ENABLED=false` setzen oder Workflow deaktivieren.
- Tests: `python -m unittest -v`. Prüfen Vergleich, Änderungen, leere Noten und fehlerhafte Zeilen; ersetzen keinen Integrationstest.

Quellen: https://docs.github.com/en/billing/concepts/product-billing/github-actions | https://playwright.dev/python/docs/auth | https://docs.ntfy.sh/
