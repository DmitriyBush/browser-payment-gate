"""End to end: scan.js inside a real headless browser, then the decision.

The pages are served by Playwright's request routing from the strings below -- no network.
Skipped when Playwright or a browser is not available (pip install playwright;
playwright install chromium -- or an installed Chrome is used).
"""
import pytest

playwright_api = pytest.importorskip('playwright.sync_api')

from browser_payment_gate import check, guarded_click, PaymentBlocked, scan_page  # noqa: E402

ARTICLE = """<html><head><title>Kazakhstan</title></head><body>
<h1>Kazakhstan</h1>
<p>We are making payments easier for farmers. A plateau extending into the steppe.</p>
<table><tr><td>GDP</td><td>$993.672 billion</td></tr><tr><td>Total area</td><td>2,724,900 km2</td></tr></table>
<p>Source <a id="ref" href="https://article.test/wiki/GDP">[12]</a></p>
<div><button id="replies">Show previous replies</button></div>
<footer><a id="help" href="https://article.test/help">Support</a></footer>
</body></html>"""

PLANS = """<html><head><title>Plans</title></head><body>
<h1>Choose a plan</h1>
<section><h2>Free</h2><p>$0</p><button id="free">Choose Free</button></section>
<section><h2>Pro</h2><p>$0.99 / month</p><button id="pro">Subscribe</button></section>
<section><h2>Team</h2><p>$9.99 / month</p><button id="team">Buy</button></section>
<section><p>Questions? Read the FAQ.</p><button id="faq">Read FAQ</button></section>
</body></html>"""

DONATE = """<html><head><title>Donate</title></head><body>
<h1>Help the project</h1>
<div><p>Support us with $5 a month</p><button id="support">Support</button></div>
<div><button id="donate">Donate</button></div>
</body></html>"""

CHECKOUT = """<html><head><title>Checkout</title></head><body>
<h1>Your order</h1>
<form><p>Order total $10.00</p>
<input id="cc" autocomplete="cc-number" name="cardnumber">
<button id="pay" type="submit">Pay $10.00</button></form>
<iframe src="https://js.stripe.com/v3/frame"></iframe>
</body></html>"""

EXPRESS = """<html><head><title>Item</title></head><body>
<h1>Mug</h1><p>$12.00</p><p>Buy with Apple Pay</p>
<div><button id="share">Share</button></div>
</body></html>"""

PAGES = {
    'https://article.test/wiki/Kazakhstan': ARTICLE,
    'https://shop.test/plans': PLANS,
    'https://donate.test/': DONATE,
    'https://shop.test/checkout': CHECKOUT,
    'https://shop.test/item': EXPRESS,
}


@pytest.fixture(scope='module')
def browser():
    with playwright_api.sync_playwright() as p:
        b = None
        for kw in ({}, {'channel': 'chrome'}):
            try:
                b = p.chromium.launch(headless=True, **kw)
                break
            except Exception:  # noqa: BLE001
                continue
        if b is None:
            pytest.skip('no browser for Playwright (playwright install chromium)')
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()

    def serve(route):
        url = route.request.url
        body = PAGES.get(url)
        if body is None:
            return route.fulfill(status=200, body='', content_type='text/html')
        return route.fulfill(status=200, body=body, content_type='text/html')

    ctx.route('**/*', serve)
    pg = ctx.new_page()
    try:
        yield pg
    finally:
        ctx.close()


def open_(page, url):
    page.goto(url)
    return page


@pytest.mark.parametrize('selector', ['#replies', '#ref', '#help'])
def test_ordinary_page_is_not_a_payment(page, selector):
    open_(page, 'https://article.test/wiki/Kazakhstan')
    d = check(page, selector, 'click', expected_domains={'article.test'})
    assert d.block is False, d


def test_ordinary_page_signals_are_whole_words(page):
    open_(page, 'https://article.test/wiki/Kazakhstan')
    sig = scan_page(page, '#replies')['signals']
    assert sig['expressPay'] is False          # "making payments" is not G Pay
    assert sig['savedCardSelector'] is False   # "extending into" is not "card ending in"
    assert sig['priceShown'] is True and sig['orderTotal'] is True   # the page does show money


@pytest.mark.parametrize('selector,block,price', [
    ('#free', False, '$0'),
    ('#pro', True, '$0.99'),     # the whole amount, not "$0"
    ('#team', True, '$9.99'),
    ('#faq', False, ''),
])
def test_plans(page, selector, block, price):
    open_(page, 'https://shop.test/plans')
    s = scan_page(page, selector)
    assert s['target']['adjacentPrice'] == price
    d = check(page, selector, 'click', expected_domains={'shop.test'})
    assert d.block is block, d


@pytest.mark.parametrize('selector,block', [('#support', True), ('#donate', True)])
def test_donations(page, selector, block):
    open_(page, 'https://donate.test/')
    assert check(page, selector, 'click', expected_domains={'donate.test'}).block is block


def test_checkout(page):
    open_(page, 'https://shop.test/checkout')
    assert check(page, '#cc', 'type', expected_domains={'shop.test'}).code in ('A_CARD', 'A_SURFACE')
    assert check(page, '#pay', 'click', expected_domains={'shop.test'}).block is True
    assert 'js.stripe.com' in scan_page(page, '#pay')['signals']['iframeSrcs']


def test_express_pay_page_refuses_unrelated_click(page):
    open_(page, 'https://shop.test/item')
    assert check(page, '#share', 'click', expected_domains={'shop.test'}).code == 'G_STORED'


def test_target_not_found(page):
    open_(page, 'https://shop.test/plans')
    assert check(page, '#nope', 'click', expected_domains={'shop.test'}).code == 'TARGET_NOT_FOUND'


@pytest.mark.parametrize('selector', ['a"b', 'a\\b', '#x\n#y', '#x</script>'])
def test_odd_selector_never_opens_the_gate(page, selector):
    open_(page, 'https://shop.test/plans')
    d = check(page, selector, 'click', expected_domains={'shop.test'})
    assert d.block is True and d.code in ('TARGET_NOT_FOUND', 'UNRESOLVED'), d


def _watch_clicks(page, selector):
    # A function, not an assignment: Playwright CALLS an expression that yields a
    # function, so "el.onclick = () => ..." would set the flag right away.
    page.evaluate("""(sel) => {
        window.__clicked = false;
        document.querySelector(sel).addEventListener('click', () => { window.__clicked = true; });
    }""", selector)
    assert page.evaluate('window.__clicked') is False


def test_guarded_click_raises_and_does_not_click(page):
    open_(page, 'https://shop.test/plans')
    _watch_clicks(page, '#team')
    with pytest.raises(PaymentBlocked) as e:
        guarded_click(page, '#team', expected_domains={'shop.test'})
    assert e.value.decision.block is True
    assert page.evaluate('window.__clicked === true') is False


def test_guarded_click_passes_ordinary_click(page):
    open_(page, 'https://shop.test/plans')
    _watch_clicks(page, '#faq')
    guarded_click(page, '#faq', expected_domains={'shop.test'})
    assert page.evaluate('window.__clicked === true') is True
