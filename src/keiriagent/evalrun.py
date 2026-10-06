"""Run one graph version over a set of invoices with cached extractions and return per-invoice records. Offline: no LangSmith, no GPU.

Each run gets a fresh ledger seeded with the duplicate entries, so versions do not see each other's postings. The graph runs with an
in-memory checkpointer (a run that pauses for review is recorded as paused: no reviewer is simulated).
"""
import time

from invoicecheck.extraction import gold_to_target, score
from langgraph.checkpoint.memory import InMemorySaver

from .data import fresh_ledger
from .graph import Deps, build_graph


def run_version(version, gold_rows, cases_by_id, extractor, registry, po_store, ledger_seed, run_id="eval"):
    deps = Deps(extractor, registry, po_store, fresh_ledger(ledger_seed))
    graph = build_graph(deps, version, InMemorySaver())
    name = getattr(version, "name", version)
    records = []
    for g in sorted(gold_rows, key=lambda x: x["invoice_id"]):
        i = g["invoice_id"]
        c = cases_by_id[i]
        t0 = time.perf_counter()
        out = graph.invoke({"invoice_id": i, "document": g.get("image", "")}, {"configurable": {"thread_id": f"{run_id}:{name}:{i}"}})
        ms = 1000 * (time.perf_counter() - t0)
        s = score(extractor.extract(i), gold_to_target(g))
        records.append({
            "invoice_id": i, "scenario": c["scenario"], "has_document_issue": c["has_document_issue"], "expected_decision": c["expected_decision"],
            "decision": out["decision"], "outcome": out.get("outcome"), "reasons": out.get("decision_reasons", []),
            "exact": s["exact"], "covered_exact": s["covered_exact"], "uncovered_exact": s["uncovered_exact"],
            "wrong_fields": [f for f, ok in s["fields"].items() if not ok], "steps": len(out["audit"]), "latency_ms": ms,
        })
    return records
