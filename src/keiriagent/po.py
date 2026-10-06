"""Purchase orders and the matching rule. Plain functions: no framework, no model, no randomness.

An invoice matches a purchase order when the supplier has an open PO, the buyer on the PO is the invoice's recipient, the invoice lines
are the PO lines (same description, quantity and unit price) and the totals agree. Each failed condition is a reason; the status
is the first one in a fixed order. The matcher reads extracted fields, so a misread recipient or line shows up here as a mismatch:
that is the point (recipient and item text have no check in the verification layer).
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from invoicecheck.checkdigit import normalize_registration_number
from invoicecheck.normalize import normalize_name, strip_company_form

MATCHED = "matched"
NO_PO = "no_po"
BUYER_MISMATCH = "buyer_mismatch"
TOTAL_MISMATCH = "total_mismatch"
LINE_MISMATCH = "line_mismatch"
STATUS_ORDER = (NO_PO, BUYER_MISMATCH, TOTAL_MISMATCH, LINE_MISMATCH)


@dataclass(frozen=True)
class POLine:
    description: str
    quantity: int
    unit_price: int


@dataclass(frozen=True)
class PurchaseOrder:
    po_id: str
    supplier_reg_no: str                # T + 13 digits
    buyer_name: str
    lines: tuple
    total: int                          # yen, the amount the invoice is expected to total


@dataclass
class POMatch:
    status: str
    po_id: str = None
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return {"status": self.status, "po_id": self.po_id, "reasons": list(self.reasons)}


class PoStore:
    """Open purchase orders indexed by supplier registration number."""

    def __init__(self, orders=()):
        self._by_supplier = defaultdict(list)
        for po in orders:
            self._by_supplier[po.supplier_reg_no].append(po)

    def for_supplier(self, reg_no):
        return list(self._by_supplier.get(reg_no, []))

    def __len__(self):
        return sum(len(v) for v in self._by_supplier.values())


def _same_party(a, b):
    na, nb = normalize_name(a or ""), normalize_name(b or "")
    if na and na == nb:
        return True
    ca, cb = strip_company_form(a or ""), strip_company_form(b or "")
    return bool(ca) and ca == cb


def _invoice_lines(extraction):
    out = Counter()
    for it in extraction.get("items") or []:
        if isinstance(it, dict):
            out[(normalize_name(it.get("description", "")), it.get("quantity"), it.get("unit_price"))] += 1
    return out


def _po_lines(po):
    return Counter((normalize_name(l.description), l.quantity, l.unit_price) for l in po.lines)


def match_po(extraction, store, tolerance_yen=0):
    """Match an extracted invoice to the closest open PO of its supplier. `tolerance_yen` is 0 by default: the PO is the agreed amount."""
    reg = normalize_registration_number(extraction.get("registration_number"))
    candidates = store.for_supplier(reg) if reg else []
    if not candidates:
        return POMatch(NO_PO, None, [f"po:{NO_PO}"])
    grand = extraction.get("grand_total")
    grand = grand if isinstance(grand, int) and not isinstance(grand, bool) else None
    best = min(candidates, key=lambda p: (abs(p.total - grand) if grand is not None else 0, p.po_id))
    reasons = {}
    if not _same_party(extraction.get("recipient_name"), best.buyer_name):
        reasons[BUYER_MISMATCH] = True
    if grand is None or abs(best.total - grand) > tolerance_yen:
        reasons[TOTAL_MISMATCH] = True
    if _invoice_lines(extraction) != _po_lines(best):
        reasons[LINE_MISMATCH] = True
    if not reasons:
        return POMatch(MATCHED, best.po_id, [])
    status = next(s for s in STATUS_ORDER if s in reasons)
    return POMatch(status, best.po_id, [f"po:{s}" for s in STATUS_ORDER if s in reasons])
