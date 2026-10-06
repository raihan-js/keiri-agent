# Keiri-Agent

A LangGraph back-office agent for Japanese qualified invoices (適格請求書). It takes the extraction of [Invoice-Check JP](https://github.com/raihan-js/invoice-check-jp), verifies it, matches a purchase order, and either posts the invoice, sends it to a human reviewer, or rejects it, with an audit trail and a state that survives a restart.

> **Status: milestone 1 of 4 (graph design).** No evaluation results yet; the evaluation protocol is fixed in advance in [`docs/PREREGISTRATION.md`](docs/PREREGISTRATION.md). Everything here runs on **synthetic** invoices, a **synthetic** registry and **synthetic** purchase orders. This is not an accounting product and gives no tax advice.

## The graph

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	ingest(ingest)
	extract(extract)
	verify(verify)
	check_duplicate(check_duplicate)
	match_po(match_po)
	decide(decide)
	review(review)
	post(post)
	reject(reject)
	__end__([<p>__end__</p>]):::last
	__start__ --> ingest;
	check_duplicate --> match_po;
	decide -.-> post;
	decide -.-> reject;
	decide -.-> review;
	extract --> verify;
	ingest --> extract;
	match_po --> decide;
	review -.-> post;
	review -.-> reject;
	verify --> check_duplicate;
	post --> __end__;
	reject --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Generated from the compiled graph (`scripts/render_graphs.py`). Three versions are built from the same nodes and compared on the same invoices; each adds one stage:

| Version | Stages | What it trusts |
|---|---|---|
| `v1_extract_only` | ingest, extract, decide, post | the extraction |
| `v2_verify` | + verify (check digit, registry, issuer name, tax arithmetic) | the extraction, if the checks pass |
| `v3_verify_po` | + duplicate check, PO matching | the extraction, if the checks pass **and** a PO agrees; an already posted invoice is rejected |

- **Typed state** (`state.py`): one `InvoiceState`; the only reducer is the append-only `audit` list, so every node adds its own entries and the list is the trail of what the agent did and why.
- **Plain functions, thin framework** (`po.py`, `decide.py`, `review.py`, `ledger.py`, `po_synth.py`): all logic is testable without LangGraph; `graph.py` wires nodes that read state, call a function and write a partial update. No language model sits in the decision path, and nothing is scored by a model.
- **Fails closed:** if a stage a version enables produced nothing, the invoice goes to review.
- **Human review is an `interrupt()`** at the `review` node: the run pauses at a checkpoint and resumes with `Command(resume=...)` on the same thread id. Posting is idempotent on the invoice id, so a re-run after a crash or resume cannot post twice.
- **Reject is narrow:** only a duplicate (same supplier and invoice number already in the ledger) is rejected automatically; everything else that fails goes to a person, because a failed check cannot tell a bad document from a misread one.

## Things that went wrong while building it

- **A bad resume answer poisons the checkpoint.** In LangGraph 1.2.13, a node that raises after `interrupt()` (for example when validating the reviewer's answer) leaves the failed resume value stored; the next `Command(resume=...)` with a *corrected* answer receives the old bad one again, so the invoice can never be resumed. The `review` node therefore never raises on a bad answer: it asks again with the error attached (`tests/test_graph.py::test_a_malformed_reviewer_answer_asks_again_and_can_still_be_resumed`).
- **The oracle test.** With a perfect extraction the full graph must reproduce the expected decision for all 300 validation and all 600 test invoices (`tests/test_oracle.py`). It passed on the first run, so in these 900 cases no purchase order was matched to the wrong invoice and every injected document issue was caught by a check. Disagreements seen later with the real extractor are extraction errors that the checks route to review.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api]"
.venv/bin/python scripts/fetch_data.py        # gold labels + synthetic registry (public dataset, CC-BY-4.0)
.venv/bin/python -m pytest tests -q           # 48 tests
```

## Roadmap

1. Graph design: done (this commit).
2. Durability and human approval: PostgresSaver in Docker, a review UI, a test that kills the process mid-run and resumes, time-travel replay.
3. LangSmith evaluation: 300-invoice dataset, evaluators for field accuracy, decision correctness and unsafe auto-approval, experiments over the three versions.
4. CI gate and release: a GitHub Action that fails a pull request if unsafe auto-approvals rise.

Licence: MIT for the code. Data: Invoice-Check JP (CC-BY-4.0, synthetic). The extractor adapter used elsewhere is non-commercial (Qwen Research License).
