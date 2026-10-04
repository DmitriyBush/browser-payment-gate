"""Decision table of the gate, one row per case.

Most rows are carried over from the self-test of the original gate this library was cut
from (the Serpentis research system's browser guard). Where the library deliberately
decides differently, the row says so and why -- see docs/CALIBRATION.md.
"""
import pytest

from browser_payment_gate import evaluate, nav_precheck
from conftest import scan

D = {'example.com'}

# (name, scan, action, expected_domains, block, allowed codes, prior_mutation)
CASES = [
    # A -- attaching a payment instrument
    ('A1 card-number field', scan(target={'autocomplete': 'cc-number', 'text': ''}), 'type', D, True, {'A_CARD'}, False),
    ('A2 attach label (RU)', scan(target={'text': 'Добавить карту'}), 'click', D, True, {'A_ATTACH'}, False),
    ('A3 IBAN field', scan(target={'name': 'iban', 'text': ''}), 'type', D, True, {'A_BANK'}, False),
    ('A4 clean page', scan(), 'click', D, False, {'FREE'}, False),
    ('A5 card widget elsewhere, unrelated click', scan(fields=[{'autocomplete': 'cc-number'}], target={'text': 'Edit profile'}), 'click', D, False, {'FREE'}, False),
    ('A6 sells + express pay, unrelated click (kept rule F11)', scan(signals={'orderTotal': True, 'expressPay': True}, target={'text': 'Edit'}), 'click', D, True, {'G_STORED'}, False),
    # B -- paid plans, checkout, payment rails
    ('B1 checkout URL', scan(signals={'blockedUrl': True}, target={'text': 'Go'}), 'click', D, True, {'A_SURFACE'}, False),
    ('B2 pay label on a page that sells (RU)', scan(signals={'priceShown': True}, target={'text': 'Оплатить'}), 'click', D, True, {'B_PAID'}, False),
    ('B3 Start Free at $0', scan(signals={'priceShown': True}, target={'text': 'Start Free', 'adjacentPrice': '$0'}), 'click', D, False, {'B_FREE'}, False),
    ('B4 explicit Free plan', scan(signals={'priceShown': True}, target={'text': 'Free', 'adjacentPrice': 'Free'}), 'click', D, False, {'B_FREE'}, False),
    ('B5 Pay in 3', scan(signals={'priceShown': True}, target={'text': 'Pay in 3'}), 'click', D, True, {'B_RAIL'}, False),
    ('B6 Continue to payment', scan(signals={'orderTotal': True, 'priceShown': True}, target={'text': 'Continue to payment'}), 'click', D, True, {'B_PAID'}, False),
    # C -- trials that turn into charges
    ('C1 renews-at terms', scan(target={'text': 'Continue', 'ancestorText': 'Free now, renews at $9/mo'}), 'click', D, True, {'C_TRIAL'}, False),
    ('C2 Start free trial', scan(target={'text': 'Start free trial'}), 'click', D, True, {'C_TRIAL'}, False),
    ('C3 free account, no card', scan(target={'text': 'Create free account'}), 'click', D, False, {'FREE'}, False),
    # D -- billing authorisation, pledges
    ('D1 agree to be billed', scan(target={'text': 'I agree', 'ancestorText': 'I authorize and agree to be billed monthly'}), 'click', D, True, {'D_AUTH'}, False),
    ('D2 usage billing in terms', scan(target={'text': 'Accept', 'ancestorText': 'Terms ... pay as you go ... usage-based billing applies'}), 'click', D, True, {'D_AUTH'}, False),
    ('D3 monthly membership', scan(target={'text': 'Become a member', 'ancestorText': 'Become a member -- $5 per month recurring'}), 'click', D, True, {'D_AUTH'}, False),
    ('D4 plain confirm', scan(target={'text': 'Confirm details', 'ancestorText': 'Confirm your name and email'}), 'click', D, False, {'FREE'}, False),
    # E -- payment frames, unreadable pages
    ('E1 payment iframe', scan(signals={'paymentIframe': True, 'iframeSrcs': ['js.stripe.com']}, target={'text': 'Submit'}), 'click', D, True, {'FLOOR'}, False),
    ('E2 page not scanned', None, 'click', D, True, {'UNRESOLVED'}, False),
    ('E3 target inside a closed shadow root (scanner that can tell)', scan(target={'text': 'Go', 'inClosedShadow': True}), 'click', D, True, {'FLOOR'}, False),
    # G -- stored card, express pay, deposits
    ('G1 Buy now on a page that sells', scan(signals={'orderTotal': True}, target={'text': 'Buy now'}), 'click', D, True, {'G_STORED'}, False),
    ('G2 Apple Pay button', scan(signals={'orderTotal': True, 'expressPay': True}, target={'text': 'Apple Pay'}), 'click', D, True, {'G_STORED'}, False),
    ('G3 Add funds', scan(target={'text': 'Add funds'}), 'click', D, True, {'G_DEPOSIT'}, False),
    ('G4 use balance on a $0 order', scan(signals={'orderTotal': True}, target={'text': 'Use balance', 'adjacentPrice': '$0'}), 'click', D, False, {'G_BALANCE', 'FREE'}, False),
    # input by screen coordinates
    ('OS1 coordinates on a page with money', scan(signals={'priceShown': True}, target={'text': 'X'}), 'os-input', D, True, {'OS_INPUT'}, False),
    ('OS2 coordinates after an earlier action', scan(), 'os-input', D, True, {'OS_INPUT'}, True),
    ('OS3 coordinates on a clean page, first action', scan(), 'os-input', D, False, {'FREE'}, False),
    # navigation that commits
    ('F1a confirm?token landing with a total', scan(url='https://shop.io/confirm?token=abc', domain='shop.io', signals={'orderTotal': True}, target={'text': ''}), 'goto', {'shop.io'}, True, {'E_NAV', 'FLOOR'}, False),
    # The original gate answered E_NAV here; the library answers A_SURFACE first because
    # the URL matches '/pay/'. Same refusal, earlier rule.
    ('F1b processor checkout page', scan(url='https://pay.stripe.com/c/pay/cs_live_abc', domain='pay.stripe.com', target={'text': ''}), 'goto', {'pay.stripe.com'}, True, {'E_NAV', 'A_SURFACE'}, False),
    ('F1c verify-email link', scan(url='https://account.example.org/verify-email?token=abc', domain='account.example.org', target={'text': 'Email verified'}), 'goto', {'account.example.org'}, False, {'FREE'}, False),
    # price shown as an image, checkout layout
    ('F6 price as image + checkout layout', scan(signals={'priceAsImage': True, 'checkoutSummaryLayout': True}, target={'text': 'Go'}), 'click', D, True, {'FLOOR'}, False),
    # carrier billing
    ('F12a phone next to carrier billing (RU)', scan(heading='Получить доступ', target={'autocomplete': 'tel', 'text': '', 'ancestorText': 'Получить доступ к подписке'}), 'type', D, True, {'A_CARRIER'}, False),
    ('F12b phone for a 2FA code', scan(target={'autocomplete': 'tel', 'text': '', 'ancestorText': 'Enter your phone for the 2FA code'}), 'type', D, False, {'FREE'}, False),
    # domain floor: committing only where the human allowed it
    ('DF1 committing on another domain', scan(domain='other.io', target={'text': 'Pay'}, signals={'priceShown': True}), 'click', {'expected.com'}, True, {'DOMAIN_FLOOR'}, False),
    ('DF2 committing, nothing allowed', scan(target={'autocomplete': 'cc-number', 'text': ''}), 'type', set(), True, {'DOMAIN_FLOOR'}, False),
    ('DF3 sign-up submit, no money', scan(target={'text': 'Sign up', 'isFormSubmit': True}), 'click', D, False, {'FREE'}, False),
    ('DF4 reading link, nothing allowed', scan(domain='news.example', target={'text': 'Open article'}), 'click', set(), False, {'FREE'}, False),
    ('OB1 Choose Free on a page that sells', scan(signals={'priceShown': True}, target={'text': 'Choose Free', 'adjacentPrice': 'Free'}), 'click', D, False, {'B_FREE'}, False),
    # Deliberate changes against the original gate (docs/CALIBRATION.md):
    # price text somewhere on the page no longer refuses an unrelated button ...
    ('X1 price on the page, unrelated button', scan(signals={'priceShown': True, 'orderTotal': True}, target={'text': 'Show replies'}), 'click', D, False, {'FREE'}, False),
    # ... express-pay words on a page that sells nothing are not a sale ...
    ('X2 express-pay words, page does not sell', scan(signals={'expressPay': True}, target={'text': 'Read more'}), 'click', D, False, {'FREE'}, False),
    # ... a missing target is reported as such, not as a payment page.
    ('X3 target not found', scan(target={'found': False}), 'click', D, True, {'TARGET_NOT_FOUND'}, False),
]


@pytest.mark.parametrize('name,sc,action,expected,block,codes,prior', CASES, ids=[c[0] for c in CASES])
def test_decision(name, sc, action, expected, block, codes, prior, lists):
    d = evaluate(sc, action, expected, prior, lists)
    assert (d.block, d.code in codes) == (block, True), d


@pytest.mark.parametrize('url,block', [
    ('https://pay.stripe.com/c/pay/cs_live_x', True),
    ('https://checkout.paypal.com/x', True),
    ('https://shop.io/confirm?token=abc', True),
    ('https://shop.io/order?order_id=7', True),
    ('https://account.example.org/verify-email?token=abc', False),
    ('https://example.com/article/123', False),
    ('https://news.example/subscribe', False),          # a subscribe page, no token: reading it is free
    ('https://notpaypal.com/x', False),                  # look-alike suffix is not paypal.com
    ('', False),
])
def test_nav_precheck(url, block, lists):
    assert nav_precheck(url, lists).block is block


def test_known_limit_form_submit_with_price_outside_form(lists):
    """Declared limit (docs/CALIBRATION.md): a form submit whose block shows no price, on
    a page with a price elsewhere and no card field, payment frame, checkout address or
    payment label, is allowed. Typing a card number into such a form is still refused."""
    s = scan(signals={'priceShown': True}, target={'text': 'Send', 'isFormSubmit': True})
    assert evaluate(s, 'click', D, False, lists).block is False
    card = scan(signals={'priceShown': True}, target={'autocomplete': 'cc-number', 'text': ''})
    assert evaluate(card, 'type', D, False, lists).code == 'A_CARD'
