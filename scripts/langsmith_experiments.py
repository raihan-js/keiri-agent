#!/usr/bin/env python3
"""Create the LangSmith dataset (300 synthetic test invoices) and run each graph version as an experiment.

  langsmith_experiments.py --create-dataset                    upload the 300 examples (once)
  langsmith_experiments.py --limit 10 --prefix trial           a small trial run of every version
  langsmith_experiments.py --prefix keiri                      the full experiments (3 x 300 invoices)
The graph runs for real inside LangSmith's `evaluate` (cached extractions, in-memory checkpointer, fresh seeded ledger per version). Evaluators use
the same functions as the offline run (keiriagent.metrics), so the two must agree; `--check results/eval_test300.json` compares them.
Evaluator runs are not traced (disable_evaluator_tracing) to keep the trace count at one root trace per invoice. Key: ~/.config/langsmith/key.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
if not os.environ.get("LANGSMITH_API_KEY"):                  # CI passes the key as a secret; locally it is read from the private file
    os.environ["LANGSMITH_API_KEY"] = (Path.home() / ".config/langsmith/key").read_text().strip()
os.environ.setdefault("LANGSMITH_TRACING", "true")

from invoicecheck.evaluation import clopper_pearson  # noqa: E402
from invoicecheck.extraction import FIELDS, gold_to_target, score  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langsmith import Client, evaluate  # noqa: E402

from keiriagent.data import fresh_ledger, load_synthetic_registry, read_jsonl, stores_from_cases  # noqa: E402
from keiriagent.decide import VERSIONS  # noqa: E402
from keiriagent.extractors import CachedExtractor  # noqa: E402
from keiriagent.graph import Deps, build_graph  # noqa: E402
from keiriagent.metrics import unsafe_vs_expected, unsafe_wrong_field  # noqa: E402
from keiriagent.po_synth import build_cases  # noqa: E402
from keiriagent.state import AUTO_APPROVE, HUMAN_REVIEW, REJECT  # noqa: E402

DATA = ROOT / "data/eval"                                    # the committed frozen inputs (also used by the CI gate)
DATASET = "keiri-eval-300-v1"
PREDS = DATA / "qlora_test.jsonl"


def world():
    gold = read_jsonl(DATA / "gold_test.jsonl")
    cases = build_cases(gold, seed=0)
    store, seed = stores_from_cases(cases)
    return gold, {c["invoice_id"]: c for c in cases}, store, seed


def create_dataset(client):
    gold, by_id, _, _ = world()
    ids = set(json.load(open(ROOT / "data/eval300_ids.json"))["ids"])
    if client.has_dataset(dataset_name=DATASET):
        n = sum(1 for _ in client.list_examples(dataset_name=DATASET))
        print(f"dataset {DATASET} exists with {n} examples")
        return
    ds = client.create_dataset(DATASET, description="300 synthetic Invoice-Check JP test invoices (seeded sample) with expected decisions from the synthetic PO world; "
                                                    "see docs/PREREGISTRATION.md. Fictitious companies only.")
    examples = [{"inputs": {"invoice_id": g["invoice_id"], "document": g["image"]},
                 "outputs": {"expected_decision": by_id[g["invoice_id"]]["expected_decision"], "scenario": by_id[g["invoice_id"]]["scenario"],
                             "has_document_issue": by_id[g["invoice_id"]]["has_document_issue"], "gold": gold_to_target(g)},
                 "metadata": {"split": "test", "template": g["template"], "layout": g["layout"]}}
                for g in sorted(gold, key=lambda x: x["invoice_id"]) if g["invoice_id"] in ids]
    client.create_examples(dataset_id=ds.id, examples=examples)
    print(f"created {DATASET} with {len(examples)} examples")


def record(outputs, ref):
    s = score(outputs.get("extraction"), ref["gold"])
    return {"decision": outputs["decision"], "expected_decision": ref["expected_decision"], "exact": s["exact"], "wrong_fields": [f for f, ok in s["fields"].items() if not ok]}


def field_accuracy(outputs, reference_outputs):
    s = score(outputs.get("extraction"), reference_outputs["gold"])
    return {"key": "field_accuracy", "score": sum(s["fields"].values()) / len(FIELDS)}


def extraction_exact(outputs, reference_outputs):
    return {"key": "extraction_exact", "score": int(record(outputs, reference_outputs)["exact"])}


def decision_correct(outputs, reference_outputs):
    return {"key": "decision_correct", "score": int(outputs["decision"] == reference_outputs["expected_decision"])}


def unsafe_auto_approval(outputs, reference_outputs):
    return {"key": "unsafe_auto_approval", "score": int(unsafe_wrong_field(record(outputs, reference_outputs)))}


def approved_vs_expected(outputs, reference_outputs):
    return {"key": "approved_vs_expected_unsafe", "score": int(unsafe_vs_expected(record(outputs, reference_outputs)))}


def steps(outputs, reference_outputs):
    return {"key": "steps", "score": outputs["steps"]}


def _rate(key, flags):
    n, k = len(flags), sum(flags)
    lo, hi = clopper_pearson(k, n)
    return {"key": key, "score": k / n, "comment": f"{k}/{n}, 95% CI [{100 * lo:.1f}%, {100 * hi:.1f}%]"}


def summary(runs, examples):
    recs = [record(r.outputs, e.outputs) for r, e in zip(runs, examples) if r.outputs]
    approved = [x for x in recs if x["decision"] == AUTO_APPROVE]
    return {"results": [
        _rate("unsafe_auto_approval_rate", [unsafe_wrong_field(x) for x in recs]),
        _rate("unsafe_among_approved_rate", [not x["exact"] for x in approved]),
        _rate("automation_rate", [x["decision"] == AUTO_APPROVE for x in recs]),
        _rate("approved_vs_expected_unsafe_rate", [unsafe_vs_expected(x) for x in recs]),
        _rate("decision_agreement_rate", [x["decision"] == x["expected_decision"] for x in recs]),
        _rate("review_workload_rate", [x["decision"] == HUMAN_REVIEW for x in recs]),
        _rate("false_rejection_rate", [x["decision"] == REJECT and x["expected_decision"] != REJECT for x in recs]),
    ]}


def make_target(version, tag):
    _, _, store, seed = world()
    deps = Deps(CachedExtractor(PREDS), load_synthetic_registry(DATA / "registry_synthetic.jsonl"), store, fresh_ledger(seed))
    graph = build_graph(deps, version, InMemorySaver())

    def target(inputs: dict) -> dict:
        out = graph.invoke({"invoice_id": inputs["invoice_id"], "document": inputs["document"]},
                           {"configurable": {"thread_id": f"{tag}:{version}:{inputs['invoice_id']}"}})
        return {"decision": out["decision"], "outcome": out.get("outcome"), "decision_reasons": out.get("decision_reasons", []),
                "extraction": out.get("extraction"), "steps": len(out["audit"])}
    return target


def run(client, prefix, limit, versions):
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    data = list(client.list_examples(dataset_name=DATASET, limit=limit)) if limit else DATASET
    for v in versions:
        res = evaluate(make_target(v, f"{prefix}-{v}"), data=data,
                       evaluators=[field_accuracy, extraction_exact, decision_correct, unsafe_auto_approval, approved_vs_expected, steps],
                       summary_evaluators=[summary], experiment_prefix=f"{prefix}-{v}", max_concurrency=2, disable_evaluator_tracing=True,
                       metadata={"version": v, "git_commit": commit, "preregistration": "docs/PREREGISTRATION.md", "extractor": "invoice-check-jp qlora_test.jsonl",
                                 "data": "synthetic"})
        print(f"{v}: experiment {res.experiment_name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--create-dataset", action="store_true")
    ap.add_argument("--prefix", default="keiri")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--versions", nargs="*", default=list(VERSIONS))
    a = ap.parse_args()
    client = Client()
    if a.create_dataset:
        create_dataset(client)
    else:
        run(client, a.prefix, a.limit, a.versions)
