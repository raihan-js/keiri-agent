"""The LangGraph layer: a thin wrapper that wires plain functions into a state graph.

  ingest -> extract -> [verify] -> [check_duplicate] -> [match_po] -> decide -+-> post                     -> END
                                                                              +-> review (interrupt) -+-> post / reject
                                                                              +-> reject                       -> END

Stages in brackets exist only in the versions that enable them (see decide.VERSIONS). `review` pauses the run with `interrupt()`; the run
resumes with `Command(resume=<reviewer answer>)` on the same thread id, from the checkpoint, in this process or another. Nodes that run before
the interrupt are re-executed on resume only if they sit in the same step, so `review` does nothing but ask; side effects (posting) are
idempotent on the invoice id. All node logic is in the modules this file imports; nodes here only read state, call them, and write a partial update.
"""
from dataclasses import dataclass
from typing import Any

from invoicecheck.checkdigit import normalize_registration_number
from invoicecheck.verify import verify as verify_invoice
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .decide import VERSIONS, GraphConfig, decide
from .extractors import Extractor
from .ledger import Ledger
from .po import PoStore, match_po
from .registry import LockedRegistry
from .review import apply_corrections, validate_review
from .state import (AUTO_APPROVE, HUMAN_REVIEW, PENDING_REVIEW, POSTED, REJECT, REJECTED, InvoiceState, audit_entry)


@dataclass
class Deps:
    extractor: Extractor
    registry: Any            # invoicecheck.registry.Registry (real snapshot or the synthetic one); wrapped for thread safety
    po_store: PoStore
    ledger: Ledger

    def __post_init__(self):
        if self.registry is not None and not isinstance(self.registry, LockedRegistry):
            self.registry = LockedRegistry(self.registry)


def make_nodes(deps, cfg):
    """The node functions for one version, as a dict. Exposed so each node can be unit-tested with stubbed dependencies."""

    def ingest(state):
        if not state.get("invoice_id"):
            raise ValueError("invoice_id is required")
        return {"audit": [audit_entry("ingest", "received", invoice_id=state["invoice_id"], version=cfg.name)]}

    def extract(state):
        ext = deps.extractor.extract(state["invoice_id"], state.get("document"))
        return {"extraction": ext, "audit": [audit_entry("extract", "parsed" if ext else "unparseable",
                                                         items=len((ext or {}).get("items") or []))]}

    def verify(state):
        ext = state.get("extraction")
        if not ext:
            return {"audit": [audit_entry("verify", "skipped", why="no extraction")]}
        v = verify_invoice(ext, deps.registry)
        result = {"approved": v.approved, "reasons": list(v.reasons), "detail": dict(v.detail)}
        return {"verification": result, "audit": [audit_entry("verify", "passed" if v.approved else "failed", reasons=list(v.reasons))]}

    def check_duplicate(state):
        ext = state.get("extraction")
        if not ext:
            return {"audit": [audit_entry("check_duplicate", "skipped", why="no extraction")]}
        dup = deps.ledger.find_duplicate(ext.get("registration_number"), ext.get("invoice_number"), exclude_key=state["invoice_id"])
        return {"duplicate_of": dup, "audit": [audit_entry("check_duplicate", "duplicate" if dup else "unique", duplicate_of=dup)]}

    def match_po_node(state):
        ext = state.get("extraction")
        if not ext:
            return {"audit": [audit_entry("match_po", "skipped", why="no extraction")]}
        m = match_po(ext, deps.po_store).as_dict()
        return {"po_match": m, "audit": [audit_entry("match_po", m["status"], po_id=m["po_id"], reasons=m["reasons"])]}

    def decide_node(state):
        decision, reasons = decide(cfg, state.get("extraction"), state.get("verification"), state.get("po_match"), state.get("duplicate_of"))
        update = {"decision": decision, "decision_reasons": reasons, "audit": [audit_entry("decide", decision, reasons=reasons)]}
        if decision == HUMAN_REVIEW:
            update["outcome"] = PENDING_REVIEW
        return update

    def review(state):
        payload = {"invoice_id": state["invoice_id"], "extraction": state.get("extraction"), "reasons": state.get("decision_reasons", []),
                   "verification": state.get("verification"), "po_match": state.get("po_match")}
        while True:
            # Never raise on a bad answer: LangGraph stores the failed resume value and replays it on the next resume, so a node that
            # raises after interrupt() can never be resumed with a corrected answer. Ask again, with the error, instead.
            try:
                answer = validate_review(interrupt(payload))
                break
            except ValueError as e:
                payload = {**payload, "error": str(e)}
        update = {"review": answer, "audit": [audit_entry("review", answer["action"], reviewer=answer["reviewer"],
                                                          corrected=sorted((answer.get("corrections") or {}))
                                                          if answer["action"] == "correct" else [])]}
        if answer["action"] == "correct":
            update["extraction"] = apply_corrections(state.get("extraction"), answer["corrections"])
        return update

    def post(state):
        ext = state.get("extraction") or {}
        review_ = state.get("review") or {}
        record = {
            "supplier_reg_no": normalize_registration_number(ext.get("registration_number")), "invoice_number": ext.get("invoice_number"),
            "issue_date": ext.get("issue_date"), "grand_total": ext.get("grand_total"),
            "po_id": (state.get("po_match") or {}).get("po_id"),
            "approved_by": "auto" if state.get("decision") == AUTO_APPROVE else f"human:{review_.get('reviewer', 'unknown')}",
            "override_reasons": list(state.get("decision_reasons") or []) if state.get("decision") != AUTO_APPROVE else [],
            "extraction": ext,
        }
        ledger_id = deps.ledger.post(state["invoice_id"], record)
        return {"outcome": POSTED, "ledger_id": ledger_id, "audit": [audit_entry("post", "posted", ledger_id=ledger_id, approved_by=record["approved_by"])]}

    def reject(state):
        by = "auto" if state.get("decision") == REJECT else f"human:{(state.get('review') or {}).get('reviewer', 'unknown')}"
        return {"outcome": REJECTED, "audit": [audit_entry("reject", "rejected", by=by, reasons=list(state.get("decision_reasons") or []))]}

    return {"ingest": ingest, "extract": extract, "verify": verify, "check_duplicate": check_duplicate, "match_po": match_po_node,
            "decide": decide_node, "review": review, "post": post, "reject": reject}


def route_after_decide(state):
    return {AUTO_APPROVE: "post", HUMAN_REVIEW: "review", REJECT: "reject"}[state["decision"]]


def route_after_review(state):
    return "reject" if state["review"]["action"] == "reject" else "post"


def stages_for(cfg):
    return (["ingest", "extract"] + (["verify"] if cfg.verify else []) + (["check_duplicate"] if cfg.check_duplicates else [])
            + (["match_po"] if cfg.match_po else []) + ["decide"])


def build_graph(deps, version="v3_verify_po", checkpointer=None):
    """Compile the graph for one version. `version` is a key of decide.VERSIONS or a GraphConfig."""
    cfg = version if isinstance(version, GraphConfig) else VERSIONS[version]
    nodes = make_nodes(deps, cfg)
    stages = stages_for(cfg)
    g = StateGraph(InvoiceState)
    for name in stages + ["review", "post", "reject"]:
        g.add_node(name, nodes[name])
    g.add_edge(START, stages[0])
    for a, b in zip(stages, stages[1:]):
        g.add_edge(a, b)
    g.add_conditional_edges("decide", route_after_decide, {"post": "post", "review": "review", "reject": "reject"})
    g.add_conditional_edges("review", route_after_review, {"post": "post", "reject": "reject"})
    g.add_edge("post", END)
    g.add_edge("reject", END)
    return g.compile(checkpointer=checkpointer, name=f"keiri-{cfg.name}")
