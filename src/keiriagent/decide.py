"""Graph versions and the decision rule. A plain function of its inputs: no framework, no model.

Three versions are compared in the evaluation; each adds one stage to the one before:
  v1_extract_only   ingest, extract, decide, post          (the extraction is trusted, nothing is checked)
  v2_verify         + the Invoice-Check JP verification    (check digit, registry, issuer name, tax arithmetic)
  v3_verify_po      + duplicate check and PO matching      (a supplier PO must exist and agree; an already posted invoice is rejected)

The rule fails closed: if a stage that the version enables produced no result, the invoice goes to review.
"""
from dataclasses import dataclass

from .po import MATCHED
from .state import AUTO_APPROVE, HUMAN_REVIEW, REJECT


@dataclass(frozen=True)
class GraphConfig:
    name: str
    verify: bool
    check_duplicates: bool
    match_po: bool


VERSIONS = {
    "v1_extract_only": GraphConfig("v1_extract_only", verify=False, check_duplicates=False, match_po=False),
    "v2_verify": GraphConfig("v2_verify", verify=True, check_duplicates=False, match_po=False),
    "v3_verify_po": GraphConfig("v3_verify_po", verify=True, check_duplicates=True, match_po=True),
}


def decide(cfg, extraction, verification, po_match, duplicate_of):
    """Return (decision, reasons). Order: nothing extracted -> review; known duplicate -> reject; any failed enabled check -> review."""
    if not extraction:
        return HUMAN_REVIEW, ["extraction:unparseable"]
    if cfg.check_duplicates and duplicate_of:
        return REJECT, [f"duplicate_of:{duplicate_of}"]
    reasons = []
    if cfg.verify:
        if verification is None:
            reasons.append("verification:missing")
        elif not verification.get("approved"):
            reasons += list(verification.get("reasons") or ["verification:failed"])
    if cfg.match_po:
        if po_match is None:
            reasons.append("po:missing")
        elif po_match.get("status") != MATCHED:
            reasons += list(po_match.get("reasons") or [f"po:{po_match.get('status')}"])
    return (HUMAN_REVIEW if reasons else AUTO_APPROVE), reasons
