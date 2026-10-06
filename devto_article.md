# PO Matching Looked Like It Halved Unsafe Invoice Approvals Until I Checked Why

*A LangGraph agent for Japanese invoices, killed with SIGKILL, pre-registered, and gated in CI. The headline gain from its last check turned out to be mostly routing, not detection.*

---

![Keiri-Agent results](https://raw.githubusercontent.com/raihan-js/keiri-agent/HEAD/images/keiri-agent.png)

> Scope note: everything here is measured on **synthetic invoices**, a **synthetic** registry and **synthetic purchase orders** (fictitious companies, generated from the true documents with a fixed scenario mix). One extractor (the QLoRA model from [Invoice-Check JP](https://github.com/raihan-js/invoice-check-jp), replayed from stored outputs), one purchase-order seed, one sample of 300 invoices. No reviewer is simulated. It says nothing yet about real invoices, real purchase orders or the real registry, and it is not an accounting product or tax advice.

## What I built

[Keiri-Agent](https://github.com/raihan-js/keiri-agent) turns an invoice extractor into a back-office workflow in LangGraph: extract, verify (check digit, registry, issuer name, tax arithmetic), check for duplicates, match a purchase order, then post, pause for a human reviewer with `interrupt()`, or reject. State is in PostgreSQL, so a paused review survives a restart. No language model sits in the decision path.

Three versions of the graph are built from the same nodes, and each adds one stage: **v1** trusts the extraction, **v2** adds the verification, **v3** adds the duplicate check and purchase-order (PO) matching.

## I wrote down how I would judge it first

Before scoring anything, I committed [a pre-registration](https://github.com/raihan-js/keiri-agent/blob/main/docs/PREREGISTRATION.md): the 300 invoices (a seeded sample of the 600-invoice test split), the pinned inputs by hash, the metrics, and four hypotheses. The primary metric is the **unsafe auto-approval rate**: invoices auto-approved although at least one extracted field is wrong.

| 300 synthetic test invoices | v1 trust the extraction | v2 + verification | v3 + duplicates and PO matching |
|---|---|---|---|
| Unsafe auto-approval, of all 300 | 17.0% [12.9, 21.7] | 4.0% [2.1, 6.9] | 2.0% [0.7, 4.3] |
| Automation rate | 100% | 77.3% [72.2, 81.9] | 50.3% [44.5, 56.1] |

Verification does the heavy lifting: 51 unsafe approvals become 12, and none of the 39 that disappeared came back (exact McNemar, 39 vs 0, p = 3.6e-12). What is left sits in fields no check reads: issue date (6), invoice number (5) and one item line. That matched my prediction.

## The part that looked too good

v3 shows 6 unsafe approvals against v2's 12. Paired, that is 6 vs 0 discordant invoices, p = 0.031. It would be easy to write "PO matching halves the residual".

Then I asked why each of the 6 invoices stopped being approved:

- **2** were true duplicates, rejected correctly. Their wrong field was the issue date, which the duplicate check does not read.
- **3** sat in scenarios where the synthetic PO world disagreed with the truth (no PO, wrong buyer, line mismatch) and were routed to review by that, again with a wrong date or invoice number the PO check does not read.
- **1** had a misread item line, and the PO check caught it.

Five of six were routed away by the scenario, not detected. Restricting to invoices whose PO world agrees with the truth removes that effect: v2 approved 151 invoices with 6 wrong, v3 approved 150 with 5 wrong. The PO check stopped **one** wrong extraction and cost 27 points of automation. The p = 0.031 would not survive a Bonferroni correction over my four pre-registered paired tests either (threshold 0.0125). I reported the pre-registered numbers as they came out, and added this analysis as a clearly labelled post-hoc section.

The same slice on 200 hold-out invoices (layouts the extractor never saw, 51.5% exact) tells the other half: v2 approved 75 with 12 wrong, v3 approved 64 with 1 wrong. The PO check stopped 11 invoices and **all 11** were wrong extractions (item text, the field a PO can see). So PO matching works when the extractor's mistakes are in fields a PO can see, and adds almost nothing when they are not. That precision is flattering: my POs are built from the true item lines, and real free-text descriptions would raise far more false alarms.

## What killing the process taught me

State is only useful if it survives. The restart tests run the graph in a subprocess against a real PostgreSQL, kill it with SIGKILL, and resume in a new process, at three moments: while paused for review, inside a node, and right after the ledger insert committed but before the checkpoint was written (the moment that could post twice; posting is `INSERT ... ON CONFLICT DO NOTHING`, so it does not).

- **The default durability mode lost the last step.** LangGraph writes a step's checkpoint in the background by default. Killing a worker inside a node and counting whether the previous step's checkpoint survived: `durability="sync"` 10 of 10, `async` (the default) 0 of 10, `exit` 0 of 10. One setup (a node blocking inside a synchronous call, sync `PostgresSaver`), not a law, but enough to not trust the default for a workflow that must not lose a step.
- **A bad resume answer poisoned the checkpoint.** In LangGraph 1.2.13, a node that raises after `interrupt()` leaves the failed resume value stored; the next `Command(resume=...)` with a corrected answer receives the old bad one again. The review node now never raises on a bad answer: it asks again with the error attached.
- **A shared SQLite connection returned wrong answers under threads.** In the first LangSmith experiment (two worker threads), 6 invoices went to review as `registry:not_found` for numbers that exist, and another run raised `sqlite3.InterfaceError`. A wrong value is worse than an exception. The registry is now behind a lock with a regression test, and the affected experiments were re-run.
- **LangSmith's aggregate feedback lags.** Read right after a run, it summed to 302 results for a 300-invoice experiment, with feedback on only 286 distinct runs. The consistency check compares each run's stored outputs with the offline run instead: 0 of 300 decisions differ in all three versions.

## A CI gate that counts flips

Because extractions are cached and the graph is deterministic, a pull request can be checked exactly, invoice by invoice, the way [FlipGate](https://github.com/raihan-js/flipgate) counts per-item flips. The gate fails if an invoice that was not an unsafe approval in the committed baseline is one now, or if automation drops by more than 5 points (so routing everything to review cannot satisfy it). It returns INVALID if the pinned inputs changed. Pointing it at a graph without the PO and duplicate stages:

```
## Keiri-Agent gate: FAIL
- 6 invoice(s) newly auto-approved with a wrong field
- 80 invoice(s) newly auto-approved although review or reject was expected
- Newly unsafe (wrong field): inv_003336, inv_003375, inv_003397, inv_003534, inv_003797, inv_003857
```

Those are exactly the six invoices from the analysis above. The GitHub Action also runs the 73 tests, including the SIGKILL ones, against a Postgres service.

## What this does not show

- Nothing about real invoices, purchase orders or the real registry. The extractor's errors and the PO scenarios are independent by construction; real PO problems correlate with document problems.
- One extractor, one PO seed, one sample: with 151 approvals, "6 unsafe" has a 95% interval of 1.5% to 8.4%.
- No reviewer is simulated: a run routed to review is not counted right or wrong. The 43% review workload is set mostly by my scenario mix and says nothing about real review rates.

Code, tests, the pre-registration, the report and the CI workflow: [github.com/raihan-js/keiri-agent](https://github.com/raihan-js/keiri-agent).
