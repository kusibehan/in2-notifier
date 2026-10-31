
"""IN2 Notifier. Never logs grades, credentials or raw errors."""

import hashlib
import hmac
import json
import os
import re
import sys

from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

DASHBOARD_URL = "https://in2.tam.ch/dashboard"

URL = (
    "https://in2.tam.ch/intranet/"
    "bzu/default/gradebook/index"
)

STATE = Path(".state/grades.json")

NOTEN_SELECTOR = (
    "body > app-root > ion-app > ion-router-outlet > "
    "app-dashboard > gr-components-page-default-layout > "
    "div > ion-split-pane > div > gr-components-menu > "
    "ion-menu > ion-menu-list > ion-menu-item:nth-child(5)"
)

CURRENT_STEP = "Start"


def set_step(step):
    global CURRENT_STEP
    CURRENT_STEP = step
    print("Schritt:", step, flush=True)


def fingerprint(value, key):
    data = json.dumps(
        value,
        ensure_ascii=False
    ).encode()

    return hmac.new(
        key.encode(),
        data,
        hashlib.sha256
    ).hexdigest()


def snapshot(courses, key):
    result = {}

    for course, rows in courses:
        for cells in rows:
            if len(cells) != 5:
                raise ValueError(
                    "Unexpected grade row"
                )

            title, value, date, weight, _ = cells

            if not re.fullmatch(
                r"\d{2}\.\d{2}\.\d{4}",
                date
            ):
                raise ValueError(
                    "Unexpected grade date"
                )

            if not value:
                continue

            if (
                not re.fullmatch(
                    r"[1-6](?:[.,]\d+)?",
                    value
                )
                or not 1 <= float(
                    value.replace(",", ".")
                ) <= 6
            ):
                raise ValueError(
                    "Unexpected grade value"
                )

            identity = fingerprint(
                [course, title, date],
                key
            )

            if identity in result:
                raise ValueError(
                    "Ambiguous duplicate exam"
                )

            result[identity] = fingerprint(
                [value, weight],
                key
            )

    return result


def changes(old, new):
    return sum(
        old.get(k) != v
        for k, v in new.items()
    )


def notify(message):
    set_step("Push-Benachrichtigung senden")

    topic = os.environ["NTFY_TOPIC"]

    if not re.fullmatch(
        r"[A-Za-z0-9_-]{24,128}",
        topic
    ):
        raise ValueError("Invalid ntfy topic")

    request = Request(
        "https://ntfy.sh/" + topic,
        data=message.encode(),
        headers={
            "Title": "IN2 Noten",
            "Click": URL
        },
        method="POST"
    )

    with urlopen(
        request,
        timeout=15
    ) as response:
        if response.status != 200:
            raise RuntimeError(
                "Notification failed"
            )


def scrape(auth):
    set_step("Playwright starten")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

        try:
            set_step("Gespeicherte Sitzung laden")

            context = browser.new_context(
                storage_state=auth,
                viewport={
                    "width": 1600,
                    "height": 900
                }
            )

            page = context.new_page()
            page.set_default_timeout(20000)

            # 1. Dashboard oeffnen
            set_step("Dashboard oeffnen")

            page.goto(
                DASHBOARD_URL,
                wait_until="domcontentloaded",
                timeout=30000
            )

            # 2. Maus ueber Noten bewegen
            set_step("Noten-Menue oeffnen")

            noten = page.locator(
                NOTEN_SELECTOR
            )

            noten.wait_for(
                state="visible",
                timeout=20000
            )

            noten.hover()

            # 3. Untermenue Notenbuch anklicken
            set_step("Notenbuch oeffnen")

            notenbuch = page.get_by_text(
                "Notenbuch",
                exact=True
            )

            notenbuch.wait_for(
                state="visible",
                timeout=20000
            )

            notenbuch.click()

            # 4. Eingebettetes Notenbuch finden
            set_step("Notentabelle suchen")

            frame = page.frame_locator("iframe")

            frame.get_by_role(
                "treegrid"
            ).wait_for(
                timeout=20000
            )

            # 5. Kurse suchen
            set_step("Kurse suchen")

            expand = frame.get_by_role(
                "link",
                name="Expand",
                exact=True
            )

            count = expand.count()

            if not 1 <= count <= 30:
                raise RuntimeError(
                    "Unexpected course count"
                )

            print(
                "Kurse gefunden:",
                count,
                flush=True
            )

            # 6. Alle Kurszeilen stabil markieren
            set_step("Kurszeilen vorbereiten")

            for i in range(count):
                link = expand.nth(i)

                row = link.locator(
                    "xpath=ancestor::tr[1]"
                )

                row.evaluate(
                    """(element, index) => {
                        element.setAttribute(
                            'data-in2-course',
                            String(index)
                        );
                    }""",
                    i
                )

            # 7. Alle Kurse auslesen
            courses = []

            for i in range(count):
                set_step(
                    f"Kurs {i + 1}/{count} oeffnen"
                )

                row = frame.locator(
                    f'tr[data-in2-course="{i}"]'
                )

                course = row.inner_text().strip()

                link = row.get_by_role(
                    "link",
                    name="Expand",
                    exact=True
                )

                link.click(
                    timeout=20000
                )

                # Detailzeile des richtigen Kurses
                set_step(
                    f"Kurs {i + 1}/{count} Details laden"
                )

                detail = row.locator(
                    "xpath=following-sibling::tr[1]"
                )

                detail.wait_for(
                    state="attached",
                    timeout=20000
                )

                # Nicht auf columnheader warten.
                # Die Tabelle direkt verwenden.
                tbody = detail.locator(
                    "tbody"
                ).last

                tbody.wait_for(
                    state="attached",
                    timeout=20000
                )

                # Eventuelle Ladeanzeige abwarten
                busy = detail.locator(
                    '[aria-busy="true"], '
                    ".k-loading-mask"
                )

                if busy.count():
                    busy.first.wait_for(
                        state="hidden",
                        timeout=20000
                    )

                # Die Kursdaten werden teilweise
                # asynchron nachgeladen.
                # Drei Sekunden haben beim lokalen
                # Strukturtest funktioniert.
                page.wait_for_timeout(3000)

                set_step(
                    f"Kurs {i + 1}/{count} Zeilen lesen"
                )

                rows = tbody.locator(
                    ":scope > tr"
                ).evaluate_all(
                    """rows => rows.map(
                        r => [...r.children]
                            .filter(
                                c => c.tagName === 'TD'
                            )
                            .map(
                                c => c.innerText.trim()
                            )
                    ).filter(r => r.length)"""
                )

                # Explizite Keine-Daten-Zeile
                if (
                    rows
                    and len(rows[0]) == 1
                    and "Keine" in rows[0][0]
                ):
                    rows = []

                # Kurse ohne Notenzeilen sind erlaubt
                courses.append(
                    (course, rows)
                )

                print(
                    f"Kurs {i + 1}/{count}: "
                    f"{len(rows)} Datenzeilen",
                    flush=True
                )

            print(
                "Alle Kurse ausgelesen.",
                flush=True
            )

            return courses

        finally:
            browser.close()


def main():
    # Push-Test ohne IN2-Zugriff
    if "--test-push" in sys.argv:
        notify(
            "Test: Dein IN2 Notifier ist erreichbar."
        )

        print("Test message sent.")
        return

    set_step("IN2-Sitzung laden")

    auth = json.loads(
        os.environ["IN2_STORAGE_STATE"]
    )

    set_step("HMAC-Schluessel pruefen")

    key = os.environ["STATE_HMAC_KEY"]

    if len(key) < 32:
        raise ValueError(
            "State key too short"
        )

    # Noten abrufen
    courses = scrape(auth)

    # Fingerprints erstellen
    set_step("Noten-Fingerprints erstellen")

    current = snapshot(
        courses,
        key
    )

    if not current:
        raise RuntimeError(
            "No graded exams found"
        )

    # Mit vorherigem Stand vergleichen
    if STATE.exists():
        set_step("Noten vergleichen")

        old = json.loads(
            STATE.read_text()
        )

        total = changes(
            old,
            current
        )

        if total:
            notify(
                "Neue oder geaenderte Note in IN2. "
                "Oeffne dein Notenbuch."
            )

        # Alte Eintraege behalten
        current = old | current

    else:
        print(
            "Initial baseline created; "
            "no old grades notified."
        )

    # Vergleichsstand speichern
    set_step("Vergleichsstand speichern")

    STATE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp = STATE.with_suffix(".tmp")

    temp.write_text(
        json.dumps(
            current,
            sort_keys=True,
            indent=2
        ) + "\n"
    )

    temp.replace(STATE)

    print(
        "Check completed.",
        flush=True
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print(
            "CHECK FAILED",
            file=sys.stderr
        )

        print(
            "Fehler bei Schritt:",
            CURRENT_STEP,
            file=sys.stderr
        )

        print(
            "Fehlertyp:",
            type(exc).__name__,
            file=sys.stderr
        )

        print(
            "Keine Noten oder Zugangsdaten ausgegeben.",
            file=sys.stderr
        )

        sys.exit(1)
