"""Inputs found by review where the gate used to ALLOW a payment or open on odd input.
Each one must now refuse (or, where marked, stay allowed for the right reason)."""
import json

import pytest

from browser_payment_gate import Lists, evaluate, load_lists, nav_precheck, parse_scan
from browser_payment_gate.core import DEFAULT_LISTS_PATH
from conftest import scan

D = {'example.com'}


@pytest.fixture
def broken(tmp_path):
    return load_lists(str(tmp_path / 'nope.json'))


# --- a broken lists file never makes the gate looser ----------------------------------

@pytest.mark.parametrize('sc,action', [
    (scan(target={'autocomplete': 'cc-number', 'text': ''}), 'type'),
    (scan(target={'name': 'iban', 'text': ''}), 'type'),
    (scan(heading='Add payment method', target={'text': 'Save'}), 'click'),
    (scan(url='https://site.example/billing', target={'text': 'Save'}), 'click'),
    (scan(signals={'iframeSrcs': ['js.stripe.com']}, target={'text': 'Submit'}), 'click'),
    (scan(target={'text': 'Continue', 'ancestorText': 'Free now, renews at $9/mo'}), 'click'),
    (scan(target={'text': 'Add card'}), 'click'),
])
def test_broken_lists_keep_code_rules(sc, action, broken):
    for expected in (D, set()):
        d = evaluate(sc, action, expected, False, broken)
        assert d.block is True, (expected, d)


def test_broken_lists_nav_to_processor(broken):
    assert nav_precheck('https://checkout.stripe.com/c/pay/cs_live_x', broken).block is True


@pytest.mark.parametrize('entry', [[' '], [''], [123], [None]])
def test_lists_entries_must_be_text(entry):
    with open(DEFAULT_LISTS_PATH, encoding='utf-8') as f:
        data = json.load(f)
    data['paid_action_labels'] = entry
    ls = Lists(data, 'x')
    assert not ls.ok and 'paid_action_labels' in ls.error


# --- a scan of an unexpected shape is refused, never read as "no signal" ----------------

@pytest.mark.parametrize('sc', [
    {},
    {'url': 'https://example.com', 'signals': {'priceShown': True}},
    scan(target=None),
    scan(target=[]),
    scan(target='x'),
    scan(target={'found': 'false', 'text': 'Read'}),
    scan(signals='x'),
    scan(signals=[]),
    scan(signals={'iframeSrcs': 'js.stripe.com'}),
    scan(signals={'priceShown': 'yes'}),
    scan(signals={'scanError': True}),
    scan(target={'text': 5}),
    scan(target={'text': ['Pay']}),
    scan(target={'ancestorText': []}),
    scan(target={'adjacentPrice': 1}),
    scan(target={'href': 1}),
    scan(target={'formFields': 'x'}),
    scan(url=1),
    scan(domain=1),
    scan(heading=1),
    scan(fields=[None]),
    scan(fields='x'),
])
def test_malformed_scan_is_refused(sc):
    d = evaluate(sc, 'click', D, False, load_lists())
    assert (d.block, d.code) == (True, 'UNRESOLVED'), d


def test_parse_scan_of_empty_object_is_refused():
    assert evaluate(parse_scan('{}'), 'click', set()).code == 'UNRESOLVED'


@pytest.mark.parametrize('action', ['os_input', 'fill', 'CLICK', '', None])
def test_unknown_action_is_refused(action):
    assert evaluate(scan(), action, D).code == 'UNRESOLVED'


def test_gate_never_raises_on_a_bad_lists_object():
    assert evaluate(scan(), 'click', D, False, lists='not lists').block is False   # falls back to defaults


# --- "free" only when every price next to the control is free ----------------------------

@pytest.mark.parametrize('text,ancestor', [
    ('Go ad-free - Subscribe', '$4.99/month Go ad-free - Subscribe'),
    ('Subscribe', '$0 setup - $29/month Subscribe'),
    ('Upgrade', 'Free $0 Pro $9.99/mo Upgrade'),
    ('Free trial', '$9.99/month after 7 days Free trial'),
    ('Subscribe - free shipping', 'Pro $9.99 / month'),
    ('Continue', 'Free $0 Pro $9.99 Continue'),
])
def test_one_real_price_beats_free(text, ancestor):
    s = scan(signals={'priceShown': True}, target={'text': text, 'ancestorText': ancestor})
    for expected in (D, set()):
        assert evaluate(s, 'click', expected).block is True


def test_free_plan_still_free():
    s = scan(signals={'priceShown': True}, target={'text': 'Choose Free', 'ancestorText': 'Free $0 Choose Free'})
    assert evaluate(s, 'click', set()).code == 'B_FREE'


def test_free_returns_on_express_page_is_not_free():
    s = scan(signals={'priceShown': True, 'expressPay': True},
             target={'text': 'Free returns', 'ancestorText': 'Free returns'})
    assert evaluate(s, 'click', D).block is True


# --- price formats ---------------------------------------------------------------------

@pytest.mark.parametrize('ancestor', [
    '1 990 ₽', '299 ₽', '990 руб.', '19 €', '9 €', 'USD 9.99', '10 USD', 'EUR 5',
    '5000 ₸', '5 000 тг', '$1,299.00',
])
def test_price_formats(ancestor):
    s = scan(target={'text': 'Продолжить', 'ancestorText': ancestor + ' Продолжить'})
    assert evaluate(s, 'click', D).code == 'FLOOR'


@pytest.mark.parametrize('ancestor', ['0 ₽', '€0', '0.00 EUR', '$0', 'USD 0'])
def test_zero_prices_are_free(ancestor):
    s = scan(signals={'priceShown': True}, target={'text': 'Choose', 'ancestorText': 'Basic ' + ancestor})
    assert evaluate(s, 'click', D).block is False


@pytest.mark.parametrize('ancestor', ['Python 3.12 released', 'Room 101, floor 2', 'rubric 5'])
def test_not_prices(ancestor):
    s = scan(target={'text': 'Next', 'ancestorText': ancestor})
    assert evaluate(s, 'click', D).code == 'FREE'


# --- payment phrases that whole-word matching would otherwise miss -------------------------

@pytest.mark.parametrize('text', ['Submit payment', 'Make a payment', 'Confirm payment',
                                  'Complete payment', 'Confirm order', 'Подтвердить заказ'])
def test_payment_phrases(text):
    s = scan(signals={'priceShown': True}, target={'text': text})
    assert evaluate(s, 'click', D).code == 'B_PAID'
    assert evaluate(scan(target={'text': text}), 'click', set()).code == 'DOMAIN_FLOOR'


# --- a form submit with a card field in the same form --------------------------------------

def test_submit_of_form_with_card_field():
    s = scan(target={'text': 'Send', 'isFormSubmit': True,
                     'formFields': [{'autocomplete': 'cc-number', 'name': '', 'id': '', 'tag': 'INPUT'}]})
    assert evaluate(s, 'click', D).code == 'A_FORM'


def test_submit_without_form_fields_key_falls_back_to_page_fields():
    # a scan with no target.formFields (older or foreign scanner) cannot say which form is
    # submitted: a card field on the page counts as held by it
    s = scan(fields=[{'autocomplete': 'cc-number', 'name': '', 'id': '', 'tag': 'INPUT'}],
             target={'text': 'Send', 'isFormSubmit': True})
    assert 'formFields' not in s['target']
    assert evaluate(s, 'click', D).code == 'A_FORM'


def test_submit_with_empty_form_fields_is_not_the_card_form():
    # formFields present and empty: the scanner resolved the form and it holds no card field
    s = scan(fields=[{'autocomplete': 'cc-number', 'name': '', 'id': '', 'tag': 'INPUT'}],
             target={'text': 'Send', 'isFormSubmit': True, 'formFields': []})
    assert evaluate(s, 'click', D).block is False


def test_submit_without_form_fields_key_bank_field_on_page():
    s = scan(fields=[{'autocomplete': '', 'name': 'iban', 'id': '', 'tag': 'INPUT'}],
             target={'text': 'Send', 'isFormSubmit': True})
    assert evaluate(s, 'click', D).block is True


def test_submit_with_form_fields_none_is_refused_as_malformed():
    s = scan(fields=[{'autocomplete': 'cc-number', 'name': '', 'id': '', 'tag': 'INPUT'}],
             target={'text': 'Send', 'isFormSubmit': True, 'formFields': None})
    d = evaluate(s, 'click', D)
    assert d.block is True and d.code == 'UNRESOLVED'


def test_submit_without_form_fields_key_page_list_cut_is_refused():
    # 300 ordinary fields seen, the list was cut: a card field may sit after the cut
    s = scan(fields=[{'autocomplete': 'email', 'name': 'f%d' % i, 'id': '', 'tag': 'INPUT'} for i in range(300)],
             target={'text': 'Send', 'isFormSubmit': True}, signals={'fieldsTruncated': True})
    d = evaluate(s, 'click', D)
    assert d.block is True and d.code == 'A_FORM'


def test_submit_without_form_fields_key_no_payment_field_is_allowed():
    # the fallback's false-block boundary: no card or bank field on the page -> an ordinary submit goes
    s = scan(fields=[{'autocomplete': 'email', 'name': 'email', 'id': '', 'tag': 'INPUT'}],
             target={'text': 'Subscribe', 'isFormSubmit': True})
    assert evaluate(s, 'click', D).block is False


def test_submit_of_other_form_on_page_with_card_widget():
    # the card field is in another form: allowed on an allowed domain, refused elsewhere
    s = scan(fields=[{'autocomplete': 'cc-number'}],
             target={'text': 'Search', 'isFormSubmit': True, 'formFields': []})
    assert evaluate(s, 'click', D).block is False
    assert evaluate(s, 'click', set()).code == 'DOMAIN_FLOOR'


def test_fields_list_cut_short_counts_as_instrument():
    s = scan(signals={'fieldsTruncated': True}, target={'text': 'Send', 'isFormSubmit': True})
    assert evaluate(s, 'click', set()).code == 'DOMAIN_FLOOR'


def test_iframes_cut_short_count_as_payment_frame():
    s = scan(signals={'iframesTruncated': True}, target={'text': 'Next'})
    assert evaluate(s, 'click', D).code == 'FLOOR'


# --- the verify exception looks at the path only ------------------------------------------

@pytest.mark.parametrize('url,block', [
    ('https://account.example.org/verify-email?token=abc', False),
    ('https://shop.example/checkout?session_id=abc&next=/verify', True),
    ('https://shop.example/confirm?order_id=7&ref=verify', True),
    ('https://verify.shop.example/order?id=7', True),
])
def test_verify_exception_path_only(url, block):
    assert nav_precheck(url).block is block
