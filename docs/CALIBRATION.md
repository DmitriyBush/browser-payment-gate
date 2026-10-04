# Calibration

This library is cut from the payment guard of the Serpentis research system, which has
guarded that system's own agent browser since June 2026. That guard was strict on purpose,
and in daily use it refused ordinary clicks often enough to be a nuisance; in the
measurement below it refused nearly one ordinary click in five. A guard like that gets
switched off -- and then guards nothing. Before
release we measured why it over-blocked, changed the rules, and measured again on two
sets at once: ordinary pages (false refusals) and pages with real payment buttons
(misses).

## What was changed, and why

1. **Whole words.** The original matched phrases inside other words: "makin**g pay**ments"
   read as *G Pay*, "ext**ending in**to" as *card ending in*. Labels and page phrases are now
   matched as whole words.
2. **Money near the target, not anywhere on the page.** The original treated any price or
   the word "total" anywhere on the page as a reason to refuse *every* action there -- a
   GDP figure in an encyclopaedia, the word "total" in a code example. Price and total text
   now count only in the target's own block (its form or section). Anywhere on the page
   they only mark the page as one that sells, which arms the label rules: a "Buy now"
   button on a page with prices is still refused. Structural signals -- a payment iframe,
   a checkout address -- still count page-wide.
3. **Kept on purpose:** where a page sells *and* offers express pay or a saved card, no
   action on it is treated as unrelated -- one button can carry two effects. The original's
   false refusals under this rule came from item 1, not from the rule.
4. **A missing target is reported as such** (`TARGET_NOT_FOUND`), not as "payment page".
5. **"Support" is not a donation by itself**: it needs money, recurring or donation words
   next to it. A help-centre "Support" link is allowed.
6. **A plain link is navigation**: it is judged by its address, after every label rule
   has run ("Buy now" links never reach this rule).
7. **The whole price is read.** The original read only the first digit of an amount --
   "$0.99" as "$0", which counts as free -- so "Subscribe" next to "$0.99 / month" was
   allowed as a free-plan choice. Found while writing the boundary tests for this release.
8. **Payment addresses are path parts.** `/payment` no longer matches `/payments/...` (a
   documentation section) or `/upgrades-...` (a blog post). A hyphen still continues the
   word, so `/billing-faq` is still refused -- the strict side.

## Measurements

**Ordinary pages (false refusals).** 35 public pages: 13 chosen by hand (encyclopaedia,
documentation, news, code hosting, research sites) and up to 2 same-site links from each.
On each page up to 6 visible links and buttons, spread over the page. Each control was
scanned and judged by both gates in a headless browser with a fresh profile; nothing was
clicked. The human's permission was set to the page's own domain.

| | Original gate | This library |
|---|---|---|
| refused, of 210 ordinary controls | 37 (18 %) | MEASURE |

**Pages with payment buttons (misses).** 7 public pricing and donation pages; only
controls whose text contains a payment-like word (26). Every element was checked by hand:
6 are real purchase buttons (Donate x2, Subscribe, Buy, Buy now x2), the rest are help,
plan descriptions, terms and FAQ.

| | Original gate | This library |
|---|---|---|
| real purchase buttons refused | 6 of 6 | MEASURE |
| other payment-word controls refused | 18 of 20 | MEASURE |

**The original's own self-test** (58 cases) was replayed against this library: 52 decide
the same; 6 differ by design -- three unrelated clicks on pages with a price elsewhere
(item 2), a closed-shadow signal the original scanner never set, express-pay words on a page
that sells nothing, and one case that refuses by an earlier rule with the same outcome.
The remaining declared gap is in the README (*Limits*).

**Limits of these measurements.** The page sets are small and chosen by us: they are a
sanity check, not statistics. No page behind a login was measured (dashboards, shops with a
saved card), and no checkout page with card fields -- those are covered by the test suite
on local pages, not by live pages. Pages that draw their text with scripts after load may
behave differently from what the scan saw.
