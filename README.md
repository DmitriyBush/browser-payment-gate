# browser-payment-gate

Before an AI agent clicks, types or navigates in a web page, ask one question: **could
this action spend money or attach a payment method?** If it could -- or if the page cannot
be read -- the action is refused and handed to a human.

**What is different here.** Most payment guards for agents sit on a payment *rail*: the
agent calls the guard before it spends from a wallet or an API, and the guard checks the
amount against rules. This library sits on the *browser*: an agent that browses ordinary
web pages can spend without ever calling a payment API -- a "Subscribe" button on a site
where the human's card is saved, an "Apple Pay" button, a trial that asks for a card two
screens later. The gate reads the page around the control the agent is about to use and
decides before the click. It runs locally, needs no service, account or key, and its
word lists are a JSON file you can read and edit.

It is a guard for a **well-meaning** agent: it keeps an agent from paying by accident. It
does not stop a hostile page that disguises its controls, nor an agent that wants to pay
and drives the browser around it (see *Limits*).

## Install

```sh
pip install "git+https://github.com/Serpentis-Git/browser-payment-gate"   # the decision core, no dependencies
pip install "browser-payment-gate[playwright] @ git+https://github.com/Serpentis-Git/browser-payment-gate"   # plus the Playwright adapter
```

Not on PyPI yet: install from this repository as shown. Python 3.8+. The core imports only the standard library.

## Use with Playwright

```python
from browser_payment_gate import guarded_click, guarded_fill, check, PaymentBlocked

ALLOWED = set()   # domains where the human allowed committing actions for THIS task

try:
    guarded_click(page, '#subscribe', expected_domains=ALLOWED)
except PaymentBlocked as e:
    hand_to_human(e.decision.reason)

d = check(page, 'input[name=card]', 'type')   # ask without acting
print(d.block, d.code, d.reason)
```

A refused `guarded_click` / `guarded_fill` raises `PaymentBlocked` and does **not** act.
The adapter resolves the selector once with a Playwright locator, scans exactly that
element and acts on exactly that locator, so the element judged is the element clicked
(also inside open shadow roots). Async pages: `check_async`, `guarded_click_async`,
`guarded_fill_async`. A full runnable example: `examples/playwright_guard.py`.

## Use with any browser driver

The gate has two halves. `scan.js` is a JavaScript function of the target element that
runs inside the page and returns a JSON description of the page and of that element;
`evaluate()` decides from that description. `scan_expression(selector)` wraps it with
`document.querySelector` -- if your driver resolves selectors differently (shadow roots),
pass the element it will act on to the function in `SCAN_JS` instead.

If you build the scan yourself instead of using `scan.js`, include `target.formFields` (the fields of
the form the target submits; `[]` when it submits none). Without it the gate cannot tell which form a
submit button belongs to, so on a page with a card or bank field every form submit is refused.

```python
from browser_payment_gate import scan_expression, parse_scan, evaluate, nav_precheck

scan = parse_scan(driver_evaluate(scan_expression('#buy')))   # None if it failed
decision = evaluate(scan, 'click', expected_domains={'shop.example'})

nav_precheck('https://pay.stripe.com/c/pay/...')   # before navigating: the URL alone
```

Actions: `'click'`, `'type'`, `'goto'`, and `'os-input'` (input by screen coordinates,
which lands outside the page model). Reading a page never needs the gate. `evaluate()`
never raises: a scan of an unexpected shape, an unknown action or an internal failure is
refused as `UNRESOLVED` with the reason.

## What it decides

`evaluate()` returns `Decision(block, code, reason)`.

| Code | Block | Meaning |
|---|---|---|
| `UNRESOLVED` | yes | the page could not be scanned, the scan has an unexpected shape, the action is unknown |
| `TARGET_NOT_FOUND` | yes | the element was not found -- check the selector (not a payment finding) |
| `LISTS_UNAVAILABLE` | yes | the lists file is broken, and the page shows money |
| `LISTS_UNAVAILABLE_CLEAN` | no | the lists file is broken, but the page shows no money at all |
| `OS_INPUT` | yes | screen-coordinate input on a page with money signals, or after an earlier action |
| `DOMAIN_FLOOR` | yes | a committing action on a domain the human did not allow for this task |
| `A_CARD` / `A_BANK` / `A_CARRIER` / `A_ATTACH` | yes | a card, bank-account or carrier-billing field; attaching a payment method or wallet |
| `A_FORM` | yes | submits a form that holds a card or bank-account field |
| `A_SURFACE` | yes | an action on a dedicated payment page (checkout / billing address or heading) |
| `C_TRIAL` | yes | a trial that turns into a charge |
| `D_AUTH` | yes | billing authorisation, recurring payment, pledge or membership |
| `G_DEPOSIT` / `G_STORED` | yes | add funds; one-click, express or saved-card purchase |
| `B_RAIL` / `B_PAID` | yes | invoice / pay-later; pay, buy or subscribe on a page that sells |
| `E_NAV` | yes | navigation to a payment processor, or to an order/confirm address with a token |
| `FLOOR` | yes | money next to the control and no rule that frees it |
| `B_FREE` / `G_BALANCE` | no | an explicit free plan (every price next to it is free); free credit applied to a $0 order |
| `LINK` | no | a plain link next to money text, judged by its address |
| `FREE` | no | no payment signal for this action |

`expected_domains` is the human's permission for the task. Empty means *nowhere*: every
committing action is refused, whatever the page.

## Editing the lists

The words and domains the gate looks for are in `lists.json`. Copy it, edit it, and pass
the path to `load_lists()` or set `BROWSER_PAYMENT_GATE_LISTS`. Check an edited file:

```sh
python -m browser_payment_gate lists my_lists.json
python -m browser_payment_gate label "Buy credits" --lists my_lists.json
```

What each list catches and what you open by shortening it: `docs/LISTS.md`. A broken or
incomplete file never opens the gate: the rules fixed in code keep running on a small
built-in list, every page with a money signal is refused, and the reason names the broken
file. If you change the lists, the decisions are yours.

## Limits

- **Good-faith guard.** A page can disguise a payment control (an icon without text, a
  canvas, a closed shadow root); an agent that wants to pay can bypass any wrapper.
- **Text only.** A price drawn as an image is not seen by `scan.js`; elements inside closed
  shadow roots are not seen at all.
- **Word lists are English and Russian.** Other languages need their own entries. Prices
  are recognised in $, EUR, GBP, RUB, KZT, UAH, CHF (symbol or code, before or after the
  number); other currencies are not seen as money.
- **One declared gap:** a form submit is allowed when its own form shows no price and holds
  no card or bank field, and the page has no payment frame, checkout address or payment
  label -- even if a price is shown elsewhere on the page. Typing a card number is always
  refused.
- Calibration figures and how they were measured: `docs/CALIBRATION.md`.

## Tests

```sh
pip install -e ".[test]"
playwright install chromium        # or have Chrome installed
pytest
```

235 tests: the decision table, the boundaries the calibration moved (whole words, money
near the target, `$0` against `$0.01`), malformed scans and broken lists, and the scan in a
real headless browser on local pages (skipped if no browser is available).

## Origin

The gate is cut from the payment guard of the Serpentis research system, which has
guarded that system's own agent browser since June 2026, and recalibrated for general use
(`docs/CALIBRATION.md`).

## License

Apache-2.0.
