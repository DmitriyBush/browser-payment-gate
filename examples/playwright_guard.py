"""browser-payment-gate with Playwright: an agent's click goes through the gate first.

    pip install "browser-payment-gate[playwright] @ git+https://github.com/DmitriyBush/browser-payment-gate"
    playwright install chromium
    python examples/playwright_guard.py

The page here is served from a string, so the example needs no network.
"""
from playwright.sync_api import sync_playwright

from browser_payment_gate import PaymentBlocked, check, guarded_click

PAGE = """<html><head><title>Plans</title></head><body>
<h1>Choose a plan</h1>
<section><h2>Free</h2><p>$0</p><button id="free">Choose Free</button></section>
<section><h2>Pro</h2><p>$9.99 / month</p><button id="pro">Subscribe</button></section>
<section><p>Questions?</p><button id="faq">Read FAQ</button></section>
</body></html>"""

# Domains where the human allowed committing actions for THIS task. Empty = nowhere:
# the gate then refuses every committing action, whatever the page.
ALLOWED = set()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.route('**/*', lambda route: route.fulfill(body=PAGE, content_type='text/html'))
        page.goto('https://shop.example/plans')

        # 1. Ask without acting.
        for sel in ('#free', '#pro', '#faq'):
            d = check(page, sel, 'click', expected_domains=ALLOWED)
            print('%-6s block=%-5s %-12s %s' % (sel, d.block, d.code, d.reason))

        # 2. Act through the gate: a refused click raises and is NOT performed.
        guarded_click(page, '#faq', expected_domains=ALLOWED)
        try:
            guarded_click(page, '#pro', expected_domains=ALLOWED)
        except PaymentBlocked as e:
            print('handed to the human:', e)
    finally:
        browser.close()
