# Keiri-Agent: evaluation report

Scored 2026-10-06 following [`docs/PREREGISTRATION.md`](../docs/PREREGISTRATION.md) (committed before scoring; the harness commit `035298a` also precedes it). Raw per-invoice records: `eval_test300.json`, `eval_holdout200.json`; tables as generated: `REPORT_test300.md`, `REPORT_holdout200.md`; development run on the validation split: `REPORT_val150.md`.

**Everything here is about synthetic invoices, a synthetic registry and synthetic purchase orders, one extractor (the Invoice-Check JP QLoRA adapter, replayed from stored outputs), one PO seed and one sample.** No reviewer is simulated: a run that needs a person is counted as "routed to review", not as right or wrong. Intervals are exact 95% Clopper-Pearson.

## Pre-registered results

**Test sample (300 invoices, seeded sample of the 600-invoice test split; extractor exact-match 83.0%, 249/300)**

| Metric | v1 extract only | v2 + verification | v3 + duplicate check and PO matching |
|---|---|---|---|
| **Unsafe auto-approval** (approved with a wrong field), of all 300 | 17.0% [12.9, 21.7] (51) | 4.0% [2.1, 6.9] (12) | 2.0% [0.7, 4.3] (6) |
| of the auto-approved only | 17.0% [12.9, 21.7] (51/300) | 5.2% [2.7, 8.9] (12/232) | 4.0% [1.5, 8.4] (6/151) |
| **Automation rate** | 100% (300) | 77.3% [72.2, 81.9] (232) | 50.3% [44.5, 56.1] (151) |
| Auto-approved though review or reject was expected | 42.0% [36.4, 47.8] (126) | 27.0% [22.1, 32.4] (81) | 0.3% [0.0, 1.8] (1) |
| Agrees with the expected decision | 58.0% (174) | 64.7% (194) | 91.0% [87.2, 94.0] (273) |
| Routed to review | 0 | 22.7% (68) | 43.3% (130) |
| Falsely rejected | 0 | 0 | 0 |
| Steps per invoice (mean) / median time | 4.00 / 2.5 ms | 4.77 / 3.0 ms | 6.57 / 4.0 ms |

Wrong fields among the unsafe approvals: v1 registration number 33, invoice number 13, issue date 10, issuer name 8, items 1; v2 issue date 6, invoice number 5, items 1; v3 invoice number 4, issue date 2.

Paired (exact McNemar, discordant invoices): unsafe approvals v1 vs v2 **39 vs 0, p = 3.6e-12**; v2 vs v3 **6 vs 0, p = 0.031**. Approved though review or reject was expected: v1 vs v2 45 vs 0 (p = 5.7e-14); v2 vs v3 80 vs 0 (p = 1.7e-24). With four paired tests pre-registered on this sample, a Bonferroni threshold is 0.0125, so the v2 vs v3 difference in unsafe approvals does **not** clear it.

**Hold-out (200 invoices on layouts the extractor never saw; extractor exact-match 51.5%, 103/200)**

| Metric | v1 | v2 | v3 |
|---|---|---|---|
| Unsafe auto-approval, of all 200 | 48.5% [41.4, 55.7] (97) | 9.0% [5.4, 13.9] (18) | 0.5% [0.0, 2.8] (1) |
| of the auto-approved only | 48.5% (97/200) | 17.1% [10.5, 25.7] (18/105) | 1.6% [0.0, 8.4] (1/64) |
| Automation rate | 100% | 52.5% [45.3, 59.6] (105) | 32.0% [25.6, 38.9] (64) |
| Auto-approved though review or reject was expected | 37.5% (75) | 15.0% (30) | 0.0% [0.0, 1.8] (0) |
| Routed to review | 0 | 47.5% (95) | 62.5% (125) |

Wrong fields among the unsafe approvals: v2 items 17, issue date 3, invoice number 1; v3 issue date 1.

## Hypotheses, as pre-registered

| | Prediction | Result |
|---|---|---|
| H1 | v1's unsafe rate equals the share of wrong extractions (about 17%) | **Held.** 17.0% (51/300) = 300 - 249 exact. By construction: v1 approves everything it can parse. |
| H2 | v2 cuts it sharply but not to zero; the residual sits in fields no check covers | **Held.** 4.0% of all, 5.2% of the approved; the 12 are issue date (6), invoice number (5) and one item line. Invoice-Check JP measured 4.6% on its full test split. |
| H3 | v3 lowers the residual only through the fields a PO can see (recipient, item text, totals), not through invoice number or issue date; if no reduction, report a null | **The mechanism held; the headline reduction on the test sample does not mean what it looks like.** See the post-hoc analysis below. |
| H4 | v3's automation rate is lower than v2's | **Held.** 77.3% to 50.3% on test, 52.5% to 32.0% on hold-out. |

## Post-hoc analysis (NOT pre-registered): why v3 approves fewer wrong invoices

The pre-registered comparison says v3 had 6 unsafe approvals against v2's 12 (p = 0.031). Looking at why each of the 6 invoices stopped being approved:

- **2** were true duplicates (rejected correctly); their wrong field was the issue date, which the duplicate check does not read.
- **3** sat in scenarios where the synthetic PO world disagrees with the truth (no PO, wrong buyer, line mismatch) and were routed away by that, again with a wrong date or invoice number that the PO check does not read.
- **1** (inv_003534, PO world agrees with the truth) had a misread item line; the PO check caught it.

So **5 of the 6 were routed away because of the PO scenario, not because the PO check noticed an extraction error**; the lower "of all 300" rate is mostly lower automation. Restricting to invoices whose PO world agrees with the truth removes that effect:

| Slice | v2 approved / wrong | v3 approved / wrong | Wrong extractions the PO check stopped |
|---|---|---|---|
| Test sample, PO world agrees (199) | 151 / 6 | 150 / 5 | **1** (an item line); the 5 that remain are invoice number (3) and issue date (2) |
| Hold-out, PO world agrees (150) | 75 / 12 | 64 / 1 | **11** (item text), and it stopped no correct extraction; 1 remains (issue date) |

Reading: **PO matching works when the extractor's mistakes are in fields a PO can see.** On the hold-out, where a vertical layout makes the model misread item descriptions, it stopped 11 of 12 residual wrong approvals. On the test sample, where the residual errors are invoice number and issue date, it adds almost nothing (1 of 6) and costs 27 points of automation. The cost of that precision here is optimistic: the synthetic POs are built from the true item lines, so a PO check on real data with free-text item descriptions would raise many more false alarms.

Duplicates: of 22 duplicate invoices in the test sample, 19 were rejected, 2 went to review (a misread field tripped a check), and 1 was auto-approved because its invoice number was misread, which is the field the duplicate check keys on. Two of the three duplicates that v2 approved with a wrong field were stopped only by this check.

## What the automation number means

With a perfect extractor, the expected decisions allow 58.0% automation on the test sample (174 of 300 are clean, have a matching PO and are not duplicates), and v3 reached 50.3%: of the 174 invoices that should be approved it approved 150 and sent 24 to review, and in all 24 the extraction was wrong. On the hold-out the ceiling is 62.5% and v3 reached 32.0%. The review workload (43.3% on test) is dominated by the synthetic scenario mix (30% of invoices are given a PO or ledger problem on purpose, and 11% carry an injected document issue); it says nothing about real review rates.

## LangSmith

The same three versions were run as LangSmith experiments on the dataset `keiri-eval-300-v1` (300 synthetic test invoices, examples carry the expected decision and the gold fields; `scripts/langsmith_experiments.py`). Each invoice is one root trace, 900 in total, with a span per node. Per-invoice evaluators: field accuracy, extraction exact, decision correct, unsafe auto-approval, approved-though-review-expected, steps; summary evaluators: the rates above with Clopper-Pearson intervals. Experiment names and links: [`langsmith_experiments.md`](langsmith_experiments.md) (a LangSmith login with access to the workspace is needed).

`scripts/langsmith_check.py` compares each experiment's stored decisions with the offline run, invoice by invoice: **0 of 300 differ in all three versions**, and the unsafe-approval counts are identical (51, 12, 6). Two things were learned on the way, both on the first attempt at these experiments:

- **A shared registry connection returned wrong answers under concurrency.** With two worker threads, the first v2 experiment sent 6 invoices to review as `registry:not_found` for numbers that exist, and one v3 run raised `sqlite3.InterfaceError`. The cause is one SQLite connection shared by several threads (the Invoice-Check JP `Registry`). It is wrapped in a lock (`keiriagent/registry.py`), a regression test runs 8 threads over the full registry, and the affected experiments were deleted and re-run. The offline numbers are unaffected (single-threaded).
- **LangSmith's aggregate feedback lags and can double count.** Read right after a run, the per-experiment feedback summed to 302 runs for a 300-invoice experiment, with feedback on only 286 distinct runs. The consistency check therefore reads each run's stored outputs, not the aggregates.

Trace usage: one root trace per invoice and per resume. Disabling evaluator tracing (`disable_evaluator_tracing`) kept it at exactly 300 per experiment. All experiments, trials and re-runs together used about 1,500 root traces.

## What this does not show

- It does not show how any of this behaves on real invoices, real purchase orders or the real registry.
- The extractor's errors and the PO scenarios are independent by construction; real PO problems correlate with document problems.
- One extractor, one training run, one PO seed, one sample of 300: intervals reflect sampling of invoices only. With 151 approvals, "6 unsafe" has a 95% interval of 1.5% to 8.4%.
- The zero-or-near-zero cells (v3 on hold-out: 1 of 200) have upper bounds of 2.8% and 1.8%; they are not "no risk".
- It does not measure a reviewer. A run routed to review is not counted as right or wrong.
- Not an accounting product; no tax advice.

## Deviations from the pre-registration

None to the pre-registered analysis. The post-hoc section above is additional and labelled as such; the pre-registered numbers are unchanged.
