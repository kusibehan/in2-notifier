"""Run on YOUR computer. Sign in manually; session is never printed."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

path = Path('.auth/state.json')
path.parent.mkdir(mode=0o700, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto('https://in2.tam.ch/login')
    input('Im Browser anmelden, Datenfreigabe pruefen und Dashboard abwarten. Dann hier Enter: ')
    if not page.url.startswith('https://in2.tam.ch/dashboard'):
        raise SystemExit('Dashboard nicht erreicht. Keine Sitzung gespeichert.')
    context.storage_state(path=str(path))
    os.chmod(path, 0o600)
    browser.close()
print('Sitzung in .auth/state.json gespeichert. Nur als GitHub Actions Secret hinterlegen, niemals committen.')
