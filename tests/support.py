"""Shared test helpers: the fixture data, a PO builder and a dependency builder. Importable from tests and from the subprocess worker."""
from pathlib import Path

from invoicecheck.extraction import gold_to_target

from keiriagent.data import load_synthetic_registry, read_jsonl
from keiriagent.extractors import StaticExtractor
from keiriagent.graph import Deps
from keiriagent.po import POLine, PoStore, PurchaseOrder

FIX = Path(__file__).parent / "fixtures"


def load_gold():
    return {g["invoice_id"]: g for g in read_jsonl(FIX / "gold_sample.jsonl")}


def load_registry():
    return load_synthetic_registry(FIX / "registry_sample.jsonl")


def po_for(g, **over):
    """A PO that agrees with the gold invoice, with optional overrides."""
    args = dict(po_id=f"PO-{g['invoice_id']}", supplier_reg_no=g["true_issuer_registration_number"], buyer_name=g["recipient"]["name"],
                lines=tuple(POLine(i["description"], i["quantity"], i["unit_price"]) for i in g["items"]), total=g["grand_total"])
    args.update(over)
    return PurchaseOrder(**args)


def build_deps(ledger, extractor=None):
    gold = load_gold()
    ext = extractor or StaticExtractor({k: gold_to_target(v) for k, v in gold.items()})
    return Deps(ext, load_registry(), PoStore([po_for(g) for g in gold.values()]), ledger)
