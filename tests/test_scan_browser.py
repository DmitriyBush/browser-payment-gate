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
            return route.fulfill(status=200, body='', content_type='text/html; charset=utf-8')
        return route.fulfill(status=200, body=body, content_type='text/html; charset=utf-8')

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


TRICKY = """<html><head><title>Cart</title></head><body>
<h1>Cart</h1>
<div><span>$19.99/month</span><div role="button" id="divbtn">Continue</div></div>
<form><p>Order total $49.00</p><div class="actions"><button id="confirm" type="submit">Go</button></div></form>
<div><p>Order total $49.00</p><a id="hash" href="#">Proceed</a></div>
<div><p>GDP $993 billion</p><a id="note" href="#cite-12">[12]</a><a id="self" href="/cart">Proceed</a></div>
<div><p>Итого 1 990 \u20bd</p><button id="rub">Продолжить</button></div>
<form><input id="cardf" autocomplete="cc-number"><button id="send" type="submit">Send</button></form>
<button id="faq2">Read FAQ</button>
<div id="host"></div>
<script>
  const root = document.getElementById('host').attachShadow({mode: 'open'});
  root.innerHTML = '<div><span>$9.99</span><button class="act">Buy now</button></div>';
  window.__shadowClicked = false;
  root.querySelector('.act').addEventListener('click', () => { window.__shadowClicked = true; });
</script>
</body></html>"""
PAGES['https://shop.test/cart'] = TRICKY


@pytest.mark.parametrize('selector,block', [
    ('#divbtn', True),    # the price next to a div-button counts (block = parent, not itself)
    ('#confirm', True),   # the enclosing form wins over the nearest wrapper div
    ('#hash', True),      # href="#" is not navigation
    ('#note', False),     # an in-page anchor is navigation: a footnote next to money
    ('#self', True),      # a link to the current page itself is a script button
    ('#rub', True),       # "1 990 \u20bd" is a price
    ('#send', True),      # submit of a form that holds a card field
    ('#faq2', False),
])
def test_tricky_cart(page, selector, block):
    open_(page, 'https://shop.test/cart')
    d = check(page, selector, 'click', expected_domains={'shop.test'})
    assert d.block is block, d


def test_scan_js_price_matches_python_price(page):
    open_(page, 'https://shop.test/cart')
    assert scan_page(page, '#rub')['target']['adjacentPrice'] == '1 990 \u20bd'
    assert scan_page(page, '#hash')['target']['href'] == ''


def test_shadow_dom_button_is_judged_and_not_clicked(page):
    open_(page, 'https://shop.test/cart')
    # Playwright's engine enters the open shadow root; the scan must see THAT element
    s = scan_page(page, '#host .act')
    assert s['target']['found'] is True and s['target']['text'] == 'Buy now'
    with pytest.raises(PaymentBlocked):
        guarded_click(page, '#host .act', expected_domains={'shop.test'})
    assert page.evaluate('window.__shadowClicked') is False


def test_generic_expression_path(page):
    from browser_payment_gate import scan_expression, parse_scan, evaluate
    open_(page, 'https://shop.test/plans')
    s = parse_scan(page.evaluate(scan_expression('#pro')))
    assert s['target']['text'] == 'Subscribe'
    assert evaluate(s, 'click', {'shop.test'}).block is True
    s2 = parse_scan(page.evaluate(scan_expression('#nope')))
    assert evaluate(s2, 'click', {'shop.test'}).code == 'TARGET_NOT_FOUND'


def test_async_page_in_sync_call_says_why():
    class FakeLoc:
        first = None
        def count(self):
            async def c():
                return 1
            return c()
    class FakePage:
        def locator(self, sel):
            l = FakeLoc(); l.first = l; return l
    d = check(FakePage(), '#x')
    assert d.code == 'UNRESOLVED' and 'async' in d.reason


BIGFORM = ("<html><head><title>Survey</title></head><body><h1>Survey</h1><form>"
           + "".join('<input name="q%d">' % i for i in range(300))
           + '<input id="cc" autocomplete="cc-number" name="cardnumber">'
           + '<button id="send" type="submit">Send</button></form></body></html>')
SMALLFORM = ('<html><head><title>Survey</title></head><body><h1>Survey</h1><form>'
             '<input name="q1"><button id="send" type="submit">Send</button></form></body></html>')
PAGES['https://shop.test/bigform'] = BIGFORM
PAGES['https://shop.test/smallform'] = SMALLFORM


def test_form_cut_at_field_cap_is_flagged_and_refused(page):
    # 301 inputs, the card field is the 301st -- past the 300-field cut
    open_(page, 'https://shop.test/bigform')
    s = scan_page(page, '#send')
    assert s['target']['formFieldsTruncated'] is True
    assert check(page, '#send', 'click', expected_domains={'shop.test'}).block is True


def test_small_form_not_flagged(page):
    open_(page, 'https://shop.test/smallform')
    assert scan_page(page, '#send')['target']['formFieldsTruncated'] is False
    assert check(page, '#send', 'click', expected_domains={'shop.test'}).block is False


def _form_page(n_data, card_last, extra_buttons=0):
    return ("<html><head><title>Survey</title></head><body><h1>Survey</h1><form>"
            + "".join('<input name="q%d">' % i for i in range(n_data - (1 if card_last else 0)))
            + ('<input id="cc" autocomplete="cc-number" name="cardnumber">' if card_last else '')
            + "".join('<button type="button">x</button>' for _ in range(extra_buttons))
            + '<button id="send" type="submit">Send</button></form></body></html>')


PAGES['https://shop.test/f300card'] = _form_page(300, True)
PAGES['https://shop.test/f301'] = _form_page(301, False)
PAGES['https://shop.test/f300'] = _form_page(300, False)
PAGES['https://shop.test/f100btn'] = _form_page(100, False, extra_buttons=250)
PAGES['https://shop.test/imgsubmit'] = ('<html><body><form><input autocomplete="cc-number" name="c">'
                                        '<input id="go" type="image" src="x.png" alt="Go"></form></body></html>')


def test_boundary_exactly_300_data_fields_card_last_is_seen(page):
    open_(page, 'https://shop.test/f300card')
    s = scan_page(page, '#send')
    assert s['target']['formFieldsTruncated'] is False and len(s['target']['formFields']) == 300
    assert check(page, '#send', 'click', expected_domains={'shop.test'}).code == 'A_FORM'


def test_boundary_300_data_fields_not_cut_301_cut(page):
    open_(page, 'https://shop.test/f300')
    assert scan_page(page, '#send')['target']['formFieldsTruncated'] is False
    assert check(page, '#send', 'click', expected_domains={'shop.test'}).block is False
    open_(page, 'https://shop.test/f301')
    assert scan_page(page, '#send')['target']['formFieldsTruncated'] is True
    assert check(page, '#send', 'click', expected_domains={'shop.test'}).block is True


def test_buttons_do_not_count_toward_the_cut(page):
    # 100 inputs + 250 buttons = 351 elements, but only 100 data fields: not cut, allowed
    open_(page, 'https://shop.test/f100btn')
    assert scan_page(page, '#send')['target']['formFieldsTruncated'] is False
    assert check(page, '#send', 'click', expected_domains={'shop.test'}).block is False


def test_image_input_submits_the_form(page):
    open_(page, 'https://shop.test/imgsubmit')
    s = scan_page(page, '#go')
    assert s['target']['isFormSubmit'] is True
    assert check(page, '#go', 'click', expected_domains={'shop.test'}).block is True
