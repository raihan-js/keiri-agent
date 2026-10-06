#!/usr/bin/env python3
"""Run the three graph versions over an invoice set and write results/eval_<name>.json plus a Markdown table (offline, cached extractions).

  run_eval.py --name test300 --split test --ids data/eval300_ids.json --preds ../invoice-check-jp/results/preds/qlora_test.jsonl
  run_eval.py --name val150  --split val  --only-with-predictions --preds ../invoice-check-jp/results/preds/qlora_val.jsonl     (development)
The purchase-order world is built over ALL invoices of the split (as pre-registered); --ids / --only-with-predictions only choose which are scored.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from keiriagent.data import load_synthetic_registry, read_jsonl, stores_from_cases  # noqa: E402
from keiriagent.decide import VERSIONS  # noqa: E402
from keiriagent.evalrun import run_version  # noqa: E402
from keiriagent.extractors import CachedExtractor  # noqa: E402
from keiriagent.metrics import fmt, paired, summarise, unsafe_vs_expected, unsafe_wrong_field  # noqa: E402
from keiriagent.po_synth import build_cases  # noqa: E402



def report(name, results, comparisons):
    rows = [("Unsafe auto-approval (wrong field), of all", "unsafe_auto_approval"), ("  of auto-approved only", "unsafe_among_approved"),
            ("Automation rate", "automation"), ("Auto-approved but expected review/reject", "unsafe_vs_expected"),
            ("Agrees with expected decision", "agreement"), ("Routed to review", "review_workload"), ("Falsely rejected", "false_rejections")]
    vs = list(results)
    out = [f"## {name}  (n = {results[vs[0]]['summary']['n']})", "", "| Metric | " + " | ".join(vs) + " |", "|---|" + "---|" * len(vs)]
    for label, key in rows:
        out.append(f"| {label} | " + " | ".join(fmt(results[v]["summary"][key]) for v in vs) + " |")
    out.append("| Steps per invoice (mean) | " + " | ".join(f"{results[v]['summary']['steps_mean']:.2f}" for v in vs) + " |")
    out.append("| Time per invoice, ms (median) | " + " | ".join(f"{results[v]['summary']['latency_ms_median']:.1f}" for v in vs) + " |")
    out += ["", f"Extraction exact-match of the cached extractor on this set: {fmt(results[vs[0]]['summary']['extraction_exact'])}.", "",
            "Wrong fields among unsafe auto-approvals: " + "; ".join(f"{v}: {results[v]['summary']['wrong_fields_among_unsafe'] or 'none'}" for v in vs), "",
            "Paired comparisons (exact McNemar on discordant invoices):", "", "| Comparison | Flag | Flagged A | Flagged B | A only | B only | p |", "|---|---|---|---|---|---|---|"]
    for c in comparisons:
        out.append(f"| {c['a']} vs {c['b']} | {c['flag']} | {c['flag_a']} | {c['flag_b']} | {c['only_a']} | {c['only_b']} | {c['p']:.4g} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--split", required=True, choices=["val", "test", "holdout"])
    ap.add_argument("--preds", required=True)
    ap.add_argument("--ids")
    ap.add_argument("--only-with-predictions", action="store_true")
    a = ap.parse_args()
    DATA = ROOT / ("data/eval" if a.split == "test" else "data/invoice-check-jp")        # test inputs are committed; val and hold-out need scripts/fetch_data.py
    all_gold = read_jsonl(DATA / f"gold_{a.split}.jsonl")
    cases = build_cases(all_gold, seed=0)
    by_id = {c["invoice_id"]: c for c in cases}
    store, seed = stores_from_cases(cases)
    ext = CachedExtractor((ROOT / a.preds).resolve())
    gold = all_gold
    if a.ids:
        keep = set(json.load(open(ROOT / a.ids))["ids"])
        gold = [g for g in gold if g["invoice_id"] in keep]
    if a.only_with_predictions:
        gold = [g for g in gold if ext.extract(g["invoice_id"])]
    registry = load_synthetic_registry(DATA / "registry_synthetic.jsonl")
    results = {}
    for v in VERSIONS:
        recs = run_version(v, gold, by_id, ext, registry, store, seed, run_id=a.name)
        results[v] = {"summary": summarise(recs), "records": recs}
    names = list(VERSIONS)
    comparisons = [{"a": x, "b": y, "flag": fname, **paired(results[x]["records"], results[y]["records"], fn)}
                   for x, y in zip(names, names[1:]) for fname, fn in (("unsafe_wrong_field", unsafe_wrong_field), ("unsafe_vs_expected", unsafe_vs_expected))]
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / f"results/eval_{a.name}.json").write_text(json.dumps({"name": a.name, "split": a.split, "n": len(gold), "preds": a.preds, "results": results,
                                                                  "comparisons": comparisons}, ensure_ascii=False, indent=1) + "\n")
    md = report(a.name, results, comparisons)
    (ROOT / f"results/REPORT_{a.name}.md").write_text(md)
    print(md)
