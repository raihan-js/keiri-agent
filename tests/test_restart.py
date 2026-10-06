"""Durability: kill the process with SIGKILL at three different moments, resume in a NEW process, and check the result.

  1. while the run is paused for human review,
  2. in the middle of a node (the extractor never returns),
  3. after the ledger commit but before the checkpoint of the `post` node (the dangerous moment for double posting).
All against a real PostgreSQL (throwaway database per test); skipped when it is not reachable.
"""
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver  # noqa: F401

import support
from keiriagent.graph import build_graph
from keiriagent.pg import PostgresLedger, postgres_saver

WORKER = str(Path(__file__).parent / "worker.py")
CLEAN, ISSUE_CD = "inv_003000", "inv_003057"
FULL_AUTO = ["ingest:received", "extract:parsed", "verify:passed", "check_duplicate:unique", "match_po:matched", "decide:auto_approve", "post:posted"]


class Proc:
    """A subprocess whose stdout lines are read by a thread (select() on a buffered stream misses lines already buffered)."""

    def __init__(self, args, env=None):
        self.p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.seen = []

    def _pump(self):
        for line in self.p.stdout:
            self.lines.put(line)
        self.lines.put(None)                                        # end of stream

    def wait_for(self, marker, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                break
            self.seen.append(line)
            if marker in line:
                return
        raise AssertionError(f"never saw {marker!r}; saw {self.seen}; stderr: {self.p.stderr.read()[-800:] if self.p.poll() is not None else '(still running)'}")

    def kill(self):
        self.p.kill()
        self.p.wait()

    def result(self, timeout=60):
        self.p.wait(timeout=timeout)
        while True:
            line = self.lines.get(timeout=5)
            if line is None:
                break
            self.seen.append(line)
        lines = [l for l in self.seen if l.startswith("RESULT ")]
        assert lines, f"no RESULT; rc={self.p.returncode}; saw {self.seen}; stderr: {self.p.stderr.read()[-800:]}"
        return json.loads(lines[-1][7:])


def spawn(dsn, mode, invoice_id, answer=None, env=None):
    import os
    args = [sys.executable, WORKER, dsn, mode, invoice_id] + ([json.dumps(answer)] if answer else [])
    return Proc(args, env={**os.environ, **(env or {})})


def inspect(dsn, invoice_id):
    """What a fresh process sees: the graph state and the number of ledger rows."""
    with postgres_saver(dsn) as saver:
        graph = build_graph(support.build_deps(PostgresLedger(dsn)), "v3_verify_po", saver)
        st = graph.get_state({"configurable": {"thread_id": invoice_id}})
    ledger = PostgresLedger(dsn)
    n = len(ledger)
    ledger.close()
    return st, n


def test_kill_while_paused_for_review_then_resume_in_a_new_process(pg_dsn):
    p1 = spawn(pg_dsn, "start-hang", ISSUE_CD)
    p1.wait_for("READY")
    p1.kill()                                                       # SIGKILL: no cleanup of any kind
    st, rows = inspect(pg_dsn, ISSUE_CD)
    assert st.next == ("review",) and rows == 0 and st.values["decision"] == "human_review"
    res = spawn(pg_dsn, "resume", ISSUE_CD, {"action": "approve", "reviewer": "kato"}).result()
    assert res["outcome"] == "posted" and res["events"][-2:] == ["review:approve", "post:posted"]
    st, rows = inspect(pg_dsn, ISSUE_CD)
    assert rows == 1 and st.next == () and sum(e["node"] == "review" for e in st.values["audit"]) == 1


def test_kill_inside_a_node_resumes_from_the_last_checkpoint_without_repeating_work(pg_dsn):
    p1 = spawn(pg_dsn, "slow-extract", CLEAN)
    p1.wait_for("EXTRACTING")
    p1.kill()
    st, rows = inspect(pg_dsn, CLEAN)
    assert st.next == ("extract",) and rows == 0
    assert [a["node"] + ":" + a["event"] for a in st.values["audit"]] == ["ingest:received"]
    res = spawn(pg_dsn, "continue", CLEAN).result()
    assert res["outcome"] == "posted" and res["events"] == FULL_AUTO          # every step exactly once; ingest was not repeated
    assert inspect(pg_dsn, CLEAN)[1] == 1


def test_kill_after_the_ledger_commit_does_not_post_twice(pg_dsn):
    p1 = spawn(pg_dsn, "crash-after-post", CLEAN)
    p1.p.wait(timeout=60)
    assert p1.p.returncode == -9                                      # it killed itself right after the INSERT committed
    st, rows = inspect(pg_dsn, CLEAN)
    assert rows == 1 and st.next == ("post",)                       # posted in the ledger, but the graph does not know yet
    res = spawn(pg_dsn, "continue", CLEAN).result()               # `post` runs again
    assert res["outcome"] == "posted" and res["events"] == FULL_AUTO
    st, rows = inspect(pg_dsn, CLEAN)
    assert rows == 1 and st.next == ()                              # still exactly one ledger row
