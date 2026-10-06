#!/usr/bin/env python3
"""Check the LangSmith experiments against the offline run (results/eval_test300.json), invoice by invoice. Writes results/langsmith_experiments.md.

Compares the STORED OUTPUTS of each root run (decision, reasons, outcome) with the offline records, and re-scores the stored extraction with the same
functions. It does not read LangSmith's aggregate feedback: those lag behind the run (feedback arrives asynchronously and was briefly double counted),
so aggregates read right after a run can be wrong. Uses the most recent `keiri-<version>-*` experiment per version. Exit code 1 on any difference."""
import json
import os
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
if not os.environ.get("LANGSMITH_API_KEY"):
    os.environ["LANGSMITH_API_KEY"] = (Path.home() / ".config/langsmith/key").read_text().strip()
os.environ["LANGSMITH_TRACING"] = "false"
sys.path.insert(0, str(ROOT / "src"))

from invoicecheck.extraction import gold_to_target, score  # noqa: E402
from langsmith import Client  # noqa: E402

from keiriagent.data import read_jsonl  # noqa: E402
from keiriagent.metrics import unsafe_vs_expected, unsafe_wrong_field  # noqa: E402

VERSIONS = ["v1_extract_only", "v2_verify", "v3_verify_po"]
N = 300

if __name__ == "__main__":
    local = json.loads((ROOT / "results/eval_test300.json").read_text())["results"]
    gold = {g["invoice_id"]: gold_to_target(g) for g in read_jsonl(ROOT / "data/eval/gold_test.jsonl")}
    c = Client()
    rows, bad = [], 0
    for v in VERSIONS:
        p = sorted(c.list_projects(name_contains=f"keiri-{v}-"), key=lambda x: x.start_time or 0)[-1]
        offline = {r["invoice_id"]: r for r in local[v]["records"]}
        runs = []
        for _ in range(6):                                     # the stored runs can take a moment to appear
            runs = list(c.list_runs(project_id=p.id, is_root=True))
            if len(runs) >= N:
                break
            time.sleep(10)
        diffs, unsafe, unsafe_exp, errors = [], 0, 0, 0
        for r in runs:
            errors += bool(r.error)
            i = (r.inputs or {}).get("invoice_id")
            o = r.outputs or {}
            ref = offline.get(i)
            if ref is None or o.get("decision") != ref["decision"] or o.get("decision_reasons") != ref["reasons"] or o.get("outcome") != ref["outcome"]:
                diffs.append(i)
            rec = {"decision": o.get("decision"), "expected_decision": ref["expected_decision"] if ref else None,
                   "exact": score(o.get("extraction"), gold[i])["exact"] if i in gold else False}
            unsafe += unsafe_wrong_field(rec)
            unsafe_exp += unsafe_vs_expected(rec)
        s = local[v]["summary"]
        ok = len(runs) == N and not diffs and not errors and unsafe == s["unsafe_auto_approval"]["k"] and unsafe_exp == s["unsafe_vs_expected"]["k"]
        bad += not ok
        rows.append((v, p.name, p.url, len(runs), errors, len(diffs), unsafe, s["unsafe_auto_approval"]["k"], unsafe_exp, s["unsafe_vs_expected"]["k"], ok))
    lines = ["# LangSmith experiments: consistency with the offline run", "",
             "Dataset `keiri-eval-300-v1` (300 synthetic test invoices). Each experiment ran the graph inside LangSmith `evaluate`; each run's stored decision, reasons and outcome "
             "were compared invoice by invoice with `results/eval_test300.json`, and the stored extraction was re-scored.", "",
             "| Version | Experiment | Root traces | Errors | Invoices whose decision differs | Unsafe approvals (LangSmith / offline) | Approved though review/reject expected (LangSmith / offline) | Match |", "|---|---|---|---|---|---|---|---|"]
    for v, name, url, n, e, d, u, uo, x, xo, ok in rows:
        lines.append(f"| {v} | [{name}]({url}) | {n} | {e} | {d} | {u} / {uo} | {x} / {xo} | {'yes' if ok else 'NO'} |")
    lines += ["", "The experiment links need a LangSmith login with access to this workspace."]
    (ROOT / "results/langsmith_experiments.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if bad else 0)
