# AGENTS.md — keiri-agent

Wave-two project 2 (ideas-v2.json id `keiri-agent`), builds on Invoice-Check JP. Portfolio for Raihan Sikder (Tokyo ML-platform / LLMOps roles; see `../PROJECTS.md`, `../AGENTS.md`).

## What it is
A LangGraph back-office agent for Japanese qualified invoices: ingest, extract (cached or live QLoRA extractor), verify (Invoice-Check JP checks), duplicate check, PO matching, decide (auto-approve / human review / reject), post. Review pauses with `interrupt()` and resumes from the checkpoint. Evaluated in LangSmith on 300 synthetic test invoices over three graph versions; a GitHub Action will fail a PR if unsafe auto-approvals rise.

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
.venv/bin/python -m pytest tests -q             # unit, node, graph and oracle tests
.venv/bin/python scripts/render_graphs.py       # docs/graphs/*.mmd from the compiled graphs
```

## Status
- M1 graph design: DONE 2026-10-06 (state, nodes, three versions, 48 tests incl. an oracle test, diagrams, pre-registration).
- M2 durability and human approval (PostgresSaver in Docker, review UI, kill-and-resume test, time travel): next.
- M3 LangSmith evaluation; M4 CI gate and release: not started.
