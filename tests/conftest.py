import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from browser_payment_gate import load_lists  # noqa: E402


def base_scan():
    """A clean, readable scan of an ordinary page on example.com: no money anywhere."""
    return {
        'url': 'https://example.com/page', 'domain': 'example.com',
        'title': 'Example', 'heading': 'Welcome',
        'target': {'found': True, 'tag': 'BUTTON', 'type': 'button',
                   'text': 'Read more', 'aria': '', 'autocomplete': '',
                   'name': '', 'id': '', 'href': '', 'isFormSubmit': False,
                   'ancestorText': 'Read more about us', 'adjacentPrice': '',
                   'inClosedShadow': False},
        'signals': {'orderTotal': False, 'priceShown': False, 'priceAsImage': False,
                    'checkoutSummaryLayout': False, 'paymentIframe': False,
                    'iframeSrcs': [], 'blockedUrl': False, 'expressPay': False,
                    'savedCardSelector': False, 'closedShadowOnPage': False,
                    'unresolvableControls': False},
        'fields': [], 'domHash': 'x',
    }


def scan(**over):
    """base_scan() with top-level keys replaced and the target/signals dicts merged."""
    out = base_scan()
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = dict(out[k], **v)
        else:
            out[k] = v
    return out


@pytest.fixture
def lists():
    """The default lists, loaded fresh (not the module cache)."""
    ls = load_lists()
    assert ls.ok, ls.error
    return ls
