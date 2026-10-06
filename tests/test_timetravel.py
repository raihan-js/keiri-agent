"""History, replay from a checkpoint into a separate thread, what-if overrides, and the review queue (PostgreSQL)."""
import support
from invoicecheck.extraction import gold_to_target  # noqa: F401
from langgraph.types import Command

from keiriagent.graph import build_graph
from keiriagent.ops import DURABILITY, dry_run_graph, history, pending_reviews, replay, run_config
from keiriagent.pg import PostgresLedger, postgres_saver

CLEAN, ISSUE_CD = "inv_003000", "inv_003057"


def test_history_replay_whatif_and_the_live_run_stays_untouched(pg_dsn):
    ledger = PostgresLedger(pg_dsn)
    deps = support.build_deps(ledger)
    with postgres_saver(pg_dsn) as saver:
        live = build_graph(deps, "v3_verify_po", saver)
        out = live.invoke({"invoice_id": CLEAN}, run_config(CLEAN), **DURABILITY)
        assert out["outcome"] == "posted" and len(ledger) == 1
        hist = history(live, CLEAN)
        assert [h["next"] for h in hist] == [["__start__"], ["ingest"], ["extract"], ["verify"], ["check_duplicate"], ["match_po"], ["decide"], ["post"], []]
        before_decide = next(h for h in hist if h["next"] == ["decide"])
        dry = dry_run_graph(deps, "v3_verify_po", saver)

        # 1. replay unchanged: same decision, the ledger is not written
        same = replay(dry, CLEAN, before_decide["checkpoint_id"], f"{CLEAN}@replay-1")
        assert same["decision"] == "auto_approve" and same["outcome"] == "posted" and len(ledger) == 1
        assert [a["node"] for a in same["audit"]].count("verify") == 1          # earlier steps are carried over, not run again

        # 2. what-if: the PO had been missing -> the replay pauses for review; the live run still says posted
        what_if = replay(dry, CLEAN, before_decide["checkpoint_id"], f"{CLEAN}@replay-2",
                         overrides={"po_match": {"status": "no_po", "po_id": None, "reasons": ["po:no_po"]}})
        assert what_if["decision"] == "human_review" and "__interrupt__" in what_if and what_if["decision_reasons"] == ["po:no_po"]
        live_state = live.get_state(run_config(CLEAN))
        assert live_state.next == () and live_state.values["outcome"] == "posted" and len(ledger) == 1

        # a checkpoint that does not exist, and the final one, are refused instead of silently re-running the invoice
        import pytest
        with pytest.raises(ValueError, match="unknown checkpoint"):
            replay(dry, CLEAN, "does-not-exist", f"{CLEAN}@replay-x")
        with pytest.raises(ValueError, match="end of the run"):
            replay(dry, CLEAN, hist[-1]["checkpoint_id"], f"{CLEAN}@replay-y")

        # 3. replay from the very first checkpoint re-runs everything
        again = replay(dry, CLEAN, hist[0]["checkpoint_id"], f"{CLEAN}@replay-3")
        assert again["outcome"] == "posted" and [a["node"] for a in again["audit"]][0] == "ingest"
    ledger.close()


def test_replay_of_a_reviewed_run_from_the_review_checkpoint(pg_dsn):
    ledger = PostgresLedger(pg_dsn)
    deps = support.build_deps(ledger)
    with postgres_saver(pg_dsn) as saver:
        live = build_graph(deps, "v3_verify_po", saver)
        live.invoke({"invoice_id": ISSUE_CD}, run_config(ISSUE_CD), **DURABILITY)
        live.invoke(Command(resume={"action": "reject", "reviewer": "kato"}), run_config(ISSUE_CD), **DURABILITY)
        hist = history(live, ISSUE_CD)
        before_reject = next(h for h in reversed(hist) if h["next"] == ["reject"])
        dry = dry_run_graph(deps, "v3_verify_po", saver)
        out = replay(dry, ISSUE_CD, before_reject["checkpoint_id"], f"{ISSUE_CD}@replay-1")
        assert out["outcome"] == "rejected" and out["audit"][-1]["by"] == "human:kato"
    ledger.close()


def test_pending_reviews_lists_only_runs_waiting_for_a_person(pg_dsn):
    ledger = PostgresLedger(pg_dsn)
    deps = support.build_deps(ledger)
    with postgres_saver(pg_dsn) as saver:
        g = build_graph(deps, "v3_verify_po", saver)
        g.invoke({"invoice_id": CLEAN}, run_config(CLEAN), **DURABILITY)
        g.invoke({"invoice_id": ISSUE_CD}, run_config(ISSUE_CD), **DURABILITY)
        q = pending_reviews(g, pg_dsn)
        assert [r["invoice_id"] for r in q] == [ISSUE_CD] and "check_digit:invalid" in q[0]["payload"]["reasons"]
        g.invoke(Command(resume={"action": "approve", "reviewer": "kato"}), run_config(ISSUE_CD), **DURABILITY)
        assert pending_reviews(g, pg_dsn) == []
    ledger.close()
