# The lists

`lists.json` holds every word and domain the gate looks for. The rules that use them are
code (`core.py`); the vocabulary is data, so you can adapt it -- another language, a site
you trust, a payment provider we did not list.

## How matching works

- **Labels** (`*_labels`) are matched against the control's own text and `aria-label`,
  lower-cased, as **whole words**: `pay` matches "Pay" and "Pay now", not "Payments" or
  "Repay". Punctuation inside a label is literal (`c++ plan`, `pay (now)`).
- **Domains** (`processor_domains`, `payment_iframe_domains`) match the host itself or any
  subdomain (`paypal.com` matches `www.paypal.com`). For iframes a look-alike host such as
  `paypal.com.example` also matches -- on the side of refusing.
- **URL patterns** (`blocked_url_patterns`): a pattern starting with `/` is a path part and
  must not run on into a longer word -- `/payment` matches `/payment`, `/payment/x`,
  `/payment-step`, not `/payments` (a hyphen continues the word, a letter does not). Other
  patterns (`checkout.stripe.com`) match anywhere in the address.

## Each list

"Committing" below means the action creates an obligation; a committing action is
refused on any domain the human did not allow for the task (`DOMAIN_FLOOR`).

| List | Catches | If you remove an entry |
|---|---|---|
| `paid_action_labels` | pay / buy / subscribe / checkout on a page that sells (`B_PAID`); committing anywhere | such a button passes unless money stands next to it (`FLOOR`) or another list catches it |
| `rail_labels` | invoice, direct debit, pay-later (`B_RAIL`) on a page that sells | the rail button passes on the same terms |
| `trial_cta_labels` | "start free trial" anywhere (`C_TRIAL`); also stops the free-plan exception | a trial that asks for a card on a later screen passes; "free" next to it may make it `B_FREE` |
| `pledge_labels` | donate, pledge, become a member -- anywhere (`D_AUTH`) | a donation button passes unless money or recurring terms stand next to it |
| `pledge_weak_labels` | "support" -- only with money, recurring or donation words next to it | a "Support" button with monthly or donation words but no price beside it passes (with a price beside it, `FLOOR` still refuses) |
| `stored_pay_labels` | buy now, 1-click, place order, use balance (`G_STORED`) on a page that sells; stops the free-plan exception | a one-click purchase with a saved card passes if no other list names it |
| `express_pay_labels` | Apple Pay, Google Pay, G Pay buttons (`G_STORED`); the same words next to a control mark it as money | an express-pay button passes; the page-wide rule F11 still uses the scan's own pattern |
| `deposit_labels` | add funds, top up, deposit, gift card -- anywhere (`G_DEPOSIT`) | a top-up passes |
| `carrier_billing_labels` | turns a phone field into a payment instrument when these words stand next to it (`A_CARRIER`) | mobile-operator billing by phone number passes (a phone field without these words is never treated as an instrument) |
| `attach_labels` | add card, add payment method, connect wallet -- anywhere (`A_ATTACH`) | attaching a card passes unless the field itself is a card field (`A_CARD` is code, not list) |
| `weak_commit_labels` | continue / next / start -- committing only when money stands next to the control | such a button with a price beside it is still refused (`FLOOR`), but no longer counts as committing for `DOMAIN_FLOOR` |
| `processor_domains` | navigating to a payment processor (`E_NAV`), before and after landing | navigation to that processor passes `nav_precheck` |
| `payment_iframe_domains` | a payment iframe on the page: every unrelated control nearby becomes suspect | a page with that provider's card frame is treated as an ordinary page |
| `blocked_url_patterns` | a checkout / billing address: every action on the page (`A_SURFACE`); a link to it (`E_NAV`) | that checkout address is judged like any other page |

Fixed in code, not in the lists (changing them changes what the gate *means*): card,
bank and carrier field patterns, trial and billing-authorisation phrases, price and total
patterns, the free-price pattern, the rule order.

## A broken file

A missing file, invalid JSON, a non-object, or any required list missing or empty makes
`Lists.ok` false. The gate then runs **floor-only**: it refuses on any page with a money
signal (`LISTS_UNAVAILABLE`), refuses screen-coordinate input, and allows only on pages
that show no money at all (`LISTS_UNAVAILABLE_CLEAN`, which says why). It never opens.

## Checking an edited file

```sh
python -m browser_payment_gate lists my_lists.json          # usable? how many entries?
python -m browser_payment_gate label "Top up wallet" --lists my_lists.json
pytest                                                        # the decision table on the defaults
```

The test suite runs on the default lists. To run the decision table against yours, set
`BROWSER_PAYMENT_GATE_LISTS=my_lists.json` -- tests that assume a default entry you removed
will fail, and each failure names the case your change opened.

If you change the lists, the decisions are yours.
