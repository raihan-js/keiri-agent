"""Synthetic purchase orders, ledger seeds and expected decisions, built from the gold invoice and never from an extraction.

The purchase orders are SYNTHETIC: generated here from the true content of each synthetic invoice, then perturbed in a known way. They say
nothing about how real purchase orders look. Each invoice gets one scenario:

  matched          the PO agrees with the invoice
  no_po            the supplier has no PO for this invoice
  line_mismatch    the PO differs on one line (lower unit price, lower quantity, or a line the PO does not have); the total follows
  buyer_mismatch   the PO is for a different buyer than the invoice's recipient
  duplicate        the invoice is already in the ledger (same supplier and invoice number), as an earlier posting

The expected decision is a function of the true document only:
  duplicate -> reject; else any injected document issue (Invoice-Check JP) or any PO problem -> human_review; else auto_approve.
Duplicates are assigned only to invoices without a document issue, so the expected decision is never ambiguous.
"""
import random

from .po import POLine, PurchaseOrder
from .state import AUTO_APPROVE, HUMAN_REVIEW, REJECT

SCENARIOS = (("matched", 0.70), ("no_po", 0.08), ("line_mismatch", 0.08), ("buyer_mismatch", 0.06), ("duplicate", 0.08))


def expected_decision(has_document_issue, scenario):
    if scenario == "duplicate":
        return REJECT
    return HUMAN_REVIEW if (has_document_issue or scenario != "matched") else AUTO_APPROVE


def _pick_scenario(rng, allow_duplicate):
    pool = [(s, w) for s, w in SCENARIOS if allow_duplicate or s != "duplicate"]
    r, acc = rng.random() * sum(w for _, w in pool), 0.0
    for s, w in pool:
        acc += w
        if r <= acc:
            return s
    return pool[-1][0]


def _mutate_lines(rng, lines, total):
    """A line-level difference between invoice and PO. Returns (po_lines, po_total) with po_total != total."""
    variants = ["price", "quantity"] + (["extra_line"] if len(lines) >= 2 else [])
    kind = rng.choice(variants)
    i = rng.randrange(len(lines))
    l = lines[i]
    if kind == "price":
        lower = max(1, min(l.unit_price - 1, round(l.unit_price * rng.uniform(0.7, 0.95)))) if l.unit_price > 1 else 0
        if l.unit_price <= 1:                      # cannot lower a 1-yen price: lower the quantity instead
            kind = "quantity"
        else:
            new = lines[:i] + (POLine(l.description, l.quantity, lower),) + lines[i + 1:]
            return new, total - (l.unit_price - lower) * l.quantity
    if kind == "quantity":
        q = max(1, l.quantity - rng.randint(1, 2)) if l.quantity > 1 else l.quantity + rng.randint(1, 2)
        new = lines[:i] + (POLine(l.description, q, l.unit_price),) + lines[i + 1:]
        return new, total - (l.quantity - q) * l.unit_price
    return lines[:i] + lines[i + 1:], total - l.quantity * l.unit_price           # extra_line: PO lacks this line


def build_case(gold, buyers, seed=0):
    """One invoice's purchase orders, ledger seed and expected decision. Deterministic in (seed, invoice id)."""
    rng = random.Random(f"{seed}:{gold['invoice_id']}")
    has_issue = bool(gold["document_issues"])
    scenario = _pick_scenario(rng, allow_duplicate=not has_issue)
    supplier = gold["true_issuer_registration_number"]
    lines = tuple(POLine(it["description"], it["quantity"], it["unit_price"]) for it in gold["items"])
    total, buyer = gold["grand_total"], gold["recipient"]["name"]
    orders, ledger_seed = [], []
    po_id = f"PO-{gold['invoice_id']}"
    if scenario in ("matched", "duplicate"):
        orders = [PurchaseOrder(po_id, supplier, buyer, lines, total)]
    elif scenario == "line_mismatch":
        po_lines, po_total = _mutate_lines(rng, lines, total)
        orders = [PurchaseOrder(po_id, supplier, buyer, po_lines, po_total)]
    elif scenario == "buyer_mismatch":
        other = rng.choice([b for b in buyers if b != buyer])
        orders = [PurchaseOrder(po_id, supplier, other, lines, total)]
    if scenario == "duplicate":
        ledger_seed = [{"invoice_id": f"prev-{gold['invoice_id']}", "supplier_reg_no": supplier, "invoice_number": gold["invoice_number"],
                        "grand_total": total, "approved_by": "auto", "override_reasons": []}]
    return {"invoice_id": gold["invoice_id"], "scenario": scenario, "has_document_issue": has_issue, "orders": orders,
            "ledger_seed": ledger_seed, "expected_decision": expected_decision(has_issue, scenario)}


def build_cases(gold_rows, seed=0):
    buyers = sorted({g["recipient"]["name"] for g in gold_rows})
    return [build_case(g, buyers, seed) for g in gold_rows]
