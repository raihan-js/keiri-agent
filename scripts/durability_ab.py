#!/usr/bin/env python3
"""Does the checkpoint of the step BEFORE a SIGKILL survive? Kill the worker inside the `extract` node N times per durability mode and count.

Each trial: new throwaway database, worker runs ingest then hangs inside extract, the script SIGKILLs it, a fresh connection reads the state.
Survived = next node is `extract` (the ingest checkpoint was written); lost = next is `__start__` (nothing after the input was persisted).
"""
import sys
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from test_restart import inspect, spawn  # noqa: E402

from keiriagent.pg import default_dsn  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10

if __name__ == "__main__":
    base = default_dsn()
    admin = psycopg.connect(base, autocommit=True)
    head = base.rsplit("/", 1)[0]
    for mode in ("sync", "async", "exit"):
        survived = lost = 0
        for _ in range(N):
            name = "keiri_ab_" + uuid.uuid4().hex[:10]
            admin.execute(f"CREATE DATABASE {name}")
            dsn = f"{head}/{name}"
            try:
                p = spawn(dsn, "slow-extract", "inv_003000", env={"KEIRI_DURABILITY": mode})
                p.wait_for("EXTRACTING")
                p.kill()
                nxt = inspect(dsn, "inv_003000")[0].next
                survived += nxt == ("extract",)
                lost += nxt != ("extract",)
            finally:
                admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        print(f"durability={mode:5s} trials={N}  previous step survived the kill: {survived}  lost: {lost}")
