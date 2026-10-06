import os
from pathlib import Path

import pytest

os.environ["LANGSMITH_TRACING"] = "false"          # tests never call out
os.environ.pop("LANGSMITH_API_KEY", None)

from invoicecheck.extraction import gold_to_target

from keiriagent.data import load_synthetic_registry, read_jsonl
from keiriagent.extractors import StaticExtractor
from keiriagent.graph import Deps
from keiriagent.ledger import InMemoryLedger
from keiriagent.po import POLine, PoStore, PurchaseOrder

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def gold():
    return {g["invoice_id"]: g for g in read_jsonl(FIX / "gold_sample.jsonl")}


@pytest.fixture(scope="session")
def registry():
    return load_synthetic_registry(FIX / "registry_sample.jsonl")


def po_for(g, **over):
    """A PO that agrees with the gold invoice, with optional overrides."""
    args = dict(po_id=f"PO-{g['invoice_id']}", supplier_reg_no=g["true_issuer_registration_number"], buyer_name=g["recipient"]["name"],
                lines=tuple(POLine(i["description"], i["quantity"], i["unit_price"]) for i in g["items"]), total=g["grand_total"])
    args.update(over)
    return PurchaseOrder(**args)


@pytest.fixture
def make_deps(gold, registry):
    def _make(extractions=None, orders=(), ledger_seed=()):
        ext = extractions if extractions is not None else {k: gold_to_target(v) for k, v in gold.items()}
        return Deps(StaticExtractor(ext), registry, PoStore(orders), InMemoryLedger(ledger_seed))
    return _make
