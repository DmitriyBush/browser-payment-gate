"""Running the page scan in a browser.

scan.js is a JavaScript function of the target element. Any tool that can evaluate a
JavaScript expression in a page can feed the gate through scan_expression(selector).
The Playwright adapter does better: it resolves the selector ONCE with a Playwright
locator, scans exactly that element, and acts on exactly that locator -- so the element
judged and the element clicked cannot differ (Playwright's selector engine also enters
open shadow roots, which document.querySelector does not).
"""
import inspect
import json
import os

from .core import Decision, evaluate, default_lists

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, 'scan.js'), 'r', encoding='utf-8') as _f:
    SCAN_JS = _f.read()

_SCAN_FN = '(' + SCAN_JS.strip() + ')'
_SCAN_TIMEOUT_MS = 5000


def scan_expression(selector):
    """A JavaScript expression that scans the page around document.querySelector(selector).
    json.dumps gives a valid JS string literal for any selector text."""
    return ('%s((function(){ try { return document.querySelector(%s); } catch (e) { return null; } })())'
            % (_SCAN_FN, json.dumps(selector or '')))


def parse_scan(result):
    """The scan returns a JSON string; None or garbage means 'not scanned'."""
    if not result:
        return None
    try:
        data = json.loads(result) if isinstance(result, str) else result
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def _unresolved(why):
    return Decision(True, 'UNRESOLVED', 'the page could not be scanned (%s) -- refused until a '
                    'human looks' % why)


def _scan(page, selector):
    """(scan or None, error text, locator or None) -- sync Playwright."""
    try:
        loc = page.locator(selector).first
        n = loc.count()
        if inspect.isawaitable(n):
            n.close()
            return None, 'async page passed to a sync call: use scan_page_async / check_async', None
        if n == 0:
            return parse_scan(page.evaluate(_SCAN_FN + '(null)')), '', None
        res = loc.evaluate(_SCAN_FN, timeout=_SCAN_TIMEOUT_MS)
        scan = parse_scan(res)
        return scan, '' if scan is not None else 'the scan returned nothing usable', loc
    except Exception as e:  # noqa: BLE001 -- any failure means 'unresolved', which refuses
        return None, '%s: %s' % (type(e).__name__, str(e).splitlines()[0][:200] if str(e) else ''), None


async def _scan_async(page, selector):
    try:
        loc = page.locator(selector).first
        n = await loc.count()
        if n == 0:
            return parse_scan(await page.evaluate(_SCAN_FN + '(null)')), '', None
        scan = parse_scan(await loc.evaluate(_SCAN_FN, timeout=_SCAN_TIMEOUT_MS))
        return scan, '' if scan is not None else 'the scan returned nothing usable', loc
    except Exception as e:  # noqa: BLE001
        return None, '%s: %s' % (type(e).__name__, str(e).splitlines()[0][:200] if str(e) else ''), None


def scan_page(page, selector):
    """Playwright (sync API): the scan dict for the element `selector` resolves to, or None
    if the page could not be scanned."""
    return _scan(page, selector)[0]


async def scan_page_async(page, selector):
    """Playwright (async API) twin of scan_page."""
    return (await _scan_async(page, selector))[0]


def _decide(scan, err, action, expected_domains, prior_mutation, lists):
    if scan is None:
        return _unresolved(err or 'no scan')
    return evaluate(scan, action, expected_domains, prior_mutation, lists or default_lists())


class PaymentBlocked(Exception):
    """Raised by the guarded actions when the gate refuses. .decision holds the reason."""

    def __init__(self, decision, what=''):
        self.decision = decision
        super().__init__('payment gate refused %s: %s (%s). A human must do this step.'
                         % (what or 'the action', decision.reason, decision.code))


def check(page, selector, action='click', expected_domains=(), prior_mutation=False, lists=None):
    """Scan and decide (sync Playwright). Returns a Decision; does not act."""
    scan, err, _ = _scan(page, selector)
    return _decide(scan, err, action, expected_domains, prior_mutation, lists)


async def check_async(page, selector, action='click', expected_domains=(), prior_mutation=False,
                      lists=None):
    """Async twin of check."""
    scan, err, _ = await _scan_async(page, selector)
    return _decide(scan, err, action, expected_domains, prior_mutation, lists)


def guarded_click(page, selector, expected_domains=(), lists=None, **click_kwargs):
    """Click through the gate: the element judged is the element clicked. Raises
    PaymentBlocked on refusal; nothing is clicked then."""
    scan, err, loc = _scan(page, selector)
    d = _decide(scan, err, 'click', expected_domains, False, lists)
    if d.block or loc is None:
        raise PaymentBlocked(d if d.block else _unresolved('element vanished'), 'click on %s' % selector)
    return loc.click(**click_kwargs)


def guarded_fill(page, selector, value, expected_domains=(), lists=None, **fill_kwargs):
    """Type through the gate: the element judged is the element filled. Raises
    PaymentBlocked on refusal; nothing is typed then."""
    scan, err, loc = _scan(page, selector)
    d = _decide(scan, err, 'type', expected_domains, False, lists)
    if d.block or loc is None:
        raise PaymentBlocked(d if d.block else _unresolved('element vanished'), 'typing into %s' % selector)
    return loc.fill(value, **fill_kwargs)


async def guarded_click_async(page, selector, expected_domains=(), lists=None, **click_kwargs):
    scan, err, loc = await _scan_async(page, selector)
    d = _decide(scan, err, 'click', expected_domains, False, lists)
    if d.block or loc is None:
        raise PaymentBlocked(d if d.block else _unresolved('element vanished'), 'click on %s' % selector)
    return await loc.click(**click_kwargs)


async def guarded_fill_async(page, selector, value, expected_domains=(), lists=None, **fill_kwargs):
    scan, err, loc = await _scan_async(page, selector)
    d = _decide(scan, err, 'type', expected_domains, False, lists)
    if d.block or loc is None:
        raise PaymentBlocked(d if d.block else _unresolved('element vanished'), 'typing into %s' % selector)
    return await loc.fill(value, **fill_kwargs)


__all__ = ['SCAN_JS', 'scan_expression', 'parse_scan', 'scan_page', 'scan_page_async',
           'check', 'check_async', 'guarded_click', 'guarded_fill', 'guarded_click_async',
           'guarded_fill_async', 'PaymentBlocked', 'Decision']
