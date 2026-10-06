from keiriagent.decide import VERSIONS, decide
from keiriagent.state import AUTO_APPROVE, HUMAN_REVIEW, REJECT

OK_V = {"approved": True, "reasons": []}
BAD_V = {"approved": False, "reasons": ["check_digit:invalid"]}
OK_PO = {"status": "matched", "po_id": "PO-1", "reasons": []}
BAD_PO = {"status": "no_po", "po_id": None, "reasons": ["po:no_po"]}
EXT = {"issuer_name": "x"}
V1, V2, V3 = VERSIONS["v1_extract_only"], VERSIONS["v2_verify"], VERSIONS["v3_verify_po"]


def test_nothing_extracted_goes_to_review_in_every_version():
    for cfg in (V1, V2, V3):
        assert decide(cfg, None, None, None, None) == (HUMAN_REVIEW, ["extraction:unparseable"])
        assert decide(cfg, {}, None, None, None)[0] == HUMAN_REVIEW


def test_v1_trusts_the_extraction():
    assert decide(V1, EXT, BAD_V, BAD_PO, "prev-1") == (AUTO_APPROVE, [])


def test_v2_follows_verification_only():
    assert decide(V2, EXT, OK_V, BAD_PO, "prev-1") == (AUTO_APPROVE, [])
    assert decide(V2, EXT, BAD_V, OK_PO, None) == (HUMAN_REVIEW, ["check_digit:invalid"])


def test_v3_needs_verification_and_po_and_rejects_duplicates():
    assert decide(V3, EXT, OK_V, OK_PO, None) == (AUTO_APPROVE, [])
    assert decide(V3, EXT, OK_V, BAD_PO, None) == (HUMAN_REVIEW, ["po:no_po"])
    assert decide(V3, EXT, BAD_V, BAD_PO, None) == (HUMAN_REVIEW, ["check_digit:invalid", "po:no_po"])
    assert decide(V3, EXT, OK_V, OK_PO, "prev-9") == (REJECT, ["duplicate_of:prev-9"])


def test_fails_closed_when_an_enabled_stage_produced_nothing():
    assert decide(V2, EXT, None, None, None) == (HUMAN_REVIEW, ["verification:missing"])
    assert decide(V3, EXT, OK_V, None, None) == (HUMAN_REVIEW, ["po:missing"])
    assert decide(V2, EXT, {"approved": False}, None, None) == (HUMAN_REVIEW, ["verification:failed"])
