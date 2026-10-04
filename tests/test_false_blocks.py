"""Ordinary actions the original gate refused, and the payment actions next to them that
must stay refused. Each pair sits on one side of a boundary the calibration moved
(docs/CALIBRATION.md): whole words, money near the target, help vs donation, links.
"""
import pytest

from browser_payment_gate import evaluate
from conftest import scan

D = {'example.com'}


# --- whole words: label lists ------------------------------------------------------

@pytest.mark.parametrize('text,block', [
    ('Pay', True),
    ('Pay now', True),
    ('Payments history', False),     # 'pay' inside 'payments'
    ('Repay schedule', False),       # 'pay' inside 'repay'
    ('Buy', True),
    ('Buyer guide', False),          # 'buy' inside 'buyer'
    ('Subscribe', True),
    ('Unsubscribe', False),          # 'subscribe' inside 'unsubscribe'
    ('Deposit', True),
    ('Deposition notes', False),
])
def test_label_is_a_whole_word(text, block, lists):
    s = scan(signals={'priceShown': True}, target={'text': text, 'ancestorText': text})
    assert evaluate(s, 'click', D, False, lists).block is block


# --- whole words: phrases near the target --------------------------------------------

@pytest.mark.parametrize('ancestor,block', [
    ('Pay with Google Pay', True),
    ('Pay with G Pay', True),
    ('We are making payments easier', False),   # 'g pay' across 'makin|g pay|ments'
    ('Visa card ending in 4242', True),
    ('A plateau extending into the steppe', False),
])
def test_phrase_near_target_is_whole_word(ancestor, block, lists):
    s = scan(target={'text': 'Continue', 'ancestorText': ancestor})
    assert evaluate(s, 'click', D, False, lists).block is block


# --- money near the target vs anywhere on the page -----------------------------------

def test_price_far_from_target_does_not_refuse(lists):
    # a page with a GDP figure and the word "Total" in a table; the click is elsewhere
    s = scan(signals={'priceShown': True, 'orderTotal': True},
             target={'text': 'Show previous replies', 'ancestorText': 'Show previous replies'})
    assert evaluate(s, 'click', D, False, lists).code == 'FREE'


@pytest.mark.parametrize('ancestor,price,block', [
    ('Order total $19.00', '$19.00', True),
    ('Subtotal', '', True),
    ('Plan price 0', '', False),        # no currency, no total word
    ('Price: $0', '$0', False),         # free price next to the target
    ('Price: $0.00', '$0.00', False),
    ('Price: $0.01', '$0.01', True),    # the smallest real price
])
def test_money_next_to_target(ancestor, price, block, lists):
    s = scan(target={'text': 'Continue', 'ancestorText': ancestor, 'adjacentPrice': price})
    assert evaluate(s, 'click', D, False, lists).block is block


# --- help 'Support' vs a donation -----------------------------------------------------

@pytest.mark.parametrize('ancestor,block', [
    ('Help centre: Support', False),
    ('Support us with $5', True),
    ('Support the project monthly', True),
    ('Support us on Patreon', True),
    ('Поддержать проект ежемесячно', True),
])
def test_support_needs_money_next_to_it(ancestor, block, lists):
    s = scan(target={'text': 'Support', 'ancestorText': ancestor})
    assert evaluate(s, 'click', D, False, lists).block is block


# --- a plain link is judged by its address -------------------------------------------

@pytest.mark.parametrize('href,block,code', [
    ('https://example.com/wiki/GDP', False, 'LINK'),
    ('https://example.com/checkout?item=1', True, 'E_NAV'),
    ('https://checkout.stripe.com/c/pay/cs_x', True, 'E_NAV'),
])
def test_link_next_to_money_is_judged_by_address(href, block, code, lists):
    s = scan(target={'tag': 'A', 'text': '[12]', 'href': href,
                     'ancestorText': 'GDP $993 billion (total)'})
    d = evaluate(s, 'click', D, False, lists)
    assert (d.block, d.code) == (block, code)


def test_buy_link_is_still_a_purchase(lists):
    s = scan(signals={'priceShown': True},
             target={'tag': 'A', 'text': 'Buy now', 'href': 'https://example.com/item/1',
                     'ancestorText': 'Item $10 Buy now'})
    assert evaluate(s, 'click', D, False, lists).block is True


def test_link_inside_payment_frame_page_is_not_waved_through(lists):
    s = scan(signals={'iframeSrcs': ['js.stripe.com']},
             target={'tag': 'A', 'text': 'Terms', 'href': 'https://example.com/terms',
                     'ancestorText': 'Total $10'})
    assert evaluate(s, 'click', D, False, lists).block is True


# --- the price boundary: the whole amount counts ---------------------------------------

@pytest.mark.parametrize('ancestor,block', [
    ('Free $0', False),
    ('Basic $0.00', False),
    ('Pro $0.01 / month', True),
    ('Pro $0.99 / month', True),
    ('Plan $0,50', True),
    ('Plan EUR 0.99', True),
    ('Plan 0.99 EUR', True),
])
def test_price_read_from_block_text(ancestor, block, lists):
    # no adjacentPrice: the core reads the price from the block text itself
    s = scan(signals={'priceShown': True}, target={'text': 'Choose', 'ancestorText': ancestor})
    assert evaluate(s, 'click', D, False, lists).block is block


@pytest.mark.parametrize('label', ['Subscribe', 'Buy', 'Choose plan'])
def test_paid_label_next_to_sub_dollar_price(label, lists):
    s = scan(signals={'priceShown': True},
             target={'text': label, 'ancestorText': 'Pro $0.99 / month ' + label,
                     'adjacentPrice': '$0.99'})
    assert evaluate(s, 'click', D, False, lists).block is True
