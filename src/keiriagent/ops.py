"""Operating the graph: run history, replay from any checkpoint, and the queue of runs waiting for a reviewer.

Replay never touches the live run. It copies the chosen checkpoint's state into a NEW thread and continues from there with a dry-run ledger
(reads the real ledger for the duplicate check, writes only to memory), so replaying a posted invoice cannot post it again and a what-if
(`overrides`) cannot leave a pending review on an invoice that was already posted. LangGraph's native fork on the same thread would do both.
"""
from dataclasses import replace

import psycopg
from langgraph.types import Command  # noqa: F401  (re-exported for callers that resume)

from .graph import Deps, build_graph
from .ledger import InMemoryLedger

DURABILITY = {"durability": "sync"}     # a checkpoint is written before the next step starts; see README, "Things that went wrong"


class DryRunLedger:
    def __init__(self, real):
        self.real, self.mem = real, InMemoryLedger()

    def find_duplicate(self, supplier_reg_no, invoice_number, exclude_key=None):
        return self.mem.find_duplicate(supplier_reg_no, invoice_number, exclude_key) or self.real.find_duplicate(supplier_reg_no, invoice_number, exclude_key)

    def post(self, key, record):
        return self.mem.post(key, record)


def run_config(thread_id, checkpoint_id=None):
    c = {"configurable": {"thread_id": thread_id}}
    if checkpoint_id:
        c["configurable"]["checkpoint_id"] = checkpoint_id
    return c


def history(graph, thread_id):
    """Checkpoints of a run, oldest first: id, step, the node that runs next, and what the state said at that point."""
    out = []
    for s in reversed(list(graph.get_state_history(run_config(thread_id)))):
        v = s.values or {}
        out.append({"checkpoint_id": s.config["configurable"]["checkpoint_id"], "step": (s.metadata or {}).get("step"), "next": list(s.next),
                    "decision": v.get("decision"), "outcome": v.get("outcome"), "audit_events": len(v.get("audit") or [])})
    return out


def _predecessor(graph, node, values):
    incoming = [e for e in graph.get_graph().edges if e.target == node]
    if len(incoming) == 1:
        return incoming[0].source
    for entry in reversed(values.get("audit") or []):               # post / reject are reached from decide or from review: take the one that ran
        if any(e.source == entry["node"] for e in incoming):
            return entry["node"]
    raise ValueError(f"cannot tell how {node} was reached")


def replay(graph, thread_id, checkpoint_id, new_thread_id, overrides=None):
    """Re-run a past run from `checkpoint_id` in `new_thread_id`, optionally with state values replaced first. Returns the graph output.

    `graph` should be compiled with dry-run dependencies (see `dry_run_graph`) and the same checkpointer as the original run."""
    snap = graph.get_state(run_config(thread_id, checkpoint_id))
    if snap.created_at is None:                                      # LangGraph returns an empty snapshot for an id it does not know
        raise ValueError(f"unknown checkpoint {checkpoint_id!r} for {thread_id!r}")
    if not snap.next:
        raise ValueError("this checkpoint is the end of the run; choose an earlier one (the first re-runs everything)")
    values = {**(snap.values or {}), **(overrides or {})}
    if snap.next[0] in ("__start__", "ingest") or not values.get("audit"):
        first = {k: v for k, v in values.items() if k in ("invoice_id", "document")} or {"invoice_id": thread_id}
        return graph.invoke(first, run_config(new_thread_id), **DURABILITY)
    cfg = run_config(new_thread_id)
    graph.update_state(cfg, values, as_node=_predecessor(graph, snap.next[0], values))
    return graph.invoke(None, cfg, **DURABILITY)


def dry_run_graph(deps, version, checkpointer):
    return build_graph(replace(deps, ledger=DryRunLedger(deps.ledger)), version, checkpointer)


def thread_ids(dsn):
    with psycopg.connect(dsn, autocommit=True) as con:
        return [r[0] for r in con.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")]


def pending_reviews(graph, dsn):
    """Runs paused at the review step, with what the reviewer needs to see. Scans the threads that have checkpoints."""
    out = []
    for tid in thread_ids(dsn):
        if "@replay" in tid:                                         # what-if replays are not real work items
            continue
        snap = graph.get_state(run_config(tid))
        if snap.next == ("review",):
            interrupts = [i for t in snap.tasks for i in (t.interrupts or [])]
            out.append({"invoice_id": tid, "payload": interrupts[-1].value if interrupts else {}})
    return out
