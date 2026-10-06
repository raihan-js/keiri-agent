"""The graph is used from several threads (LangSmith evaluate, FastAPI). Regression test for the intermittent sqlite InterfaceError on the shared registry."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

DATA = Path(__file__).parent.parent / "data" / "eval"                   # committed frozen inputs


def test_deps_wrap_the_registry_once(make_deps):
    from keiriagent.graph import Deps
    from keiriagent.registry import LockedRegistry
    d = make_deps()
    assert isinstance(d.registry, LockedRegistry)
    assert Deps(d.extractor, d.registry, d.po_store, d.ledger).registry is d.registry          # not wrapped twice


def test_many_threads_on_the_full_registry_never_raise():
    from langgraph.checkpoint.memory import InMemorySaver

    from keiriagent.data import fresh_ledger, load_synthetic_registry, read_jsonl, stores_from_cases
    from keiriagent.extractors import CachedExtractor
    from keiriagent.graph import Deps, build_graph
    from keiriagent.po_synth import build_cases

    preds = DATA / "qlora_test.jsonl"
    gold = read_jsonl(DATA / "gold_test.jsonl")
    store, seed = stores_from_cases(build_cases(gold, seed=0))
    graph = build_graph(Deps(CachedExtractor(preds), load_synthetic_registry(DATA / "registry_synthetic.jsonl"), store, fresh_ledger(seed)),
                        "v3_verify_po", InMemorySaver())
    errors = []

    def one(g):
        try:
            graph.invoke({"invoice_id": g["invoice_id"]}, {"configurable": {"thread_id": "c:" + g["invoice_id"]}})
        except Exception as e:                                                                  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    for _ in range(3):                                          # the failure was intermittent (2 of 3 trials before the fix)
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(one, gold))
    assert not errors, errors[:3]
