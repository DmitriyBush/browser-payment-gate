"""The lists are the part a user may edit. A broken file must make the gate stricter,
never open; an edited file must take effect."""
import json

from browser_payment_gate import evaluate, load_lists
from browser_payment_gate.core import DEFAULT_LISTS_PATH, LISTS_ENV, REQUIRED_LISTS
from conftest import scan

D = {'example.com'}


def _defaults():
    with open(DEFAULT_LISTS_PATH, encoding='utf-8') as f:
        return json.load(f)


def test_default_lists_complete():
    ls = load_lists()
    assert ls.ok, ls.error
    assert all(ls.get(n) for n in REQUIRED_LISTS)


def test_missing_file_is_not_ok(tmp_path):
    ls = load_lists(str(tmp_path / 'nope.json'))
    assert not ls.ok and 'cannot read' in ls.error


def test_not_an_object(tmp_path):
    p = tmp_path / 'l.json'
    p.write_text('[1, 2]', encoding='utf-8')
    assert not load_lists(str(p)).ok


def test_broken_json(tmp_path):
    p = tmp_path / 'l.json'
    p.write_text('{"paid_action_labels": [', encoding='utf-8')
    assert not load_lists(str(p)).ok


def test_empty_required_list_is_not_ok(tmp_path):
    data = _defaults()
    data['paid_action_labels'] = []
    p = tmp_path / 'l.json'
    p.write_text(json.dumps(data), encoding='utf-8')
    ls = load_lists(str(p))
    assert not ls.ok and 'paid_action_labels' in ls.error


def test_broken_lists_refuse_on_money_page(tmp_path):
    ls = load_lists(str(tmp_path / 'nope.json'))
    s = scan(signals={'priceShown': True}, target={'text': 'Buy'})
    assert evaluate(s, 'click', D, False, ls).code == 'LISTS_UNAVAILABLE'


def test_broken_lists_allow_clean_page_and_say_so(tmp_path):
    ls = load_lists(str(tmp_path / 'nope.json'))
    d = evaluate(scan(target={'text': 'Star'}), 'click', D, False, ls)
    assert (d.block, d.code) == (False, 'LISTS_UNAVAILABLE_CLEAN')


def test_broken_lists_refuse_os_input(tmp_path):
    ls = load_lists(str(tmp_path / 'nope.json'))
    assert evaluate(scan(), 'os-input', D, False, ls).code == 'OS_INPUT'


def test_env_var_selects_file(tmp_path, monkeypatch):
    data = _defaults()
    data['deposit_labels'] = ['load wallet']
    p = tmp_path / 'mine.json'
    p.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setenv(LISTS_ENV, str(p))
    ls = load_lists()
    assert ls.source == str(p) and ls.ok


def test_user_added_label_takes_effect(tmp_path):
    data = _defaults()
    data['deposit_labels'] = data['deposit_labels'] + ['load wallet']
    p = tmp_path / 'mine.json'
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    s = scan(target={'text': 'Load wallet'})
    assert evaluate(s, 'click', D, False, load_lists()).block is False
    assert evaluate(s, 'click', D, False, load_lists(str(p))).code == 'G_DEPOSIT'


def test_user_removed_label_stops_matching(tmp_path):
    data = _defaults()
    data['deposit_labels'] = [x for x in data['deposit_labels'] if x != 'add funds']
    p = tmp_path / 'mine.json'
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    s = scan(target={'text': 'Add funds'})
    assert evaluate(s, 'click', D, False, load_lists()).code == 'G_DEPOSIT'
    assert evaluate(s, 'click', D, False, load_lists(str(p))).block is False


def test_label_with_regex_characters_is_literal(tmp_path):
    data = _defaults()
    data['paid_action_labels'] = data['paid_action_labels'] + ['pay (now)', 'c++ plan']
    p = tmp_path / 'mine.json'
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    ls = load_lists(str(p))
    assert ls.ok
    s = scan(signals={'priceShown': True}, target={'text': 'Get the c++ plan'})
    assert evaluate(s, 'click', D, False, ls).code == 'B_PAID'
