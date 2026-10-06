"""PostgreSQL ledger and checkpointer (a throwaway database per test)."""
import pytest
from conftest import po_for
from invoicecheck.checkdigit import make_corporate_number
from invoicecheck.extraction import gold_to_target
from langgraph.types import Command

from keiriagent.extractors import StaticExtractor
from keiriagent.graph import Deps, build_graph
from keiriagent.pg import PostgresLedger, postgres_saver
from keiriagent.state import POSTED

CLEAN, ISSUE_CD = "inv_003000", "inv_003057"


def test_ledger_contract_matches_the_in_memory_one(pg_dsn):
    reg = "T" + make_corporate_number("123456789012")
    led = PostgresLedger(pg_dsn, seed=[{"invoice_id": "prev", "supplier_reg_no": reg, "invoice_number": "R-1"}])
    assert led.find_duplicate(reg, "R-1") == "prev" and led.find_duplicate(reg, " R-1 ") == "prev"
    assert led.find_duplicate(reg, "R-2") is None and led.find_duplicate(reg, "R-1", exclude_key="prev") is None
    assert led.find_duplicate(None, "R-1") is None and led.find_duplicate(reg, "") is None
    assert led.post("inv-1", {"supplier_reg_no": reg, "invoice_number": "A"}) == "inv-1"
    led.post("inv-1", {"supplier_reg_no": reg, "invoice_number": "CHANGED"})          # idempotent on the key
    rows = {r["invoice_id"]: r for r in led.entries()}
    assert len(led) == 2 and rows["inv-1"]["invoice_number"] == "A"
    led.close()


def test_graph_runs_on_the_postgres_saver_and_ledger(pg_dsn, gold, registry):
    from keiriagent.po import PoStore
    ext = {k: gold_to_target(v) for k, v in gold.items()}
    ledger = PostgresLedger(pg_dsn)
    with postgres_saver(pg_dsn) as saver:
        graph = build_graph(Deps(StaticExtractor(ext), registry, PoStore([po_for(gold[CLEAN]), po_for(gold[ISSUE_CD])]), ledger), "v3_verify_po", saver)
        out = graph.invoke({"invoice_id": CLEAN}, {"configurable": {"thread_id": CLEAN}})
        assert out["outcome"] == POSTED and len(ledger) == 1
        cfg = {"configurable": {"thread_id": ISSUE_CD}}
        paused = graph.invoke({"invoice_id": ISSUE_CD}, cfg)
        assert "__interrupt__" in paused and graph.get_state(cfg).next == ("review",)
    # a brand-new saver (a fresh connection, as after a restart) still sees the paused run and can resume it
    with postgres_saver(pg_dsn) as saver2:
        graph2 = build_graph(Deps(StaticExtractor(ext), registry, PoStore([po_for(gold[ISSUE_CD])]), ledger), "v3_verify_po", saver2)
        assert graph2.get_state(cfg).next == ("review",)
        out = graph2.invoke(Command(resume={"action": "approve", "reviewer": "kato"}), cfg)
        assert out["outcome"] == POSTED and len(ledger) == 2
    ledger.close()
