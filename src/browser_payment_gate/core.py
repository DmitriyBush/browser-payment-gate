"""Decision core of browser-payment-gate.

Question it answers: an AI agent is about to click, type or navigate in a web page --
could this action spend money or attach a payment instrument? If yes, or if the page
cannot be read, the action is refused and handed to the human.

The core is pure: it takes the page scan produced by scan.js (see scanner.py) and the
action, and returns a Decision. It does not drive a browser and does not import one.

Ancestry: this is the decision layer of the payment gate that has guarded the Serpentis
research system's own browser since June 2026 (Serpentis "kalpa_payment_gate"). Changes
against that gate, measured before release (docs/CALIBRATION.md):
  1. Labels and page phrases are matched as WHOLE WORDS ("making payments" is not
     "G Pay", "extending into" is not "card ending in").
  2. Price/total TEXT counts against an action only NEAR its target (the target's form
     or block). Anywhere on the page it only marks the page as commerce for the
     label rules -- a "Buy now" button on a page with prices is still refused.
     Structural signals (payment iframe, checkout URL, checkout layout) stay page-wide.
  3. A target that is not found is reported as TARGET_NOT_FOUND, not as a payment page.
  4. "support" / "поддержать" alone is not a pledge: it needs money or recurring terms
     next to it (a help-centre "Support" link is not a donation).

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

REQUIRED_LISTS = (
    'paid_action_labels', 'rail_labels', 'trial_cta_labels', 'pledge_labels',
    'pledge_weak_labels', 'stored_pay_labels', 'express_pay_labels', 'deposit_labels',
    'carrier_billing_labels', 'attach_labels', 'weak_commit_labels',
    'processor_domains', 'payment_iframe_domains', 'blocked_url_patterns',
)


class Lists(object):
    """The editable part of the gate. ok is False when the file could not be read or a
    required list is missing/empty -- the gate then runs FLOOR-ONLY (stricter), never
    open."""

    def __init__(self, data, source, error=''):
        self.data = data or {}
        self.source = source
        self.error = error
        missing = [n for n in REQUIRED_LISTS
                   if not (isinstance(self.data.get(n), list) and self.data.get(n))]
        self.ok = not error and not missing
        if missing and not error:
            self.error = 'missing or empty lists: %s' % ', '.join(missing)
        self._rx = {}

    def get(self, name):
        v = self.data.get(name)
        return v if isinstance(v, list) else []

    def label_rx(self, name):
        """One compiled whole-word pattern per list (cached)."""
        rx = self._rx.get(name)
        if rx is None:
            labels = sorted((str(x).lower() for x in self.get(name) if str(x).strip()),
                            key=len, reverse=True)
            if labels:
                rx = re.compile(r'(?<!\w)(' + '|'.join(re.escape(l) for l in labels) + r')(?!\w)', re.I)
            else:
                rx = re.compile(r'(?!x)x')  # matches nothing
            self._rx[name] = rx
        return rx


def load_lists(path=None):
    """Load lists from path, else from $BROWSER_PAYMENT_GATE_LISTS, else the defaults.
    Never raises: a broken file gives Lists(ok=False), and the gate goes floor-only."""
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
FREE_INDICATOR_RE = re.compile(r'\bfree\b|бесплатн', re.I)
FREE_PRICE_RE = re.compile(r'^\s*(free|\$?0([.,]0{1,2})?|0\s*(usd|eur|руб))\s*$', re.I)
# Price and total near the target (same shapes the scanner uses page-wide).
# The WHOLE amount is captured: "$0.99" must not be read as "$0" (free).
PRICE_RE = re.compile(r'(\$|EUR|GBP|RUB|€|£|₽)\s?\d+(?:[.,]\d+)*|\d+[.,]\d{2}\s?(\$|EUR|GBP|USD|RUB|€|£|₽)', re.I)
TOTAL_RE = re.compile(r'\b(total|order summary|amount due|subtotal)\b|итого|к оплате', re.I)


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


def _adjacent_is_free(t):
    price = (t.get('adjacentPrice') or '').strip()
    if price and FREE_PRICE_RE.match(price):
        return True
    return bool(FREE_INDICATOR_RE.search(t.get('text') or ''))


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


def blocked_url(url, lists):
    u = (url or '').lower()
    return any(p.lower() in u for p in lists.get('blocked_url_patterns'))


def _local_money(t):
    """Price or total text in the target's own block (form/section/div)."""
    anc = t.get('ancestorText') or ''
    price = (t.get('adjacentPrice') or '').strip()
    if not price:
        # scan.js fills adjacentPrice itself; a scanner that does not still gets judged
        # on the block text, the same way.
        m = PRICE_RE.search(anc)
        price = m.group(0) if m else ''
    return bool((price and not FREE_PRICE_RE.match(price)) or TOTAL_RE.search(anc))


def surface_signals(scan, lists):
    """Floor signals. Returns (suspect, detail).
    s1 money text NEAR the target; s2 payment iframe on the page; s3 checkout URL;
    s4 checkout layout / express or saved-card text near the target; s5 target inside a
    closed shadow root (unreadable)."""
    sig = scan.get('signals') or {}
    t = scan.get('target') or {}
    anc = t.get('ancestorText') or ''
    s1 = _local_money(t)
    s2 = bool(sig.get('paymentIframe')
              or _domain_in(sig.get('iframeSrcs') or [], lists.get('payment_iframe_domains')))
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
                or sig.get('checkoutSummaryLayout') or sig.get('paymentIframe')
                or _domain_in(sig.get('iframeSrcs') or [], lists.get('payment_iframe_domains'))
                or sig.get('blockedUrl') or blocked_url(scan.get('url'), lists))


def _is_free_select(scan, t, lists):
    if not commerce_page(scan, lists):
        return False
    if _is_card_field(t) or _is_bank_field(t):
        return False
    sig = scan.get('signals') or {}
    if sig.get('paymentIframe') or _domain_in(sig.get('iframeSrcs') or [], lists.get('payment_iframe_domains')):
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


def sig_page(scan):
    return scan.get('signals') or {}


def _page_has_instrument_field(scan):
    """A card or bank field anywhere on the page. Does NOT refuse an unrelated click by
    itself (a billing widget in a dashboard corner is allowed); it makes a FORM SUBMIT
    count as committing."""
    for f in scan.get('fields') or []:
        if _is_card_field(f) or _is_bank_field(f):
            return True
    return False


def evaluate(scan, action, expected_domains=(), prior_mutation=False, lists=None):
    """The gate decision for ONE mutating action.

    scan: dict from scan.js, or None when the page could not be scanned.
    action: 'click' | 'type' | 'os-input' (coordinates outside the DOM) | 'goto'.
    expected_domains: domains where the HUMAN allowed committing actions for this task;
        empty means nowhere.
    prior_mutation: an action already changed this tab (relevant for os-input).
    lists: Lists from load_lists(); default lists when None.
    Returns Decision(block, code, reason). Reading a page never needs this call."""
    lists = lists or default_lists()
    expected = set(expected_domains or ())

    if scan is None:
        return Decision(True, 'UNRESOLVED',
                        'the page could not be scanned -- refused until a human looks')
    t = scan.get('target') or {}
    if action != 'goto' and not t.get('found', True):
        return Decision(True, 'TARGET_NOT_FOUND',
                        'the element to act on was not found on the page -- nothing to judge; '
                        'check the selector (this is not a payment finding)')

    suspect, sdet = surface_signals(scan, lists)

    # Lists unreadable -> floor-only: stricter, never open.
    if not lists.ok:
        if suspect or commerce_page(scan, lists):
            return Decision(True, 'LISTS_UNAVAILABLE',
                            'payment lists unavailable (%s) -- refused on a page with money '
                            'signals' % lists.error)
        if action == 'os-input':
            return Decision(True, 'OS_INPUT', 'lists unavailable -- os-input refused')
        return Decision(False, 'LISTS_UNAVAILABLE_CLEAN',
                        'payment lists unavailable (%s) -- allowed only because the page '
                        'shows no money signal' % lists.error)

    if action == 'os-input' and (suspect or commerce_page(scan, lists) or prior_mutation):
        return Decision(True, 'OS_INPUT',
                        'input by screen coordinates lands outside the page model -- refused '
                        'on a page with money signals or after an earlier action')

    committing = is_committing(scan, action, lists)
    if committing and not host_matches(scan.get('domain'), expected):
        return Decision(True, 'DOMAIN_FLOOR',
                        'committing action on a domain the human did not allow for this task')

    if _is_free_select(scan, t, lists):
        return Decision(False, 'B_FREE', 'explicit free-plan selection (free price/label, no instrument)')

    if _is_card_field(t):
        return Decision(True, 'A_CARD', 'target is a card number / CVV / expiry field')
    if _is_bank_field(t):
        return Decision(True, 'A_BANK', 'target is a bank-account field (IBAN / account / routing)')
    if _is_carrier_field(scan, t, lists):
        return Decision(True, 'A_CARRIER', 'phone field next to a carrier-billing commitment')
    if _label_in(t, lists, 'attach_labels'):
        return Decision(True, 'A_ATTACH', 'target attaches a payment method or wallet')
    heading = (scan.get('heading') or '') + ' ' + (scan.get('title') or '')
    if sdet['s3'] or re.search(r'checkout|billing|add card|add payment|payment method', heading, re.I):
        return Decision(True, 'A_SURFACE', 'action on a dedicated payment page')

    commerce = commerce_page(scan, lists)
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
    # Page-wide on purpose (kept from the original gate, its finding F11): where a page
    # sells AND offers express pay or a saved card, no click there is "unrelated" -- one
    # button can carry two effects. What made this rule over-block before was phrases
    # found inside other words; the scanner now matches whole words.
    if commerce and (sig_page(scan).get('expressPay') or sig_page(scan).get('savedCardSelector')):
        return Decision(True, 'G_STORED', 'page sells and offers express pay / a saved card -- '
                        'no action on it is treated as unrelated')

    if commerce:
        if _label_in(t, lists, 'rail_labels'):
            return Decision(True, 'B_RAIL', 'invoice / direct debit / pay-later control')
        if _label_in(t, lists, 'paid_action_labels') and not _adjacent_is_free(t):
            return Decision(True, 'B_PAID', 'pay / buy / subscribe control on a page that sells')

    if action == 'goto' and nav_as_commit(scan, lists):
        return Decision(True, 'E_NAV', 'navigation commits an order or lands on a payment processor')

    # A plain link is navigation: judge its address, not the money text around it (a
    # footnote next to a GDP figure is not a purchase). Every label rule above has
    # already run, so "Buy now" / "Subscribe" links never reach this point.
    href = (t.get('href') or '').strip()
    if (suspect and action == 'click' and (t.get('tag') or '').upper() == 'A'
            and href.lower().startswith(('http://', 'https://')) and not sdet['s2']):
        if blocked_url(href, lists):
            return Decision(True, 'E_NAV', 'the link leads to a payment / checkout address')
        nav = nav_precheck(href, lists)
        if nav.block:
            return nav
        return Decision(False, 'LINK', 'plain link: navigation to %s, judged by its address' % href[:80])

    if suspect:
        return Decision(True, 'FLOOR',
                        'money signals next to the control (%s) and no free classification'
                        % ','.join(k for k, v in sdet.items() if v))

    return Decision(False, 'FREE', 'no payment signal for this action')


def nav_precheck(url, lists=None):
    """URL-only check before navigating (the landing page is not visible yet)."""
    lists = lists or default_lists()
    if not url:
        return Decision(False, 'FREE', 'no url')
    try:
        from urllib.parse import urlparse
        host = urlparse(url.lower()).hostname or ''
    except Exception:  # noqa: BLE001
        host = ''
    if host_matches(host, lists.get('processor_domains')):
        return Decision(True, 'E_NAV', 'navigation to a payment-processor domain')
    if COMMIT_SIGNATURE_RE.search(url) and TOKEN_PARAM_RE.search(url):
        if VERIFY_PATH_RE.search(url):
            return Decision(False, 'FREE', 'account verify / activate link')
        return Decision(True, 'E_NAV', 'navigation carries an order/confirm signature and a token')
    return Decision(False, 'FREE', 'plain navigation')
