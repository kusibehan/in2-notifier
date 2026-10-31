"""IN2 notifier. Never logs grades, credentials, or raw exception messages."""
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

URL = 'https://in2.tam.ch/intranet/bzu/default/gradebook/index'
STATE = Path('.state/grades.json')


def fingerprint(value, key):
    return hmac.new(key.encode(), json.dumps(value, ensure_ascii=False).encode(), hashlib.sha256).hexdigest()


def snapshot(courses, key):
    result = {}
    for course, rows in courses:
        for cells in rows:
            if len(cells) != 5:
                raise ValueError('Unexpected grade row')
            title, value, date, weight, _ = cells
            if not re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', date):
                raise ValueError('Unexpected grade date')
            if not value:
                continue
            if not re.fullmatch(r'[1-6](?:[.,]\d+)?', value) or not 1 <= float(value.replace(',', '.')) <= 6:
                raise ValueError('Unexpected grade value')
            identity = fingerprint([course, title, date], key)
            if identity in result:
                raise ValueError('Ambiguous duplicate exam')
            result[identity] = fingerprint([value, weight], key)
    return result


def changes(old, new):
    return sum(old.get(k) != v for k, v in new.items())


def notify(message):
    topic = os.environ['NTFY_TOPIC']
    if not re.fullmatch(r'[A-Za-z0-9_-]{24,128}', topic):
        raise ValueError('Use a long random ntfy topic')
    request = Request('https://ntfy.sh/' + topic, data=message.encode(),
                      headers={'Title': 'IN2 Noten', 'Click': URL}, method='POST')
    with urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError('Notification failed')


def scrape(auth):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(storage_state=auth)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.goto(URL, wait_until='domcontentloaded')
        frame = page.frame_locator('iframe')
        frame.get_by_role('treegrid').wait_for()
        # Open only course rows, never exam or unrelated controls.
        expand = frame.get_by_role('link', name='Expand', exact=True)
        count = expand.count()
        if not 1 <= count <= 30:
            raise RuntimeError('Unexpected course count')
        courses = []
        for _ in range(count):
            link = expand.first
            parent = link.locator('xpath=ancestor::tr[1]')
            course = parent.inner_text().strip()
            link.click()
            detail = parent.locator('xpath=following-sibling::tr[1]')
            detail.get_by_role('columnheader').first.wait_for()
            # Kendo sets aria-busy while fetching remote data.
            page.wait_for_load_state("networkidle", timeout=10000)
            busy = detail.locator('[aria-busy="true"], .k-loading-mask')
            if busy.count():
                busy.first.wait_for(state='hidden')
            # Wait for rows or the explicit empty-state indicator.
            detail.locator('tbody').last.wait_for(state='attached')
            rows = detail.locator('tbody').last.locator(':scope > tr').evaluate_all(
                "rows => rows.map(r => [...r.children].filter(c => c.tagName === 'TD').map(c => c.innerText.trim())).filter(r => r.length)")
            if rows and len(rows[0]) == 1 and 'Keine' in rows[0][0]:
                rows = []
            courses.append((course, rows))
        browser.close()
        return courses


def main():
    if '--test-push' in sys.argv:
        notify('Test: Dein IN2 Notifier ist erreichbar.')
        print('Test message sent.')
        return
    auth = json.loads(os.environ['IN2_STORAGE_STATE'])
    key = os.environ['STATE_HMAC_KEY']
    if len(key) < 32:
        raise ValueError('State key too short')
    current = snapshot(scrape(auth), key)
    if not current:
        raise RuntimeError('No graded exams found; retaining previous baseline')
    if STATE.exists():
        old = json.loads(STATE.read_text())
        # Keep vanished entries to avoid re-notification after temporary omissions.
        total = changes(old, current)
        if total:
            notify('Neue oder geaenderte Note in IN2. Oeffne dein Notenbuch.')
        current = old | current
    else:
        print('Initial baseline created; no old grades notified.')
    STATE.parent.mkdir(exist_ok=True)
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(current, sort_keys=True, indent=2) + '\n')
    temp.replace(STATE)
    print('Check completed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Check failed: session expired, page changed, or service unavailable. Baseline preserved.', file=sys.stderr)
        sys.exit(1)
