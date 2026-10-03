"""Running the page scan in a browser.

The scan itself is scan.js and runs inside the page. Any tool that can evaluate a
JavaScript expression in a page can feed the gate; this module gives the expression and a
ready adapter for Playwright (sync and async pages).
"""
import json
import os

from .core import Decision, evaluate, default_lists

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, 'scan.js'), 'r', encoding='utf-8') as _f:
    SCAN_JS = _f.read()


def scan_expression(selector):
    """The JavaScript expression to evaluate in the page for this CSS selector."""
    sel = (selector or '').replace('\\', '\\\\').replace('"', '\\"')
    return SCAN_JS.replace('{SELECTOR}', sel)


def parse_scan(result):
    """The scan returns a JSON string; None or garbage means 'not scanned'."""
    if not result:
        return None
    try:
        data = json.loads(result) if isinstance(result, str) else result
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def scan_page(page, selector):
    """Playwright (sync API): scan `page` around the element matched by `selector`.
    Returns the scan dict, or None if the page could not be scanned."""
    try:
        return parse_scan(page.evaluate(scan_expression(selector)))
    except Exception:  # noqa: BLE001 -- any failure means 'unresolved', which refuses
        return None


async def scan_page_async(page, selector):
    """Playwright (async API) twin of scan_page."""
    try:
        return parse_scan(await page.evaluate(scan_expression(selector)))
    except Exception:  # noqa: BLE001
        return None


class PaymentBlocked(Exception):
    """Raised by the guarded actions when the gate refuses. .decision holds the reason."""

    def __init__(self, decision, what=''):
        self.decision = decision
        super().__init__('payment gate refused %s: %s (%s). A human must do this step.'
                         % (what or 'the action', decision.reason, decision.code))


def check(page, selector, action='click', expected_domains=(), prior_mutation=False, lists=None):
    """Scan and decide. Returns a Decision; does not act."""
    return evaluate(scan_page(page, selector), action, expected_domains, prior_mutation,
                    lists or default_lists())


def guarded_click(page, selector, expected_domains=(), lists=None, **click_kwargs):
    """page.click() that first asks the gate. Raises PaymentBlocked on refusal."""
    d = check(page, selector, 'click', expected_domains, lists=lists)
    if d.block:
        raise PaymentBlocked(d, 'click on %s' % selector)
    return page.click(selector, **click_kwargs)


def guarded_fill(page, selector, value, expected_domains=(), lists=None, **fill_kwargs):
    """page.fill() that first asks the gate. Raises PaymentBlocked on refusal."""
    d = check(page, selector, 'type', expected_domains, lists=lists)
    if d.block:
        raise PaymentBlocked(d, 'typing into %s' % selector)
    return page.fill(selector, value, **fill_kwargs)


__all__ = ['SCAN_JS', 'scan_expression', 'parse_scan', 'scan_page', 'scan_page_async',
           'check', 'guarded_click', 'guarded_fill', 'PaymentBlocked', 'Decision']
