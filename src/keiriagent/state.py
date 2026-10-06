"""The typed state that flows through the graph, and the vocabulary of decisions.

Every node returns a partial update. `audit` is the only field with a reducer (append), so each node adds its own entries and the
list is the complete, ordered trail of what the agent did and why. Nothing here imports LangGraph machinery beyond typing.
"""
import operator
from typing import Annotated, Optional, TypedDict

AUTO_APPROVE = "auto_approve"
HUMAN_REVIEW = "human_review"
REJECT = "reject"
DECISIONS = (AUTO_APPROVE, HUMAN_REVIEW, REJECT)

POSTED = "posted"
REJECTED = "rejected"
PENDING_REVIEW = "pending_review"

REVIEW_ACTIONS = ("approve", "correct", "reject")


class InvoiceState(TypedDict, total=False):
    invoice_id: str                     # also the thread id and the posting idempotency key
    document: str                       # where the document lives (image path or id); only a live extractor reads it
    extraction: Optional[dict]          # the extractor's fields (Invoice-Check JP schema); None if nothing parsed
    verification: Optional[dict]        # {"approved": bool, "reasons": [...], "detail": {...}} from invoicecheck.verify
    po_match: Optional[dict]            # {"status": ..., "po_id": ..., "reasons": [...]} from keiriagent.po.match_po
    duplicate_of: Optional[str]         # id of an already posted invoice with the same supplier and invoice number
    decision: Optional[str]             # one of DECISIONS, set by the decide node
    decision_reasons: list              # why the decision is not auto_approve (check codes)
    review: Optional[dict]              # the reviewer's answer after the graph resumes: action, reviewer, corrections, note
    outcome: Optional[str]              # POSTED, REJECTED or PENDING_REVIEW
    ledger_id: Optional[str]
    audit: Annotated[list, operator.add]


def audit_entry(node, event, **fields):
    """One audit line. Deterministic content only (no clock), so replays and tests compare equal; the clock lives in the ledger."""
    return {"node": node, "event": event, **fields}
