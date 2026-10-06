import pytest

from keiriagent.ledger import InMemoryLedger
from keiriagent.review import apply_corrections, validate_review


def test_post_is_idempotent_on_the_key():
    led = InMemoryLedger()
    assert led.post("inv-1", {"supplier_reg_no": "T1", "invoice_number": "A"}) == "inv-1"
    led.post("inv-1", {"supplier_reg_no": "T1", "invoice_number": "CHANGED"})
    assert len(led) == 1 and led.entries()[0]["invoice_number"] == "A"


def test_duplicate_is_by_supplier_and_invoice_number_and_ignores_the_own_key():
    from invoicecheck.checkdigit import make_corporate_number
    reg = "T" + make_corporate_number("123456789012")
    led = InMemoryLedger([{"invoice_id": "prev", "supplier_reg_no": reg, "invoice_number": "R-1"}])
    assert led.find_duplicate(reg, "R-1") == "prev"
    assert led.find_duplicate(reg, " R-1 ") == "prev"          # whitespace is not a different number
    assert led.find_duplicate(reg, "R-2") is None
    assert led.find_duplicate(reg, "R-1", exclude_key="prev") is None
    assert led.find_duplicate(None, "R-1") is None and led.find_duplicate(reg, "") is None


def test_validate_review_accepts_the_three_actions():
    assert validate_review({"action": "approve", "reviewer": "kato"})["action"] == "approve"
    assert validate_review({"action": "reject", "reviewer": "kato"})["action"] == "reject"
    assert validate_review({"action": "correct", "reviewer": "kato", "corrections": {"grand_total": 100}})


@pytest.mark.parametrize("bad", [None, "approve", {"action": "maybe", "reviewer": "k"}, {"action": "approve"}, {"action": "approve", "reviewer": " "},
                                 {"action": "correct", "reviewer": "k"}, {"action": "correct", "reviewer": "k", "corrections": {"colour": 1}}])
def test_validate_review_rejects_malformed_answers(bad):
    with pytest.raises(ValueError):
        validate_review(bad)


def test_apply_corrections_returns_a_copy_and_replaces_whole_fields():
    ext = {"grand_total": 1, "items": [{"description": "a"}]}
    out = apply_corrections(ext, {"items": [{"description": "b"}]})
    assert out["items"] == [{"description": "b"}] and ext["items"] == [{"description": "a"}] and out["grand_total"] == 1
