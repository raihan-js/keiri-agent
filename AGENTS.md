# AGENTS.md — keiri-agent

Wave-two project 2 (ideas-v2.json id `keiri-agent`), builds on Invoice-Check JP. Portfolio for Raihan Sikder (Tokyo ML-platform / LLMOps roles; see `../PROJECTS.md`, `../AGENTS.md`).

## What it is
A LangGraph back-office agent for Japanese qualified invoices: ingest, extract (cached or live QLoRA extractor), verify (Invoice-Check JP checks), duplicate check, PO matching, decide (auto-approve / human review / reject), post. Review pauses with `interrupt()` and resumes from the checkpoint. Evaluated offline and in LangSmith on 300 synthetic test invoices over three graph versions; a GitHub Action will fail a PR if unsafe auto-approvals rise.

## Rules
- Core logic lives in plain modules (`po.py`, `decide.py`, `review.py`, `ledger.py`, `po_synth.py`); `graph.py` is a thin LangGraph layer. Pin LangGraph / LangSmith versions (pyproject).
- `docs/PREREGISTRATION.md` is frozen before the test sample is scored: never tune rules, tolerances or the PO scenario mix on the test sample; list any deviation there, keep the original numbers.
- No LLM anywhere in the decision path; no LLM-as-judge. All data is synthetic (fictitious companies, synthetic registry and POs); never present it as an accounting product or tax advice.
- Claims follow `../../noeon-prep/content/interview/09-never-say.md`: scope every number, report nulls as nulls.
- LangSmith key: `~/.config/langsmith/key` (chmod 600). Never print it, commit it, or put it in a URL or log. `LANGSMITH_API_KEY=$(cat ~/.config/langsmith/key)` at run time.
- Workflow: one project at a time; ask before `gh repo create` / pushing / publishing; clear heavy content after shipping (`../pipeline/clear_finished_projects.py`, archive first).

## Commands
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api]"
.venv/bin/python scripts/fetch_data.py          # gold + synthetic registry from the public HF dataset
.venv/bin/python -m pytest tests -q             # unit, node, graph, oracle, Postgres, restart and service tests
docker start keiri-pg                           # (or docker compose up -d) PostgreSQL for the Postgres tests; DSN in .env
.venv/bin/python scripts/render_graphs.py       # docs/graphs/*.mmd from the compiled graphs
```

## Status
- M1 graph design: DONE 2026-10-06 (state, nodes, three versions, 48 tests incl. an oracle test, diagrams, pre-registration).
- M2 durability and human approval: DONE 2026-10-06 (PostgreSQL container `keiri-pg` on 127.0.0.1:55432, `pg.py`, `ops.py`, `service.py`, review page, 3 SIGKILL tests, durability A/B: sync 10/10 vs async 0/10, replay in a separate thread; 60 tests). Always pass durability="sync".
- M3 LangSmith evaluation: DONE 2026-10-06 (pre-registered run: test300 + holdout200, `results/REPORT.md` with a labelled post-hoc analysis; dataset `keiri-eval-300-v1`; experiments `keiri-v1_extract_only-4bca9831`, `keiri-v2_verify-377590c1`, `keiri-v3_verify_po-d32192ad` match the offline run 300/300; 66 tests). Registry wrapped in a lock (sqlite race gave silent wrong answers under threads).
- M4 CI gate and release (next): GitHub Action that fails a PR if unsafe auto-approvals rise (run offline from the frozen files; upload to LangSmith only if a key secret exists), repo, screenshots of LangSmith traces/experiments, write-up, portfolio/resume. LangSmith note: every invoke and every resume is its own root trace; `list_runs` is deprecated (use `client.runs.query`); check the free-tier trace limit before experiments.
