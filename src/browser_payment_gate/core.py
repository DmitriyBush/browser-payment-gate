"""Decision core of browser-payment-gate.

Question it answers: an AI agent is about to click, type or navigate in a web page --
could this action spend money or attach a payment instrument? If yes, or if the page
cannot be read, the action is refused and handed to the human.

The core is pure: it takes the page scan produced by scan.js (see scanner.py) and the
action, and returns a Decision. It does not drive a browser and does not import one.
It never raises on its input: a scan it cannot read is refused as UNRESOLVED.

Ancestry: this is the decision layer of the payment gate that has guarded the Serpentis
research system's own browser since June 2026, recalibrated before release -- what was
changed and how it was measured: docs/CALIBRATION.md.

Threat model: GOOD-FAITH guard. It keeps a well-meaning agent from paying by accident;
it does not stop a hostile page that disguises its controls, nor an agent that wants to
pay and drives the browser around it.
"""
import json
import os
import re
from collections import namedtuple

Decision = namedtuple('Decision', ['block', 'code', 'reason'])

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LISTS_PATH = os.path.join(_HERE, 'lists.json')
LISTS_ENV = 'BROWSER_PAYMENT_GATE_LISTS'

ACTIONS = ('click', 'type', 'goto', 'os-input')

REQUIRED_LISTS = (
    'paid_action_labels', 'rail_labels', 'trial_cta_labels', 'pledge_labels',
    'pledge_weak_labels', 'stored_pay_labels', 'express_pay_labels', 'deposit_labels',
    'carrier_billing_labels', 'attach_labels', 'weak_commit_labels',
    'processor_domains', 'payment_iframe_domains', 'blocked_url_patterns',
)


class Lists(object):
    """The editable part of the gate. ok is False when the file could not be read, a
    required list is missing or empty, or holds an entry that is not a non-blank string
    -- the gate then runs on its built-in minimum and refuses on any money signal; it
    never opens."""

    def __init__(self, data, source, error=''):
        self.data = data if isinstance(data, dict) else {}
        self.source = source
        self.error = error
        missing, bad = [], []
        for n in REQUIRED_LISTS:
            v = self.data.get(n)
            if not (isinstance(v, list) and v):
                missing.append(n)
            elif not all(isinstance(x, str) and x.strip() for x in v):
                bad.append(n)
        self.ok = not error and not missing and not bad
        if not error and (missing or bad):
            parts = []
            if missing:
                parts.append('missing or empty lists: %s' % ', '.join(missing))
            if bad:
                parts.append('entries that are not non-blank strings in: %s' % ', '.join(bad))
            self.error = '; '.join(parts)
        self._rx = {}

    def get(self, name):
        v = self.data.get(name)
        return [x for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []

    def label_rx(self, name):
        """One compiled whole-word pattern per list (cached)."""
        rx = self._rx.get(name)
        if rx is None:
            labels = sorted((x.lower() for x in self.get(name)), key=len, reverse=True)
            if labels:
                rx = re.compile(r'(?<!\w)(' + '|'.join(re.escape(l) for l in labels) + r')(?!\w)', re.I)
            else:
                rx = re.compile(r'(?!x)x')  # matches nothing
            self._rx[name] = rx
        return rx


def load_lists(path=None):
    """Load lists from path, else from $BROWSER_PAYMENT_GATE_LISTS, else the defaults.
    Never raises: a broken file gives Lists(ok=False)."""
    src = path or os.environ.get(LISTS_ENV) or DEFAULT_LISTS_PATH
    try:
        with open(src, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return Lists({}, src, 'lists file is not a JSON object')
        return Lists(data, src)
    except Exception as e:  # noqa: BLE001 -- any failure means: not readable
        return Lists({}, src, 'cannot read lists file: %s' % e)


_DEFAULT = None


def default_lists():
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_lists()
    return _DEFAULT


# Used when the lists are unusable: a small built-in minimum, so that a broken file
# can never make the gate blind to the most common payment controls and providers.
FLOOR_LISTS = Lists({
    'paid_action_labels': ['subscribe', 'upgrade', 'buy', 'pay', 'checkout', 'place order',
                           'submit payment', 'make a payment', 'confirm payment',
                           'confirm order', 'complete order',
                           'оплатить', 'подписаться', 'купить', 'подтвердить заказ'],
    'rail_labels': ['pay later', 'direct debit', 'pay by invoice'],
    'trial_cta_labels': ['start free trial', 'start trial', 'free trial', 'try free'],
    'pledge_labels': ['donate', 'pledge', 'become a member', 'пожертвовать'],
    'pledge_weak_labels': ['support', 'поддержать'],
    'stored_pay_labels': ['buy now', '1-click', 'pay now', 'order now', 'complete purchase'],
    'express_pay_labels': ['apple pay', 'google pay', 'g pay'],
    'deposit_labels': ['add funds', 'top up', 'deposit', 'пополнить'],
    'carrier_billing_labels': ['subscribe to continue', 'get access', 'подписаться'],
    'attach_labels': ['add card', 'add payment method', 'connect wallet', 'добавить карту'],
    'weak_commit_labels': ['continue', 'next', 'продолжить', 'далее'],
    'processor_domains': ['stripe.com', 'paypal.com', 'braintreegateway.com', 'adyen.com',
                          'checkout.com', 'pay.google.com', 'payments.google.com'],
    'payment_iframe_domains': ['stripe.com', 'paypal.com', 'braintreegateway.com',
                               'adyen.com', 'checkout.com', 'pay.google.com'],
    'blocked_url_patterns': ['/checkout', '/payment', '/billing', '/pay/', '/purchase',
                             '/subscribe', 'checkout.stripe.com', 'pay.google.com'],
}, '<built-in minimum>')


# ---------------------------------------------------------------------------
# Fixed patterns (code, not configuration: changing them changes what the gate means)
# ---------------------------------------------------------------------------

CARD_AUTOCOMPLETE = {'cc-number', 'cc-exp', 'cc-csc', 'cc-name', 'cc-exp-month', 'cc-exp-year'}
CARD_FIELD_RE = re.compile(r'card ?number|cardnum|cc-?num|\bcvv\b|\bcvc\b|expiry|card-?exp', re.I)
BANK_RAIL_RE = re.compile(r'\biban\b|account ?number|\brouting\b|sort ?code|\bbic\b|\bswift\b|\bupi\b', re.I)
CARRIER_FIELD_RE = re.compile(r'msisdn|mobile ?number|\bphone\b|\btel\b', re.I)

BILLING_AUTH_TERMS_RE = re.compile(
    r'\bauthori[sz]e\b|agree to be billed|pay as you go|\bpostpaid\b|usage[- ]based|'
    r'оплата по факту|списыв|\binvoice\b|in 3 (interest-free|payments)|в рассрочку', re.I)
TRIAL_TERMS_RE = re.compile(
    r'auto-?renew|card required|after (the )?trial|renews at|'
    r"we('| wi)ll charge|then \$?[0-9]|после .{0,12}пробн|по окончании", re.I)
RECURRING_TERMS_RE = re.compile(
    r'\bmonthly\b|\brecurring\b|per month|auto-?renew|в месяц|ежемесячно|\bsubscription\b|подписк', re.I)
DCB_TERMS_RE = re.compile(
    r'carrier billing|premium ?sms|wap-?billing|\bdcb\b|'
    r'мобильный платеж|оплата с телефона|спишут с телефона|с баланса телефона', re.I)
COMMIT_SIGNATURE_RE = re.compile(
    r'/(confirm|activate|subscribe|order|place-?order|checkout|pay|purchase)\b', re.I)
TOKEN_PARAM_RE = re.compile(r'[?&](token|order|order_id|oid|id|cs|session_id|sessionid|sid)=', re.I)
VERIFY_PATH_RE = re.compile(r'verify|activate-?account|verify-?email|confirm-?email', re.I)
# "free" as its own word -- not the tail of "ad-free" / "risk-free".
FREE_INDICATOR_RE = re.compile(r'(?<![\w-])free\b|бесплатн', re.I)

# Prices. The WHOLE amount is captured ("$0.99" is not "$0"); thousands may be grouped by
# spaces ("1 990 ₽"); the currency may stand before or after the number.
_AMOUNT = r'\d+(?:[   ]\d{3})*(?:[.,]\d+)*'
_CUR_BEFORE = r'(?:\$|€|£|₽|₸|\b(?:USD|EUR|GBP|RUB|KZT|UAH|CHF)\b)'
_CUR_AFTER = r'(?:\$|€|£|₽|₸|(?:USD|EUR|GBP|RUB|KZT|UAH|CHF|руб|тг)(?![a-zа-яё]))'
PRICE_RE = re.compile(_CUR_BEFORE + r'\s?' + _AMOUNT + '|' + _AMOUNT + r'\s?' + _CUR_AFTER, re.I)
_ZERO = r'0+(?:[.,]0+)?'
FREE_PRICE_RE = re.compile(
    r'^\s*(?:free|бесплатно|' + _CUR_BEFORE + r'?\s?' + _ZERO + r'\s?(?:' + _CUR_AFTER + r'|руб\.)?)\s*$', re.I)
TOTAL_RE = re.compile(r'\b(total|order summary|amount due|subtotal)\b|итого|к оплате', re.I)


# ---------------------------------------------------------------------------
# Reading the scan
# ---------------------------------------------------------------------------

_TARGET_STR = ('tag', 'type', 'text', 'aria', 'autocomplete', 'name', 'id', 'href',
               'ancestorText', 'adjacentPrice')
_TARGET_BOOL = ('isFormSubmit', 'inClosedShadow', 'formFieldsTruncated')
_SCAN_STR = ('url', 'domain', 'title', 'heading')


def _malformed(scan, action):
    """Why this scan cannot be judged, or '' if it can. Any shape the gate does not
    expect is refused, never coerced into 'no signal'."""
    if not isinstance(scan, dict):
        return 'scan is not an object'
    for k in _SCAN_STR:
        if scan.get(k) is not None and not isinstance(scan.get(k), str):
            return '%s is not text' % k
    sig = scan.get('signals', {})
    if not isinstance(sig, dict):
        return 'signals is not an object'
    for k, v in sig.items():
        if k == 'iframeSrcs':
            if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
                return 'signals.iframeSrcs is not a list of text'
        elif v is not None and not isinstance(v, bool):
            return 'signals.%s is not true/false' % k
    if sig.get('scanError'):
        return 'the page scan reported an error'
    fields = scan.get('fields', [])
    if not (isinstance(fields, list) and all(isinstance(f, dict) for f in fields)):
        return 'fields is not a list of objects'
    for f in fields:
        if any(v is not None and not isinstance(v, str) for v in f.values()):
            return 'a field has a value that is not text'
    if action == 'goto':
        return ''
    t = scan.get('target')
    if not isinstance(t, dict):
        return 'target is missing or not an object'
    if t.get('found') is False:
        return ''
    if t.get('found') is not True:
        return 'target.found is not true/false'
    for k in _TARGET_STR:
        if t.get(k) is not None and not isinstance(t.get(k), str):
            return 'target.%s is not text' % k
    for k in _TARGET_BOOL:
        if t.get(k) is not None and not isinstance(t.get(k), bool):
            return 'target.%s is not true/false' % k
    ff = t.get('formFields', [])
    if not (isinstance(ff, list) and all(isinstance(f, dict) for f in ff)):
        return 'target.formFields is not a list of objects'
    if any(v is not None and not isinstance(v, str) for f in ff for v in f.values()):
        return 'a form field has a value that is not text'
    return ''


def _target_text(t):
    return ((t.get('text') or '') + ' ' + (t.get('aria') or '')).lower()


def _label_in(t, lists, name):
    """The first label of list `name` found in the target text/aria as a whole word."""
    blob = _target_text(t)
    if not blob.strip():
        return ''
    m = lists.label_rx(name).search(blob)
    return m.group(1).lower() if m else ''


def _is_card_field(t):
    if (t.get('autocomplete') or '').lower() in CARD_AUTOCOMPLETE:
        return True
    probe = (t.get('name') or '') + ' ' + (t.get('id') or '') + ' ' + (t.get('aria') or '')
    return bool(CARD_FIELD_RE.search(probe))


def _is_bank_field(t):
    probe = ((t.get('name') or '') + ' ' + (t.get('id') or '') + ' '
             + (t.get('aria') or '') + ' ' + (t.get('text') or ''))
    return bool(BANK_RAIL_RE.search(probe))


def _is_carrier_field(scan, t, lists):
    """A phone field is an instrument ONLY next to a carrier-billing commit or DCB terms;
    a bare phone (signup, 2FA) is not."""
    ac = (t.get('autocomplete') or '').lower()
    probe = (t.get('name') or '') + ' ' + (t.get('id') or '')
    if not (ac == 'tel' or CARRIER_FIELD_RE.search(probe)):
        return False
    ancestor = t.get('ancestorText') or ''
    if DCB_TERMS_RE.search(ancestor):
        return True
    ctx = {'text': ancestor + ' ' + (scan.get('heading') or '')}
    return bool(_label_in(ctx, lists, 'carrier_billing_labels'))


def _is_instrument_field(scan, t, lists):
    return _is_card_field(t) or _is_bank_field(t) or _is_carrier_field(scan, t, lists)


def _block_prices(t):
    """Every price in the target's block: the scanner's adjacentPrice plus every price
    in the block text."""
    out = [m.group(0) for m in PRICE_RE.finditer(t.get('ancestorText') or '')]
    adj = (t.get('adjacentPrice') or '').strip()
    if adj:
        out.append(adj)
    return out


def _adjacent_is_free(t):
    """Free only if every price in the block is free; with no price at all, a 'free'
    word on the control itself. One real price anywhere in the block wins."""
    prices = _block_prices(t)
    if prices:
        return all(FREE_PRICE_RE.match(p) for p in prices)
    return bool(FREE_INDICATOR_RE.search(t.get('text') or ''))


def _local_money(t):
    """A non-free price, or total text, in the target's own block (form/section/div)."""
    if any(not FREE_PRICE_RE.match(p) for p in _block_prices(t)):
        return True
    return bool(TOTAL_RE.search(t.get('ancestorText') or ''))


def _domain_in(values, domain_list):
    for v in values:
        host = (v or '').lower()
        for d in domain_list:
            d = d.lower()
            # 'd in host' on purpose: a look-alike frame host such as paypal.com.example
            # is treated as the processor (refuse), never as a stranger (allow).
            if host == d or host.endswith('.' + d) or d in host:
                return True
    return False


def host_matches(domain, domain_list):
    h = (domain or '').lower()
    if h.startswith('www.'):
        h = h[4:]
    return any(h == d.lower() or h.endswith('.' + d.lower()) for d in domain_list)


def _url_pattern_rx(p):
    """A pattern starting with '/' is a path part and must not run on into a longer word:
    '/payment' matches '/payment', '/payment/', '/payment?x', '/payment-step', but not
    '/payments' (a docs section) -- a hyphen continues the match, a letter or digit does
    not. Other patterns (host parts such as 'checkout.stripe.com') match anywhere."""
    p = p.lower()
    if p.startswith('/') and not p.endswith('/'):
        return re.compile(re.escape(p) + r'(?![a-z0-9])')
    return re.compile(re.escape(p))


def blocked_url(url, lists):
    u = (url or '').lower()
    return any(_url_pattern_rx(p).search(u) for p in lists.get('blocked_url_patterns'))


def _payment_frame(scan, lists):
    sig = scan.get('signals') or {}
    return bool(sig.get('paymentIframe') or sig.get('iframesTruncated')
                or _domain_in(sig.get('iframeSrcs') or [], lists.get('payment_iframe_domains')))


def surface_signals(scan, lists):
    """Floor signals. Returns (suspect, detail).
    s1 money text NEAR the target; s2 payment iframe on the page (or iframes the scan
    could not list in full); s3 checkout URL; s4 checkout layout / express or saved-card
    text near the target; s5 target inside a closed shadow root (unreadable)."""
    sig = scan.get('signals') or {}
    t = scan.get('target') or {}
    anc = t.get('ancestorText') or ''
    s1 = _local_money(t)
    s2 = _payment_frame(scan, lists)
    s3 = bool(sig.get('blockedUrl') or blocked_url(scan.get('url'), lists))
    s4 = bool(sig.get('checkoutSummaryLayout')
              or _label_in({'text': anc}, lists, 'express_pay_labels')
              or re.search(r'\b(card )?ending in\b\s*\d|(\*{2,}|•{2,})\s?\d{4}\b', anc, re.I))
    s5 = bool(t.get('inClosedShadow'))
    detail = {'s1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5}
    return any(detail.values()), detail


def commerce_page(scan, lists):
    """The page sells something somewhere: used ONLY to arm the label rules (a control
    that itself reads as pay/buy/subscribe), never to refuse an arbitrary click."""
    sig = scan.get('signals') or {}
    return bool(sig.get('orderTotal') or sig.get('priceShown') or sig.get('priceAsImage')
                or sig.get('checkoutSummaryLayout') or _payment_frame(scan, lists)
                or sig.get('blockedUrl') or blocked_url(scan.get('url'), lists))


def _is_free_select(scan, t, lists):
    if not commerce_page(scan, lists):
        return False
    if _is_card_field(t) or _is_bank_field(t):
        return False
    if _payment_frame(scan, lists):
        return False
    if not _adjacent_is_free(t):
        return False
    if _label_in(t, lists, 'trial_cta_labels') or TRIAL_TERMS_RE.search(t.get('ancestorText') or ''):
        return False
    if (_label_in(t, lists, 'rail_labels') or _label_in(t, lists, 'express_pay_labels')
            or _label_in(t, lists, 'stored_pay_labels')):
        return False
    return True


def _weak_pledge(t, lists):
    """'support' is a pledge only with money/recurring/donation terms next to it."""
    if not _label_in(t, lists, 'pledge_weak_labels'):
        return False
    anc = t.get('ancestorText') or ''
    return bool(_local_money(t) or RECURRING_TERMS_RE.search(anc)
                or re.search(r'\bdonat|пожертв|patreon|boosty', anc, re.I))


def nav_as_commit(scan, lists):
    url = scan.get('url') or ''
    sig = scan.get('signals') or {}
    if (host_matches(scan.get('domain'), lists.get('processor_domains'))
            or _domain_in(sig.get('iframeSrcs') or [], lists.get('processor_domains'))):
        return True
    if COMMIT_SIGNATURE_RE.search(url) and TOKEN_PARAM_RE.search(url):
        suspect, _ = surface_signals(scan, lists)
        return bool(suspect or commerce_page(scan, lists))
    return False


def _page_has_instrument_field(scan):
    """A card or bank field anywhere on the page (or fields the scan could not list in
    full). Does NOT refuse an unrelated click by itself; it makes a FORM SUBMIT count as
    committing."""
    if (scan.get('signals') or {}).get('fieldsTruncated'):
        return True
    for f in scan.get('fields') or []:
        if _is_card_field(f) or _is_bank_field(f):
            return True
    return False


def is_committing(scan, action, lists):
    """Does this action create a billing/instrument obligation?"""
    t = scan.get('target') or {}
    if action == 'goto':
        return nav_as_commit(scan, lists)
    if _is_instrument_field(scan, t, lists):
        return True
    if _is_free_select(scan, t, lists):
        return False
    strong = any(_label_in(t, lists, n) for n in (
        'paid_action_labels', 'rail_labels', 'trial_cta_labels', 'pledge_labels',
        'stored_pay_labels', 'express_pay_labels', 'deposit_labels', 'attach_labels'))
    if strong or _weak_pledge(t, lists):
        return True
    suspect, _ = surface_signals(scan, lists)
    if _label_in(t, lists, 'weak_commit_labels') and suspect:
        return True
    if t.get('isFormSubmit') and (suspect or _page_has_instrument_field(scan)):
        return True
    return False


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------

def evaluate(scan, action, expected_domains=(), prior_mutation=False, lists=None):
    """The gate decision for ONE mutating action.

    scan: dict from scan.js, or None when the page could not be scanned.
    action: 'click' | 'type' | 'os-input' (coordinates outside the DOM) | 'goto'.
    expected_domains: domains where the HUMAN allowed committing actions for this task;
        empty means nowhere.
    prior_mutation: an action already changed this tab (relevant for os-input).
    lists: Lists from load_lists(); default lists when None.
    Returns Decision(block, code, reason). Never raises. Reading a page never needs this."""
    if action not in ACTIONS:
        return Decision(True, 'UNRESOLVED', 'unknown action %r -- expected one of %s'
                        % (action, ', '.join(ACTIONS)))
    if scan is None:
        return Decision(True, 'UNRESOLVED',
                        'the page could not be scanned -- refused until a human looks')
    why = _malformed(scan, action)
    if why:
        return Decision(True, 'UNRESOLVED', 'the page scan cannot be judged (%s) -- refused' % why)
    if not isinstance(lists, Lists):
        lists = default_lists()
    try:
        expected = set(d for d in (expected_domains or ()) if isinstance(d, str))
        if not lists.ok:
            return _evaluate_floor_only(scan, action, expected, prior_mutation, lists)
        return _evaluate(scan, action, expected, prior_mutation, lists)
    except Exception as e:  # noqa: BLE001 -- the gate never opens on its own failure
        return Decision(True, 'UNRESOLVED', 'the gate failed on this scan (%s: %s) -- refused'
                        % (type(e).__name__, e))


def _evaluate_floor_only(scan, action, expected, prior_mutation, lists):
    """Lists unusable: every rule fixed in code still runs, on the built-in minimum
    lists; anything with a money signal is refused; only a page with no money signal at
    all lets an action through, and the reason says so."""
    note = 'payment lists unavailable (%s); built-in minimum used' % lists.error
    d = _evaluate(scan, action, expected, prior_mutation, FLOOR_LISTS)
    if d.block:
        return Decision(True, d.code, '%s; %s' % (d.reason, note))
    suspect, _ = surface_signals(scan, FLOOR_LISTS)
    if suspect or commerce_page(scan, FLOOR_LISTS):
        return Decision(True, 'LISTS_UNAVAILABLE', '%s -- refused on a page with money signals' % note)
    if action == 'os-input':
        return Decision(True, 'OS_INPUT', '%s -- os-input refused' % note)
    return Decision(False, 'LISTS_UNAVAILABLE_CLEAN',
                    '%s -- allowed only because the page shows no money signal' % note)


def _evaluate(scan, action, expected, prior_mutation, lists):
    if action == 'goto':
        # A navigation is judged by the address first, then by the landing scan.
        nav = nav_precheck(scan.get('url') or '', lists)
        if nav.block and not host_matches(scan.get('domain'), expected):
            return nav
    t = scan.get('target') or {}
    if action != 'goto' and t.get('found') is False:
        return Decision(True, 'TARGET_NOT_FOUND',
                        'the element to act on was not found on the page -- nothing to judge; '
                        'check the selector (this is not a payment finding)')

    suspect, sdet = surface_signals(scan, lists)

    if action == 'os-input' and (suspect or commerce_page(scan, lists) or prior_mutation):
        return Decision(True, 'OS_INPUT',
                        'input by screen coordinates lands outside the page model -- refused '
                        'on a page with money signals or after an earlier action')

    committing = is_committing(scan, action, lists)
    if committing and not host_matches(scan.get('domain'), expected):
        return Decision(True, 'DOMAIN_FLOOR',
                        'committing action on a domain the human did not allow for this task')

    commerce = commerce_page(scan, lists)
    sig = scan.get('signals') or {}
    # Page-wide on purpose (kept from the original gate): where a page sells AND offers
    # express pay or a saved card, no click there is "unrelated" -- one button can carry
    # two effects; not even a "free" one. What made this rule over-block before was
    # phrases found inside other words; the scanner now matches whole words.
    if commerce and (sig.get('expressPay') or sig.get('savedCardSelector')):
        return Decision(True, 'G_STORED', 'page sells and offers express pay / a saved card -- '
                        'no action on it is treated as unrelated')

    if _is_free_select(scan, t, lists):
        return Decision(False, 'B_FREE', 'explicit free-plan selection (every price next to it is free, no instrument)')

    if _is_card_field(t):
        return Decision(True, 'A_CARD', 'target is a card number / CVV / expiry field')
    if _is_bank_field(t):
        return Decision(True, 'A_BANK', 'target is a bank-account field (IBAN / account / routing)')
    if _is_carrier_field(scan, t, lists):
        return Decision(True, 'A_CARRIER', 'phone field next to a carrier-billing commitment')
    if _label_in(t, lists, 'attach_labels'):
        return Decision(True, 'A_ATTACH', 'target attaches a payment method or wallet')
    # a scan without target.formFields (older or foreign scanner) cannot say which form this
    # control submits: assume it may hold the page's card or bank field
    form_fields = t.get('formFields') if 'formFields' in t else scan.get('fields')
    page_cut = 'formFields' not in t and (scan.get('signals') or {}).get('fieldsTruncated')
    page_cut = page_cut or t.get('formFieldsTruncated') is True  # the form itself was cut at FIELDS_MAX
    if t.get('isFormSubmit') and (page_cut or any(_is_card_field(f) or _is_bank_field(f)
                                                  for f in form_fields or [])):
        return Decision(True, 'A_FORM', 'submits a form that holds a card or bank-account field'
                        + (' (the field list was cut, the rest cannot be seen)' if page_cut else ''))
    heading = (scan.get('heading') or '') + ' ' + (scan.get('title') or '')
    if sdet['s3'] or re.search(r'checkout|billing|add card|add payment|payment method', heading, re.I):
        return Decision(True, 'A_SURFACE', 'action on a dedicated payment page')

    anc = t.get('ancestorText') or ''

    if _label_in(t, lists, 'trial_cta_labels'):
        return Decision(True, 'C_TRIAL', 'trial button -- a card may be demanded on a later screen')
    if TRIAL_TERMS_RE.search(anc):
        return Decision(True, 'C_TRIAL', 'trial-then-charge terms next to the control')

    if BILLING_AUTH_TERMS_RE.search(anc):
        return Decision(True, 'D_AUTH', 'control next to billing-authorization terms')
    if (_label_in(t, lists, 'pledge_labels') or _weak_pledge(t, lists)
            or (RECURRING_TERMS_RE.search(anc) and committing)):
        return Decision(True, 'D_AUTH', 'recurring / pledge / membership commitment')

    tblob = _target_text(t)
    use_balance = any(p in tblob for p in ('use balance', 'redeem balance', 'use store credit',
                                           'использовать баланс'))
    if _label_in(t, lists, 'deposit_labels'):
        return Decision(True, 'G_DEPOSIT', 'add funds / top up / gift card')
    if use_balance and _adjacent_is_free(t) and not _is_card_field(t) and not sdet['s2']:
        return Decision(False, 'G_BALANCE', 'applying free credit to a $0 order with no instrument')
    if commerce and (_label_in(t, lists, 'stored_pay_labels') or _label_in(t, lists, 'express_pay_labels')):
        return Decision(True, 'G_STORED', 'one-click / express / saved-card purchase control')

    if commerce:
        if _label_in(t, lists, 'rail_labels'):
            return Decision(True, 'B_RAIL', 'invoice / direct debit / pay-later control')
        if _label_in(t, lists, 'paid_action_labels') and not _adjacent_is_free(t):
            return Decision(True, 'B_PAID', 'pay / buy / subscribe control on a page that sells')

    if action == 'goto' and nav_as_commit(scan, lists):
        return Decision(True, 'E_NAV', 'navigation commits an order or lands on a payment processor')

    # A plain link is navigation: judge its address. A link INTO a checkout or a payment
    # processor is refused whatever stands around it (an "Add to plan" link to
    # /checkout?key=... has no price in its block). A link elsewhere is not refused for
    # the money text around it (a footnote next to a GDP figure is not a purchase).
    # Every label rule above has already run, so "Buy now" / "Subscribe" links never
    # reach this point.
    href = (t.get('href') or '').strip()
    is_link = (action == 'click' and (t.get('tag') or '').upper() == 'A'
               and href.lower().startswith(('http://', 'https://')))
    if is_link:
        if blocked_url(href, lists):
            return Decision(True, 'E_NAV', 'the link leads to a payment / checkout address')
        nav = nav_precheck(href, lists)
        if nav.block:
            return nav
        if suspect and not sdet['s2']:
            return Decision(False, 'LINK', 'plain link: navigation to %s, judged by its address' % href[:80])

    if suspect:
        return Decision(True, 'FLOOR',
                        'money signals next to the control (%s) and no free classification'
                        % ','.join(k for k, v in sdet.items() if v))

    return Decision(False, 'FREE', 'no payment signal for this action')


def nav_precheck(url, lists=None):
    """URL-only check before navigating (the landing page is not visible yet).
    Never raises; with unusable lists the built-in minimum is used."""
    if not isinstance(lists, Lists):
        lists = default_lists()
    if not lists.ok:
        lists = FLOOR_LISTS
    if not url:
        return Decision(False, 'FREE', 'no url')
    if not isinstance(url, str):
        return Decision(True, 'UNRESOLVED', 'the address is not text -- refused')
    try:
        from urllib.parse import urlparse
        parts = urlparse(url.lower())
        host, path = parts.hostname or '', parts.path or ''
    except Exception:  # noqa: BLE001
        return Decision(True, 'E_NAV', 'the address cannot be parsed -- refused')
    if host_matches(host, lists.get('processor_domains')):
        return Decision(True, 'E_NAV', 'navigation to a payment-processor domain')
    if COMMIT_SIGNATURE_RE.search(url) and TOKEN_PARAM_RE.search(url):
        if VERIFY_PATH_RE.search(path) and not re.search(
                r'/(checkout|pay|purchase|order|place-?order|subscribe)\b', path):
            return Decision(False, 'FREE', 'account verify / activate link')
        return Decision(True, 'E_NAV', 'navigation carries an order/confirm signature and a token')
    return Decision(False, 'FREE', 'plain navigation')
