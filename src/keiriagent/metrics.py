"""The pre-registered metrics (docs/PREREGISTRATION.md), as pure functions over per-invoice records. Used by the offline run, the LangSmith
evaluators and the CI gate, so all three report the same numbers.

A record is one invoice's outcome at the point the graph either acts or pauses (no reviewer is simulated):
  decision (auto_approve / human_review / reject), expected_decision, exact (every extracted field right), wrong_fields, steps, latency_ms ...
"""
from collections import Counter

from invoicecheck.evaluation import clopper_pearson
from scipy.stats import binomtest

from .state import AUTO_APPROVE, HUMAN_REVIEW, REJECT


def rate(flags):
    """k, n, rate and the exact 95% Clopper-Pearson interval of a list of booleans."""
    n, k = len(flags), sum(bool(f) for f in flags)
    lo, hi = clopper_pearson(k, n) if n else (None, None)
    return {"k": k, "n": n, "rate": (k / n if n else None), "lo": lo, "hi": hi}


def unsafe_wrong_field(r):
    """Primary: auto-approved although at least one extracted field is wrong."""
    return r["decision"] == AUTO_APPROVE and not r["exact"]


def unsafe_vs_expected(r):
    """Secondary: auto-approved although the expected decision is review or reject (document issue, PO problem, duplicate)."""
    return r["decision"] == AUTO_APPROVE and r["expected_decision"] != AUTO_APPROVE


def summarise(records):
    approved = [r for r in records if r["decision"] == AUTO_APPROVE]
    lat = sorted(r["latency_ms"] for r in records)
    out = {
        "n": len(records),
        "unsafe_auto_approval": rate([unsafe_wrong_field(r) for r in records]),
        "unsafe_among_approved": rate([not r["exact"] for r in approved]),
        "automation": rate([r["decision"] == AUTO_APPROVE for r in records]),
        "unsafe_vs_expected": rate([unsafe_vs_expected(r) for r in records]),
        "unsafe_vs_expected_among_approved": rate([r["expected_decision"] != AUTO_APPROVE for r in approved]),
        "agreement": rate([r["decision"] == r["expected_decision"] for r in records]),
        "review_workload": rate([r["decision"] == HUMAN_REVIEW for r in records]),
        "false_rejections": rate([r["decision"] == REJECT and r["expected_decision"] != REJECT for r in records]),
        "extraction_exact": rate([r["exact"] for r in records]),
        "steps_mean": sum(r["steps"] for r in records) / len(records) if records else None,
        "latency_ms_mean": sum(lat) / len(lat) if lat else None,
        "latency_ms_median": lat[len(lat) // 2] if lat else None,
        "decisions": dict(Counter(r["decision"] for r in records)),
        "wrong_fields_among_unsafe": dict(Counter(f for r in records if unsafe_wrong_field(r) for f in r["wrong_fields"])),
    }
    return out


def paired(records_a, records_b, flag):
    """Exact McNemar test of `flag` between two versions on the same invoices: discordant pairs and the two-sided exact p."""
    a = {r["invoice_id"]: flag(r) for r in records_a}
    b = {r["invoice_id"]: flag(r) for r in records_b}
    ids = sorted(set(a) & set(b))
    only_a = sum(a[i] and not b[i] for i in ids)        # flagged in A only
    only_b = sum(b[i] and not a[i] for i in ids)        # flagged in B only
    d = only_a + only_b
    return {"n": len(ids), "flag_a": sum(a[i] for i in ids), "flag_b": sum(b[i] for i in ids), "only_a": only_a, "only_b": only_b,
            "p": (binomtest(min(only_a, only_b), d, 0.5).pvalue if d else 1.0)}


def fmt(r, pct=True):
    if r["rate"] is None:
        return "-"
    f = (lambda x: f"{100 * x:.1f}%") if pct else (lambda x: f"{x:.3f}")
    return f"{f(r['rate'])} [{f(r['lo'])}, {f(r['hi'])}] ({r['k']}/{r['n']})"
