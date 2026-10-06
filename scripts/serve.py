#!/usr/bin/env python3
"""Serve the review API and page over the frozen evaluation world: the pre-registered purchase orders and ledger seed, the cached QLoRA
extractions, the synthetic registry, PostgreSQL. A demo: starting runs here is NOT the evaluation (that is scripts/run_eval.py).

  .venv/bin/python scripts/serve.py [--version v3_verify_po] [--port 8800]
LangSmith tracing turns on when LANGSMITH_TRACING=true; the key is read from ~/.config/langsmith/key, never from the command line.
"""
import argparse
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from keiriagent.data import load_synthetic_registry, read_jsonl, stores_from_cases  # noqa: E402
from keiriagent.extractors import CachedExtractor  # noqa: E402
from keiriagent.graph import Deps  # noqa: E402
from keiriagent.pg import PostgresLedger, default_dsn  # noqa: E402
from keiriagent.po_synth import build_cases  # noqa: E402
from keiriagent.service import create_app  # noqa: E402


def load_langsmith_key():
    key = Path.home() / ".config/langsmith/key"
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and not os.environ.get("LANGSMITH_API_KEY") and key.exists():
        os.environ["LANGSMITH_API_KEY"] = key.read_text().strip()


def build(version="v3_verify_po"):
    data = ROOT / "data/invoice-check-jp"
    gold = read_jsonl(data / "gold_test.jsonl")
    cases = build_cases(gold, seed=0)                       # the pre-registered PO world over all 600 test invoices
    store, seed = stores_from_cases(cases)
    deps = Deps(CachedExtractor(ROOT.parent / "invoice-check-jp/results/preds/qlora_test.jsonl"),
                load_synthetic_registry(data / "registry_synthetic.jsonl"), store, PostgresLedger(default_dsn(), seed=seed))
    return create_app(deps, default_dsn(), version)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v3_verify_po")
    ap.add_argument("--port", type=int, default=8800)
    a = ap.parse_args()
    load_langsmith_key()
    uvicorn.run(build(a.version), host="127.0.0.1", port=a.port, log_level="warning")
