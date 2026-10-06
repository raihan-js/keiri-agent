"""Each node on its own: stubbed dependencies, no graph, no checkpointer."""
from conftest import po_for
from invoicecheck.extraction import gold_to_target

from keiriagent.decide import VERSIONS
from keiriagent.graph import make_nodes
from keiriagent.state import AUTO_APPROVE, HUMAN_REVIEW, PENDING_REVIEW, POSTED, REJECT, REJECTED

CLEAN, ISSUE_CD, ISSUE_TAX = "inv_003000", "inv_003057", "inv_003069"
V3 = VERSIONS["v3_verify_po"]


def nodes(make_deps, cfg=V3, **kw):
    deps = make_deps(**kw)
    return make_nodes(deps, cfg), deps


def test_ingest_requires_an_invoice_id(make_deps):
    n, _ = nodes(make_deps)
    assert n["ingest"]({"invoice_id": "x"})["audit"][0]["event"] == "received"
    import pytest
    with pytest.raises(ValueError):
        n["ingest"]({})


def test_extract_returns_the_extraction_and_an_audit_line(make_deps):
    n, _ = nodes(make_deps)
    out = n["extract"]({"invoice_id": CLEAN})
    assert out["extraction"]["registration_number"].startswith("T") and out["audit"][0]["event"] == "parsed"
    out = n["extract"]({"invoice_id": "unknown"})
    assert out["extraction"] is None and out["audit"][0]["event"] == "unparseable"


def test_verify_passes_a_clean_invoice_and_fails_injected_issues(make_deps, gold):
    n, _ = nodes(make_deps)
    ok = n["verify"]({"extraction": gold_to_target(gold[CLEAN])})
    assert ok["verification"]["approved"] is True
    bad = n["verify"]({"extraction": gold_to_target(gold[ISSUE_CD])})
    assert bad["verification"]["approved"] is False and "check_digit:invalid" in bad["verification"]["reasons"]
    tax = n["verify"]({"extraction": gold_to_target(gold[ISSUE_TAX])})
    assert any(r.startswith("tax:") for r in tax["verification"]["reasons"])


def test_verify_skips_when_nothing_was_extracted(make_deps):
    n, _ = nodes(make_deps)
    out = n["verify"]({"extraction": None})
    assert "verification" not in out and out["audit"][0]["event"] == "skipped"


def test_check_duplicate_finds_a_prior_posting_but_not_itself(make_deps, gold):
    g = gold[CLEAN]
    seed = [{"invoice_id": "prev-1", "supplier_reg_no": g["issuer"]["registration_number"], "invoice_number": g["invoice_number"]}]
    n, _ = nodes(make_deps, ledger_seed=seed)
    assert n["check_duplicate"]({"invoice_id": CLEAN, "extraction": gold_to_target(g)})["duplicate_of"] == "prev-1"
    n2, _ = nodes(make_deps, ledger_seed=[{**seed[0], "invoice_id": CLEAN}])
    assert n2["check_duplicate"]({"invoice_id": CLEAN, "extraction": gold_to_target(g)})["duplicate_of"] is None


def test_match_po_node_reports_status(make_deps, gold):
    g = gold[CLEAN]
    n, _ = nodes(make_deps, orders=[po_for(g)])
    assert n["match_po"]({"extraction": gold_to_target(g)})["po_match"]["status"] == "matched"
    n2, _ = nodes(make_deps)
    assert n2["match_po"]({"extraction": gold_to_target(g)})["po_match"]["status"] == "no_po"


def test_decide_node_sets_pending_review_only_for_review(make_deps):
    n, _ = nodes(make_deps)
    ok = n["decide"]({"extraction": {"x": 1}, "verification": {"approved": True}, "po_match": {"status": "matched"}, "duplicate_of": None})
    assert ok["decision"] == AUTO_APPROVE and "outcome" not in ok
    rv = n["decide"]({"extraction": {"x": 1}, "verification": {"approved": True}, "po_match": {"status": "no_po", "reasons": ["po:no_po"]}})
    assert rv["decision"] == HUMAN_REVIEW and rv["outcome"] == PENDING_REVIEW and rv["decision_reasons"] == ["po:no_po"]


def test_post_writes_once_and_records_who_approved(make_deps, gold):
    g = gold[CLEAN]
    n, deps = nodes(make_deps, orders=[po_for(g)])
    state = {"invoice_id": CLEAN, "extraction": gold_to_target(g), "decision": AUTO_APPROVE, "po_match": {"po_id": f"PO-{CLEAN}"}}
    first = n["post"](state)
    n["post"](state)                                              # a re-run must not post a second row
    row = deps.ledger.entries()[0]
    assert first["outcome"] == POSTED and len(deps.ledger) == 1
    assert row["approved_by"] == "auto" and row["po_id"] == f"PO-{CLEAN}" and row["grand_total"] == g["grand_total"]
    human = n["post"]({**state, "invoice_id": "other", "decision": HUMAN_REVIEW, "decision_reasons": ["po:no_po"], "review": {"reviewer": "kato"}})
    assert deps.ledger.entries()[1]["approved_by"] == "human:kato" and deps.ledger.entries()[1]["override_reasons"] == ["po:no_po"] and human["outcome"] == POSTED


def test_reject_records_who_rejected(make_deps):
    n, _ = nodes(make_deps)
    assert n["reject"]({"decision": REJECT, "decision_reasons": ["duplicate_of:p"]})["audit"][0]["by"] == "auto"
    out = n["reject"]({"decision": HUMAN_REVIEW, "review": {"reviewer": "kato"}})
    assert out["outcome"] == REJECTED and out["audit"][0]["by"] == "human:kato"
