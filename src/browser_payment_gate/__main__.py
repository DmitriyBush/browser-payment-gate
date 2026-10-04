"""Command line: check an edited lists file, and see which list a label falls into.

    python -m browser_payment_gate lists [PATH]
    python -m browser_payment_gate label "Buy now" [--lists PATH]

Exit code: 0 the lists are usable, 1 they are not (the gate would run floor-only).
"""
import argparse
import sys

from .core import REQUIRED_LISTS, load_lists


def _lists(path):
    ls = load_lists(path)
    print('lists: %s' % ls.source)
    if ls.ok:
        print('ok: all %d required lists present and non-empty' % len(REQUIRED_LISTS))
    else:
        print('NOT USABLE: %s' % ls.error)
        print('the gate would run floor-only: stricter on pages with money, never open')
    return ls


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m browser_payment_gate')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('lists', help='check a lists file')
    a.add_argument('path', nargs='?')
    b = sub.add_parser('label', help='which lists match this control text')
    b.add_argument('text')
    b.add_argument('--lists', dest='path')
    args = ap.parse_args(argv)

    ls = _lists(args.path)
    if args.cmd == 'lists':
        for name in REQUIRED_LISTS:
            print('  %-24s %d' % (name, len(ls.get(name))))
        return 0 if ls.ok else 1

    hits = [(n, m.group(1)) for n in REQUIRED_LISTS if n.endswith('_labels')
            for m in [ls.label_rx(n).search(args.text.lower())] if m]
    if not hits:
        print('%r matches no label list (whole words, case-insensitive)' % args.text)
    for n, word in hits:
        print('%r -> %s (word: %r)' % (args.text, n, word))
    return 0 if ls.ok else 1


if __name__ == '__main__':
    sys.exit(main())
