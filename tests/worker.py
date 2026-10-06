"""Subprocess worker for the restart tests: runs (part of) one invoice against PostgreSQL and prints what happened.

  worker.py <dsn> <mode> <invoice_id> [reviewer_answer_json]
modes: start | start-hang (stay alive after the run pauses, to be killed) | slow-extract (hang inside `extract`) |
       crash-after-post (SIGKILL itself right after the ledger commit, before the checkpoint) | resume (needs the answer) | continue
Prints `READY` / `EXTRACTING` markers and a final `RESULT {json}` line.
"""
import json
import os
import signal
import sys
import time

from langgraph.types import Command

import support
from keiriagent.extractors import StaticExtractor
from keiriagent.graph import build_graph
from keiriagent.pg import PostgresLedger, postgres_saver


class SlowExtractor(StaticExtractor):
    def extract(self, invoice_id, document=None):
        print("EXTRACTING", flush=True)
        time.sleep(600)


class CrashingLedger(PostgresLedger):
    def post(self, key, record):
        super().post(key, record)                    # committed
        os.kill(os.getpid(), signal.SIGKILL)         # the checkpoint for this node is never written


def main():
    dsn, mode, invoice_id = sys.argv[1:4]
    answer = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
    ledger = (CrashingLedger if mode == "crash-after-post" else PostgresLedger)(dsn)
    extractor = SlowExtractor({}) if mode == "slow-extract" else None
    cfg = {"configurable": {"thread_id": invoice_id}}
    kw = {"durability": os.environ.get("KEIRI_DURABILITY", "sync")}
    with postgres_saver(dsn) as saver:
        graph = build_graph(support.build_deps(ledger, extractor), "v3_verify_po", saver)
        if mode in ("start", "start-hang", "slow-extract", "crash-after-post"):
            out = graph.invoke({"invoice_id": invoice_id}, cfg, **kw)
        elif mode == "resume":
            out = graph.invoke(Command(resume=answer), cfg, **kw)
        elif mode == "continue":
            out = graph.invoke(None, cfg, **kw)
        else:
            raise SystemExit(f"unknown mode {mode}")
        print("RESULT " + json.dumps({"outcome": out.get("outcome"), "decision": out.get("decision"), "paused": "__interrupt__" in out,
                                      "events": [a["node"] + ":" + a["event"] for a in out["audit"]]}), flush=True)
        if mode == "start-hang":
            print("READY", flush=True)
            time.sleep(600)


if __name__ == "__main__":
    main()
