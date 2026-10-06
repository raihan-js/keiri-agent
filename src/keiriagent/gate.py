"""The CI gate: run the graph from a pull request on the frozen evaluation set and fail if it lets a new unsafe invoice through.

Extractions are cached and the graph is deterministic, so the comparison with the committed baseline is exact, invoice by invoice (the same idea as
FlipGate's per-item flips): an invoice that was NOT an unsafe auto-approval in the baseline and is one now is a regression. No statistics, no noise.

  FAIL     a new unsafe auto-approval (approved with a wrong field), or a new approval where review or reject was expected, or automation fell by more
           than `max_automation_drop` (so the gate cannot be satisfied by sending everything to review)
  INVALID  the pinned inputs (gold, extractions, registry) differ from the ones the baseline was built on; nothing can be certified
  PASS     otherwise (fixed invoices and better automation are reported, never penalised)
Exit codes of the CLI: 0 PASS, 1 FAIL, 2 INVALID.
"""
import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .data import load_synthetic_registry, read_jsonl, stores_from_cases
from .decide import VERSIONS
from .evalrun import run_version
from .extractors import CachedExtractor
from .metrics import fmt, summarise, unsafe_vs_expected, unsafe_wrong_field
from .po_synth import build_cases

INPUTS = {"gold": "gold_test.jsonl", "extractions": "qlora_test.jsonl", "registry": "registry_synthetic.jsonl"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_hashes(data_dir):
    return {k: sha256(Path(data_dir) / f) for k, f in INPUTS.items()}


@dataclass
class GateResult:
    verdict: str
    reasons: list = field(default_factory=list)
    regressions_wrong_field: list = field(default_factory=list)
    regressions_vs_expected: list = field(default_factory=list)
    fixed_wrong_field: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    baseline_summary: dict = field(default_factory=dict)
    records: list = field(default_factory=list)


def evaluate(version, data_dir, ids_file):
    """Per-invoice records of `version` (a key of VERSIONS or a GraphConfig) on the frozen sample."""
    data_dir = Path(data_dir)
    gold = read_jsonl(data_dir / INPUTS["gold"])
    cases = build_cases(gold, seed=0)
    store, seed = stores_from_cases(cases)
    keep = set(json.loads(Path(ids_file).read_text())["ids"])
    return run_version(version, [g for g in gold if g["invoice_id"] in keep], {c["invoice_id"]: c for c in cases},
                       CachedExtractor(Path(data_dir) / INPUTS["extractions"]), load_synthetic_registry(Path(data_dir) / INPUTS["registry"]), store, seed, run_id="gate")


def baseline_from(records, version_name, data_dir, commit=""):
    s = summarise(records)
    return {"version": version_name, "n": len(records), "commit": commit, "inputs_sha256": input_hashes(data_dir),
            "summary": {k: s[k] for k in ("unsafe_auto_approval", "unsafe_vs_expected", "automation")},
            "records": {r["invoice_id"]: {"decision": r["decision"], "unsafe_wrong_field": unsafe_wrong_field(r), "unsafe_vs_expected": unsafe_vs_expected(r)}
                        for r in records}}


def check(records, baseline, data_dir, max_automation_drop=0.05):
    now = input_hashes(data_dir)
    if now != baseline["inputs_sha256"]:
        changed = [k for k in now if now[k] != baseline["inputs_sha256"].get(k)]
        return GateResult("INVALID", [f"pinned input changed: {', '.join(changed)}; rebuild the baseline deliberately (--update-baseline) and say why"])
    summary, base = summarise(records), baseline["summary"]
    res = GateResult("PASS", summary=summary, baseline_summary=base, records=records)
    for r in records:
        b = baseline["records"].get(r["invoice_id"])
        if b is None:
            return GateResult("INVALID", [f"{r['invoice_id']} is not in the baseline"])
        if unsafe_wrong_field(r) and not b["unsafe_wrong_field"]:
            res.regressions_wrong_field.append(r["invoice_id"])
        if unsafe_vs_expected(r) and not b["unsafe_vs_expected"]:
            res.regressions_vs_expected.append(r["invoice_id"])
        if b["unsafe_wrong_field"] and not unsafe_wrong_field(r):
            res.fixed_wrong_field.append(r["invoice_id"])
    if res.regressions_wrong_field:
        res.reasons.append(f"{len(res.regressions_wrong_field)} invoice(s) newly auto-approved with a wrong field")
    if res.regressions_vs_expected:
        res.reasons.append(f"{len(res.regressions_vs_expected)} invoice(s) newly auto-approved although review or reject was expected")
    drop = base["automation"]["rate"] - summary["automation"]["rate"]
    if drop > max_automation_drop:
        res.reasons.append(f"automation fell by {100 * drop:.1f} points ({fmt(base['automation'])} to {fmt(summary['automation'])}); limit {100 * max_automation_drop:.0f}")
    if res.reasons:
        res.verdict = "FAIL"
    return res


def markdown(res, version_name, max_automation_drop):
    out = [f"## Keiri-Agent gate: {res.verdict}", "", f"Graph version `{version_name}` on the frozen sample (synthetic invoices, cached extractions).", ""]
    if res.verdict == "INVALID":
        return "\n".join(out + [f"**{r}**" for r in res.reasons]) + "\n"
    s, b = res.summary, res.baseline_summary
    out += ["| Metric | Baseline | This change |", "|---|---|---|"]
    for label, key in (("Unsafe auto-approval (wrong field)", "unsafe_auto_approval"), ("Approved though review/reject expected", "unsafe_vs_expected"), ("Automation", "automation")):
        out.append(f"| {label} | {fmt(b[key])} | {fmt(s[key])} |")
    out.append("")
    if res.reasons:
        out += ["**Why it fails:**"] + [f"- {r}" for r in res.reasons] + [""]
    for title, ids in (("Newly unsafe (wrong field)", res.regressions_wrong_field), ("Newly approved though review/reject expected", res.regressions_vs_expected), ("No longer unsafe", res.fixed_wrong_field)):
        if ids:
            out.append(f"- {title}: " + ", ".join(ids[:15]) + (f" (+{len(ids) - 15} more)" if len(ids) > 15 else ""))
    out.append(f"\nAutomation may fall by at most {100 * max_automation_drop:.0f} points; fixed invoices are never penalised.")
    return "\n".join(out) + "\n"


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(prog="keiri-gate")
    ap.add_argument("--version", default="v3_verify_po", choices=list(VERSIONS))
    ap.add_argument("--data", default=str(root / "data/eval"))
    ap.add_argument("--ids", default=str(root / "data/eval300_ids.json"))
    ap.add_argument("--baseline", default=str(root / "results/gate_baseline.json"))
    ap.add_argument("--max-automation-drop", type=float, default=0.05)
    ap.add_argument("--report")
    ap.add_argument("--update-baseline", action="store_true", help="rewrite the baseline from the current graph (do this deliberately, in its own commit)")
    a = ap.parse_args(argv)
    records = evaluate(a.version, a.data, a.ids)
    if a.update_baseline:
        Path(a.baseline).write_text(json.dumps(baseline_from(records, a.version, a.data), indent=1) + "\n")
        print(f"baseline written: {a.baseline}")
        return 0
    baseline = json.loads(Path(a.baseline).read_text())
    res = check(records, baseline, a.data, a.max_automation_drop)
    md = markdown(res, a.version, a.max_automation_drop)
    print(md)
    if a.report:
        Path(a.report).write_text(md)
    return {"PASS": 0, "FAIL": 1, "INVALID": 2}[res.verdict]


if __name__ == "__main__":
    sys.exit(main())
