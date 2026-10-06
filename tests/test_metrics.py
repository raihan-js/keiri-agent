import pytest

from keiriagent.metrics import paired, rate, summarise, unsafe_vs_expected, unsafe_wrong_field


def rec(i, decision, exact=True, expected="auto_approve", fields=(), steps=7, ms=1.0):
    return {"invoice_id": i, "decision": decision, "exact": exact, "expected_decision": expected, "wrong_fields": list(fields), "steps": steps, "latency_ms": ms}


def test_rate_matches_clopper_pearson_at_the_edges():
    r = rate([False] * 50)
    assert r["k"] == 0 and r["n"] == 50 and r["lo"] == 0.0 and 0.05 < r["hi"] < 0.08          # 3/n rule: about 5.8% for n = 50
    assert rate([True] * 10)["hi"] == 1.0 and rate([])["rate"] is None


def test_the_two_unsafe_definitions_are_different_things():
    wrong_but_right_decision = rec("a", "auto_approve", exact=False, expected="auto_approve", fields=["invoice_number"])
    right_but_should_not_post = rec("b", "auto_approve", exact=True, expected="human_review")
    reviewed = rec("c", "human_review", exact=False, expected="auto_approve")
    assert unsafe_wrong_field(wrong_but_right_decision) and not unsafe_vs_expected(wrong_but_right_decision)
    assert unsafe_vs_expected(right_but_should_not_post) and not unsafe_wrong_field(right_but_should_not_post)
    assert not unsafe_wrong_field(reviewed) and not unsafe_vs_expected(reviewed)                  # routed to a person: not unsafe


def test_summary_denominators_and_counts():
    rs = [rec("1", "auto_approve"), rec("2", "auto_approve", exact=False, fields=["issue_date", "invoice_number"]), rec("3", "human_review", exact=False),
          rec("4", "reject", expected="reject"), rec("5", "reject", expected="auto_approve")]
    s = summarise(rs)
    assert s["unsafe_auto_approval"]["k"] == 1 and s["unsafe_auto_approval"]["n"] == 5            # over all invoices
    assert s["unsafe_among_approved"]["k"] == 1 and s["unsafe_among_approved"]["n"] == 2          # over approved ones only
    assert s["automation"]["k"] == 2 and s["review_workload"]["k"] == 1 and s["false_rejections"]["k"] == 1
    assert s["wrong_fields_among_unsafe"] == {"issue_date": 1, "invoice_number": 1} and s["decisions"] == {"auto_approve": 2, "human_review": 1, "reject": 2}


def test_paired_mcnemar_counts_discordant_pairs_and_uses_the_exact_test():
    a = [rec(str(i), "auto_approve", exact=False) for i in range(10)]                             # all unsafe in A
    b = [rec(str(i), "human_review", exact=False) for i in range(10)]                             # none unsafe in B
    p = paired(a, b, unsafe_wrong_field)
    assert (p["only_a"], p["only_b"], p["n"]) == (10, 0, 10) and p["p"] == pytest.approx(2 * 0.5 ** 10)
    same = paired(a, a, unsafe_wrong_field)
    assert same["only_a"] == same["only_b"] == 0 and same["p"] == 1.0
