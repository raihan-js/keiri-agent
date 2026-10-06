"""With a PERFECT extraction, the full graph must reproduce the expected decision for every invoice.

This ties the pieces together before any model output is involved: the synthetic POs and ledger seeds, the PO matcher, the verification
layer and the decision rule must agree with the expected decisions built from the true documents. Any disagreement here is a bug in the
design, not a model error. Uses the validation split (the split rules were developed on); skipped when the data has not been downloaded.
"""
from collections import Counter
from pathlib import Path

import pytest

DATA = Path(__file__).parent.parent / "data" / "invoice-check-jp"
pytestmark = pytest.mark.skipif(not (DATA / "gold_val.jsonl").exists(), reason="run scripts/fetch_data.py first")


@pytest.mark.parametrize("split", ["val", "test"])
def test_perfect_extraction_reproduces_expected_decisions(split):
    from invoicecheck.extraction import gold_to_target
    from langgraph.checkpoint.memory import InMemorySaver

    from keiriagent.data import fresh_ledger, load_synthetic_registry, read_jsonl, stores_from_cases
    from keiriagent.extractors import StaticExtractor
    from keiriagent.graph import Deps, build_graph
    from keiriagent.po_synth import build_cases

    gold = read_jsonl(DATA / f"gold_{split}.jsonl")
    cases = build_cases(gold, seed=0)
    store, seed = stores_from_cases(cases)
    deps = Deps(StaticExtractor({g["invoice_id"]: gold_to_target(g) for g in gold}), load_synthetic_registry(DATA / "registry_synthetic.jsonl"),
                store, fresh_ledger(seed))
    graph = build_graph(deps, "v3_verify_po", InMemorySaver())
    wrong = []
    for c in cases:
        out = graph.invoke({"invoice_id": c["invoice_id"]}, {"configurable": {"thread_id": c["invoice_id"]}})
        if out["decision"] != c["expected_decision"]:
            wrong.append((c["invoice_id"], c["scenario"], c["has_document_issue"], c["expected_decision"], out["decision"], out["decision_reasons"]))
    assert not wrong, f"{len(wrong)} of {len(cases)} disagree; first: {wrong[:5]}; scenarios: {Counter(w[1] for w in wrong)}"
