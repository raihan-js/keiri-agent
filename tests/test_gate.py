"""The CI gate: passes the unchanged graph, fails regressions, cannot be gamed by routing everything to review, never penalises fixes, refuses to certify changed inputs."""
import json
import shutil
from pathlib import Path

import pytest

from keiriagent import gate
from keiriagent.decide import GraphConfig

ROOT = Path(__file__).parent.parent
DATA, IDS, BASE = ROOT / "data/eval", ROOT / "data/eval300_ids.json", ROOT / "results/gate_baseline.json"


@pytest.fixture(scope="module")
def baseline():
    return json.loads(BASE.read_text())


@pytest.fixture(scope="module")
def current():
    return gate.evaluate("v3_verify_po", DATA, IDS)


def test_the_committed_baseline_is_the_preregistered_v3_result(baseline):
    s = baseline["summary"]
    assert (s["unsafe_auto_approval"]["k"], s["unsafe_vs_expected"]["k"], s["automation"]["k"], baseline["n"]) == (6, 1, 151, 300)


def test_unchanged_graph_passes(current, baseline):
    res = gate.check(current, baseline, DATA)
    assert res.verdict == "PASS" and not res.reasons and not res.regressions_wrong_field and not res.fixed_wrong_field


def test_a_graph_without_verification_fails_with_named_invoices(baseline):
    sabotaged = gate.evaluate(GraphConfig("v3_without_verify", verify=False, check_duplicates=True, match_po=True), DATA, IDS)
    res = gate.check(sabotaged, baseline, DATA)
    assert res.verdict == "FAIL" and res.regressions_wrong_field
    assert "newly auto-approved with a wrong field" in res.reasons[0]
    md = gate.markdown(res, "v3_without_verify", 0.05)
    assert "gate: FAIL" in md and res.regressions_wrong_field[0] in md


def test_sending_everything_to_review_cannot_satisfy_the_gate(current, baseline):
    all_review = [dict(r, decision="human_review") for r in current]
    res = gate.check(all_review, baseline, DATA)
    assert res.verdict == "FAIL" and not res.regressions_wrong_field and any("automation fell" in r for r in res.reasons)


def test_fixes_are_reported_and_never_penalised(baseline):
    v1_records = gate.evaluate("v1_extract_only", DATA, IDS)
    v1_baseline = gate.baseline_from(v1_records, "v1_extract_only", DATA)           # a worse graph as the baseline; the current v3 is the "fix"
    v3 = gate.evaluate("v3_verify_po", DATA, IDS)
    res = gate.check(v3, v1_baseline, DATA, max_automation_drop=1.0)
    assert res.verdict == "PASS" and len(res.fixed_wrong_field) == 51 - 6 and not res.regressions_wrong_field


def test_a_changed_pinned_input_is_invalid_not_pass(tmp_path, baseline):
    d = tmp_path / "eval"
    shutil.copytree(DATA, d)
    with open(d / "qlora_test.jsonl", "a") as f:
        f.write("\n")                                                                 # one byte
    records = gate.evaluate("v3_verify_po", d, IDS)
    res = gate.check(records, baseline, d)
    assert res.verdict == "INVALID" and "extractions" in res.reasons[0]


def test_cli_exit_codes(tmp_path, capsys):
    assert gate.main([]) == 0
    d = tmp_path / "eval"
    shutil.copytree(DATA, d)
    (d / "registry_synthetic.jsonl").write_text((d / "registry_synthetic.jsonl").read_text() + "\n")
    assert gate.main(["--data", str(d)]) == 2
    report = tmp_path / "r.md"
    gate.main(["--report", str(report)])
    assert "gate: PASS" in report.read_text()
