# Pre-registration: what Keiri-Agent will be measured on, written before the test sample is scored

Written 2026-10-06, before any graph version was run on the evaluation sample. The git history timestamps this file; the results report must quote
this commit and say where it deviates. Everything below is about **synthetic** invoices and **synthetic** purchase orders.

## What was and was not looked at before this was written

- **Looked at:** the validation split (150 of its 300 invoices have cached model predictions): the three graph versions were run on it with the model's
  stored extractions, to check that the rules behave sensibly (nothing was tuned afterwards). All rule development happened on this split and on the fixtures.
- **Looked at, with no model output:** the gold labels of the 600 test invoices, in an oracle test (a *perfect* extraction pushed through the full graph
  must reproduce the expected decision for every invoice). It passed on the first run; nothing was changed after seeing it.
- **Not looked at:** the model's test-split predictions as seen by any graph version, and every score derived from them.

## Inputs (pinned)

| Input | Pin |
|---|---|
| Invoices and gold | Invoice-Check JP `gold_test.jsonl`, sha256 `d3c5f9f3…02b1`; 300 invoices sampled with `random.Random(0)` from the sorted 600 ids, frozen in `data/eval300_ids.json` |
| Extractions | `invoice-check-jp/results/preds/qlora_test.jsonl` (QLoRA Qwen2.5-VL-3B), sha256 `ad7b335e…8715`, replayed, never regenerated |
| Registry | the dataset's synthetic registry `registry_synthetic.jsonl`, sha256 `b17134bc…2e12` (never the real NTA data) |
| Verification code | `invoicecheck` at commit `ef45007` |
| Purchase orders and ledger | `po_synth.build_cases(gold, seed=0)` over all 600 test invoices: one PO per invoice (so each supplier has many open POs and the matcher must pick the right one) |

The 300-invoice sample has 33 invoices with an injected document issue and 69 vertical-layout invoices.

## Versions under test

| Version | Stages after ingest and extract | Decision rule |
|---|---|---|
| v1_extract_only | decide, post | trust the extraction (review only if nothing parsed) |
| v2_verify | + verify (schema, check digit, registry, issuer name, tax arithmetic) | review if any check fails |
| v3_verify_po | + duplicate check and PO matching | reject a duplicate; review if a check fails or the PO is missing or disagrees |

Frozen settings: PO amount tolerance 0 yen; PO scenario mix `matched 0.70, no_po 0.08, line_mismatch 0.08, buyer_mismatch 0.06, duplicate 0.08` (duplicates only for invoices without a document issue).

## Metrics (computed per version on the 300 invoices; 95% Clopper-Pearson intervals for rates)

**Primary**
1. **Unsafe auto-approval rate:** share of the 300 that were auto-approved although at least one extracted field is wrong (any field: `invoicecheck.extraction.score(...)["exact"]` is false). Also reported among the auto-approved only.
2. **Automation rate:** share of the 300 auto-approved (neither sent to a reviewer nor rejected).

**Secondary**
3. Auto-approved although the expected decision is review or reject (injected document issue, PO problem or duplicate): the second kind of unsafe approval.
4. Agreement of the decision with the expected decision.
5. Reviewer workload (share routed to review) and false rejections (rejected although the expected decision is not reject).
6. Steps (nodes executed) and wall-clock time per invoice. Token cost is zero by construction (extractions are replayed; no language model is called in the graph).
7. Which fields were wrong among the unsafe approvals, to see which stage can and cannot catch them.

**Paired comparisons:** v2 against v1 and v3 against v2 on metrics 1 and 3, by invoice, with an exact McNemar test on the discordant pairs.

**Secondary robustness run, reported separately:** the same three versions on the 200 hold-out invoices (unseen layouts; the extractor is much weaker there, 51.5% exact), PO world built the same way.

## Hypotheses, stated in advance

- **H1.** v1 approves everything it can parse, so its unsafe rate equals the share of wrong extractions (about 17% on test, from the Invoice-Check JP report).
- **H2.** v2 cuts that sharply but not to zero: errors in fields no check covers (invoice number, issue date, recipient, item text) can still pass. Invoice-Check JP measured 4.6% of approved invoices wrong in uncovered fields.
- **H3.** v3 lowers the residual only through the fields a PO can see (recipient, item text, totals), not through invoice number or issue date. If v3 shows no reduction in metric 1 over v2, that is reported as a null.
- **H4.** v3's automation rate is lower than v2's: PO problems and duplicates are routed away. That is the price of the extra checks, not a defect.
- Reaching 0 unsafe approvals on this sample proves little by itself: with about 150 to 250 approvals the 95% upper bound is still about 1.5% to 2%. It will be reported as an upper bound, not as "zero".

## Out of scope and known limits

- Purchase orders and ledger entries are generated from the true documents with a fixed scenario mix; real PO data differs. The numbers say how the graph behaves in this synthetic world.
- The extractor's errors and the PO scenarios are independent by construction.
- A reviewer is not simulated for correctness: an oracle reviewer would make every posted invoice right by definition. Reviewer cost appears only as workload.
- One extractor, one training run, one PO seed, one sample of 300. Intervals reflect sampling of invoices, not extractor or PO-world variance.
- This is not an accounting product and gives no tax advice.

## Deviations

None. The sample was scored once (2026-10-06) with the harness committed in `035298a`; results are in `results/REPORT.md`, which adds one clearly labelled post-hoc analysis and changes none of the pre-registered numbers.
