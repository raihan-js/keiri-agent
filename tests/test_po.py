from conftest import po_for
from invoicecheck.extraction import gold_to_target

from keiriagent.po import BUYER_MISMATCH, LINE_MISMATCH, MATCHED, NO_PO, TOTAL_MISMATCH, POLine, PoStore, match_po

A = "inv_003000"


def test_matches_when_everything_agrees(gold):
    r = match_po(gold_to_target(gold[A]), PoStore([po_for(gold[A])]))
    assert (r.status, r.po_id, r.reasons) == (MATCHED, f"PO-{A}", [])


def test_no_po_for_unknown_supplier_or_missing_number(gold):
    ext = gold_to_target(gold[A])
    assert match_po(ext, PoStore([])).status == NO_PO
    assert match_po({**ext, "registration_number": None}, PoStore([po_for(gold[A])])).status == NO_PO
    other = po_for(gold[A], supplier_reg_no="T0000000000000")
    assert match_po(ext, PoStore([other])).status == NO_PO


def test_buyer_mismatch_and_same_core_name_is_accepted(gold):
    ext = gold_to_target(gold[A])
    r = match_po(ext, PoStore([po_for(gold[A], buyer_name="全く別の会社")]))
    assert r.status == BUYER_MISMATCH and r.reasons == ["po:buyer_mismatch"]
    # the recipient printed without its legal form is still the same party
    core = ext["recipient_name"].replace("株式会社", "").replace("合同会社", "").replace("有限会社", "")
    assert match_po({**ext, "recipient_name": core}, PoStore([po_for(gold[A])])).status == MATCHED


def test_total_and_line_mismatch_are_reported_together_in_fixed_order(gold):
    ext = gold_to_target(gold[A])
    g = gold[A]
    lines = (POLine(g["items"][0]["description"], g["items"][0]["quantity"] + 1, g["items"][0]["unit_price"]),) + po_for(g).lines[1:]
    r = match_po(ext, PoStore([po_for(g, lines=lines, total=g["grand_total"] - 100)]))
    assert r.status == TOTAL_MISMATCH and r.reasons == ["po:total_mismatch", "po:line_mismatch"]


def test_line_mismatch_alone_when_total_agrees(gold):
    g = gold[A]
    lines = po_for(g).lines[:-1]
    r = match_po(gold_to_target(g), PoStore([po_for(g, lines=lines)]))
    assert r.status == LINE_MISMATCH


def test_tolerance_is_zero_by_default_and_configurable(gold):
    g = gold[A]
    store = PoStore([po_for(g, total=g["grand_total"] + 1)])
    assert match_po(gold_to_target(g), store).status == TOTAL_MISMATCH
    assert match_po(gold_to_target(g), store, tolerance_yen=1).status == MATCHED


def test_picks_the_closest_po_of_the_supplier(gold):
    g = gold[A]
    far = po_for(g, po_id="PO-far", total=g["grand_total"] + 5000)
    near = po_for(g)
    assert match_po(gold_to_target(g), PoStore([far, near])).po_id == near.po_id
    assert match_po(gold_to_target(g), PoStore([near, far])).po_id == near.po_id


def test_non_integer_total_never_matches(gold):
    ext = {**gold_to_target(gold[A]), "grand_total": "322211"}
    assert match_po(ext, PoStore([po_for(gold[A])])).status == TOTAL_MISMATCH
