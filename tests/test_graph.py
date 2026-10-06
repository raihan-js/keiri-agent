"""The compiled graph end to end, in memory. Durability across a real restart is the next milestone's test."""
import pytest
from conftest import po_for
from invoicecheck.extraction import gold_to_target
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from keiriagent.decide import VERSIONS
from keiriagent.graph import build_graph, stages_for
from keiriagent.state import AUTO_APPROVE, HUMAN_REVIEW, PENDING_REVIEW, POSTED, REJECT, REJECTED

CLEAN, TAXINC, ISSUE_CD = "inv_003000", "inv_003005", "inv_003057"


def run(make_deps, invoice_id, version="v3_verify_po", orders=None, ledger_seed=(), gold=None, extractions=None):
    deps = make_deps(extractions=extractions, orders=orders if orders is not None else [po_for(gold[invoice_id])], ledger_seed=ledger_seed)
    graph = build_graph(deps, version, InMemorySaver())
    cfg = {"configurable": {"thread_id": invoice_id}}
    out = graph.invoke({"invoice_id": invoice_id, "document": f"images/{invoice_id}.jpg"}, cfg)
    return graph, cfg, deps, out


def events(out):
    return [(a["node"], a["event"]) for a in out["audit"]]


def test_a_clean_matched_invoice_is_auto_approved_and_posted(make_deps, gold):
    _, _, deps, out = run(make_deps, CLEAN, gold=gold)
    assert out["decision"] == AUTO_APPROVE and out["outcome"] == POSTED and out["decision_reasons"] == []
    assert events(out) == [("ingest", "received"), ("extract", "parsed"), ("verify", "passed"), ("check_duplicate", "unique"),
                           ("match_po", "matched"), ("decide", AUTO_APPROVE), ("post", "posted")]
    assert len(deps.ledger) == 1 and "__interrupt__" not in out


def test_tax_included_invoice_also_passes(make_deps, gold):
    assert run(make_deps, TAXINC, gold=gold)[3]["outcome"] == POSTED


def test_a_failed_check_pauses_for_review_and_posts_nothing(make_deps, gold):
    graph, cfg, deps, out = run(make_deps, ISSUE_CD, gold=gold)
    assert out["decision"] == HUMAN_REVIEW and out["outcome"] == PENDING_REVIEW
    assert "check_digit:invalid" in out["decision_reasons"]
    assert out["__interrupt__"][0].value["invoice_id"] == ISSUE_CD and "check_digit:invalid" in out["__interrupt__"][0].value["reasons"]
    assert len(deps.ledger) == 0 and graph.get_state(cfg).next == ("review",)


def test_reviewer_approval_resumes_the_same_thread_and_posts(make_deps, gold):
    graph, cfg, deps, _ = run(make_deps, ISSUE_CD, gold=gold)
    out = graph.invoke(Command(resume={"action": "approve", "reviewer": "kato"}), cfg)
    assert out["outcome"] == POSTED and deps.ledger.entries()[0]["approved_by"] == "human:kato"
    assert ("review", "approve") in events(out) and graph.get_state(cfg).next == ()


def test_reviewer_rejection_ends_without_posting(make_deps, gold):
    graph, cfg, deps, _ = run(make_deps, ISSUE_CD, gold=gold)
    out = graph.invoke(Command(resume={"action": "reject", "reviewer": "kato"}), cfg)
    assert out["outcome"] == REJECTED and len(deps.ledger) == 0 and events(out)[-1] == ("reject", "rejected")


def test_reviewer_correction_is_applied_before_posting(make_deps, gold):
    graph, cfg, deps, _ = run(make_deps, ISSUE_CD, gold=gold)
    right = gold[ISSUE_CD]["true_issuer_registration_number"]
    out = graph.invoke(Command(resume={"action": "correct", "reviewer": "kato", "corrections": {"registration_number": right}}), cfg)
    assert out["extraction"]["registration_number"] == right
    assert deps.ledger.entries()[0]["supplier_reg_no"] == right and ("review", "correct") in events(out)


def test_a_malformed_reviewer_answer_asks_again_and_can_still_be_resumed(make_deps, gold):
    graph, cfg, deps, _ = run(make_deps, ISSUE_CD, gold=gold)
    out = graph.invoke(Command(resume={"action": "approve"}), cfg)         # no reviewer name
    assert "reviewer name" in out["__interrupt__"][0].value["error"]
    assert len(deps.ledger) == 0 and graph.get_state(cfg).next == ("review",)
    out = graph.invoke(Command(resume={"action": "maybe", "reviewer": "kato"}), cfg)   # still bad: asks again
    assert "action must be one of" in out["__interrupt__"][0].value["error"] and len(deps.ledger) == 0
    out = graph.invoke(Command(resume={"action": "approve", "reviewer": "kato"}), cfg)
    assert out["outcome"] == POSTED and len(deps.ledger) == 1 and "__interrupt__" not in out


def test_a_duplicate_is_rejected_without_review(make_deps, gold):
    g = gold[CLEAN]
    seed = [{"invoice_id": "prev", "supplier_reg_no": g["issuer"]["registration_number"], "invoice_number": g["invoice_number"]}]
    _, _, deps, out = run(make_deps, CLEAN, gold=gold, ledger_seed=seed)
    assert out["decision"] == REJECT and out["outcome"] == REJECTED and out["decision_reasons"] == ["duplicate_of:prev"]
    assert len(deps.ledger) == 1 and "__interrupt__" not in out


def test_a_missing_po_goes_to_review_in_v3_but_posts_in_v2(make_deps, gold):
    assert run(make_deps, CLEAN, "v3_verify_po", orders=[], gold=gold)[3]["decision_reasons"] == ["po:no_po"]
    assert run(make_deps, CLEAN, "v2_verify", orders=[], gold=gold)[3]["outcome"] == POSTED


def test_v1_posts_a_bad_invoice_because_it_checks_nothing(make_deps, gold):
    _, _, deps, out = run(make_deps, ISSUE_CD, "v1_extract_only", gold=gold)
    assert out["decision"] == AUTO_APPROVE and out["outcome"] == POSTED and len(deps.ledger) == 1


def test_an_unparseable_extraction_goes_to_review_in_every_version(make_deps, gold):
    for v in VERSIONS:
        out = run(make_deps, CLEAN, v, gold=gold, extractions={})[3]
        assert out["decision"] == HUMAN_REVIEW and out["decision_reasons"] == ["extraction:unparseable"], v


def test_each_version_has_the_stages_it_claims():
    assert stages_for(VERSIONS["v1_extract_only"]) == ["ingest", "extract", "decide"]
    assert stages_for(VERSIONS["v2_verify"]) == ["ingest", "extract", "verify", "decide"]
    assert stages_for(VERSIONS["v3_verify_po"]) == ["ingest", "extract", "verify", "check_duplicate", "match_po", "decide"]


def test_every_version_compiles_and_draws(make_deps):
    for v in VERSIONS:
        g = build_graph(make_deps(), v)
        nodes = set(g.get_graph().nodes)
        assert {"ingest", "extract", "decide", "review", "post", "reject"} <= nodes
        assert ("verify" in nodes) == VERSIONS[v].verify and ("match_po" in nodes) == VERSIONS[v].match_po
