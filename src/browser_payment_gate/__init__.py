"""browser-payment-gate: before an AI agent clicks, types or navigates in a web page,
check whether the action could spend money or attach a payment method. If it could, or if
the page cannot be read, refuse and hand the step to a human.
"""
from .core import Decision, Lists, evaluate, load_lists, default_lists, nav_precheck
from .scanner import (SCAN_JS, scan_expression, parse_scan, scan_page, scan_page_async,
                      check, check_async, guarded_click, guarded_fill, guarded_click_async,
                      guarded_fill_async, PaymentBlocked)

__version__ = '0.1.0.dev0'

__all__ = ['Decision', 'Lists', 'evaluate', 'load_lists', 'default_lists', 'nav_precheck',
           'SCAN_JS', 'scan_expression', 'parse_scan', 'scan_page', 'scan_page_async',
           'check', 'check_async', 'guarded_click', 'guarded_fill', 'guarded_click_async',
           'guarded_fill_async', 'PaymentBlocked', '__version__']
