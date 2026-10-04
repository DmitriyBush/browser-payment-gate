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
pip install browser-payment-gate                 # the decision core, no dependencies
pip install "browser-payment-gate[playwright]"   # plus the Playwright adapter
```

Python 3.8+. The core imports only the standard library.

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
A full runnable example: `examples/playwright_guard.py`.

## Use with any browser driver

The gate has two halves. `scan.js` runs inside the page and returns a JSON description of
the page and of the target element; `evaluate()` decides from that description.

```python
from browser_payment_gate import scan_expression, parse_scan, evaluate, nav_precheck

scan = parse_scan(driver_evaluate(scan_expression('#buy')))   # None if it failed
decision = evaluate(scan, 'click', expected_domains={'shop.example'})

nav_precheck('https://pay.stripe.com/c/pay/...')   # before navigating: the URL alone
```

Actions: `'click'`, `'type'`, `'goto'`, and `'os-input'` (input by screen coordinates,
which lands outside the page model). Reading a page never needs the gate.

## What it decides

`evaluate()` returns `Decision(block, code, reason)`.

| Code | Block | Meaning |
|---|---|---|
| `UNRESOLVED` | yes | the page could not be scanned |
| `TARGET_NOT_FOUND` | yes | the element was not found -- check the selector (not a payment finding) |
| `LISTS_UNAVAILABLE` | yes | the lists file is broken, and the page shows money |
| `LISTS_UNAVAILABLE_CLEAN` | no | the lists file is broken, but the page shows no money at all |
| `OS_INPUT` | yes | screen-coordinate input on a page with money signals, or after an earlier action |
| `DOMAIN_FLOOR` | yes | a committing action on a domain the human did not allow for this task |
| `A_CARD` / `A_BANK` / `A_CARRIER` / `A_ATTACH` | yes | a card, bank-account or carrier-billing field; attaching a payment method or wallet |
| `A_SURFACE` | yes | an action on a dedicated payment page (checkout / billing address or heading) |
| `C_TRIAL` | yes | a trial that turns into a charge |
| `D_AUTH` | yes | billing authorisation, recurring payment, pledge or membership |
| `G_DEPOSIT` / `G_STORED` | yes | add funds; one-click, express or saved-card purchase |
| `B_RAIL` / `B_PAID` | yes | invoice / pay-later; pay, buy or subscribe on a page that sells |
| `E_NAV` | yes | navigation to a payment processor, or to an order/confirm address with a token |
| `FLOOR` | yes | money next to the control and no rule that frees it |
| `B_FREE` / `G_BALANCE` | no | an explicit free plan; free credit applied to a $0 order |
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
incomplete file never opens the gate -- it runs stricter until the file is fixed. If you
change the lists, the decisions are yours.

## Limits

- **Good-faith guard.** A page can disguise a payment control (an icon without text, a
  canvas, a closed shadow root); an agent that wants to pay can bypass any wrapper.
- **Text only.** A price drawn as an image is not seen by `scan.js`; elements inside closed
  shadow roots are not seen at all.
- **Word lists are English and Russian.** Other languages need their own entries.
- **One declared gap:** a form submit whose own block shows no price, on a page with a price
  elsewhere and no card field, payment frame, checkout address or payment label, is allowed.
  Typing a card number into such a form is still refused.
- Calibration figures and how they were measured: `docs/CALIBRATION.md`.

## Tests

```sh
pip install -e ".[test]"
playwright install chromium        # or have Chrome installed
pytest
```

127 tests: the decision table, the boundaries the calibration moved (whole words, money
near the target, `$0` against `$0.01`), the lists, and the scan in a real headless browser
on local pages (skipped if no browser is available).

## Origin

The gate is cut from the payment guard of the Serpentis research system, which has
guarded that system's own agent browser since June 2026, and recalibrated for general use
(`docs/CALIBRATION.md`).

## License

Apache-2.0.
