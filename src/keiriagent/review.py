"""What a reviewer may answer when the graph pauses, and how corrections are applied. Plain functions."""
import copy

from .state import REVIEW_ACTIONS

CORRECTABLE = ("issuer_name", "registration_number", "issue_date", "recipient_name", "invoice_number", "tax_included",
               "items", "totals", "grand_total")


def validate_review(answer):
    """Raise ValueError unless the resume payload is a well-formed reviewer answer; return it unchanged."""
    if not isinstance(answer, dict):
        raise ValueError("review answer must be an object")
    if answer.get("action") not in REVIEW_ACTIONS:
        raise ValueError(f"review action must be one of {REVIEW_ACTIONS}, got {answer.get('action')!r}")
    if not isinstance(answer.get("reviewer"), str) or not answer["reviewer"].strip():
        raise ValueError("review answer needs a reviewer name")
    corrections = answer.get("corrections") or {}
    if answer["action"] == "correct":
        if not corrections:
            raise ValueError("action 'correct' needs a non-empty corrections object")
        unknown = [k for k in corrections if k not in CORRECTABLE]
        if unknown:
            raise ValueError(f"cannot correct unknown fields: {unknown}")
    return answer


def apply_corrections(extraction, corrections):
    """A corrected copy of the extraction: each corrected field is replaced as a whole."""
    out = copy.deepcopy(extraction or {})
    for k, v in (corrections or {}).items():
        out[k] = copy.deepcopy(v)
    return out
