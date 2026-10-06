"""Loaders for the Invoice-Check JP data and the frozen evaluation set."""
import json
from pathlib import Path

from invoicecheck.registry import Record, Registry

from .ledger import InMemoryLedger
from .po import PoStore


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_synthetic_registry(path):
    return Registry.from_records([Record(**r) for r in read_jsonl(path)])


def stores_from_cases(cases):
    """(PoStore, ledger seed rows) for a list of cases; build a fresh InMemoryLedger from the seed for every run."""
    orders = [po for c in cases for po in c["orders"]]
    seed = [row for c in cases for row in c["ledger_seed"]]
    return PoStore(orders), seed


def fresh_ledger(seed_rows):
    return InMemoryLedger(seed_rows)
