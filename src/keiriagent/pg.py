"""PostgreSQL pieces: the DSN, the LangGraph checkpointer and the posting ledger.

The checkpointer (langgraph-checkpoint-postgres) stores every step of every run, which is what makes a paused review survive a restart
and lets a past run be replayed from any checkpoint. The ledger is a plain table; `post` is `INSERT ... ON CONFLICT DO NOTHING` on the
invoice id, so re-running the `post` node after a crash (checkpoint not yet written, row already committed) cannot post twice.
"""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
from invoicecheck.checkdigit import normalize_registration_number
from invoicecheck.normalize import nfkc
from langgraph.checkpoint.postgres import PostgresSaver

SCHEMA = """
CREATE TABLE IF NOT EXISTS keiri_ledger (
  invoice_id          text PRIMARY KEY,
  supplier_reg_no     text,
  invoice_number_norm text,
  record              jsonb NOT NULL,
  posted_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS keiri_ledger_dup ON keiri_ledger (supplier_reg_no, invoice_number_norm);
"""


def default_dsn():
    """KEIRI_PG_DSN from the environment, else from the git-ignored .env next to the project."""
    if os.environ.get("KEIRI_PG_DSN"):
        return os.environ["KEIRI_PG_DSN"]
    env = Path(__file__).resolve().parents[2] / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("KEIRI_PG_DSN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("KEIRI_PG_DSN is not set and no .env was found")


def _norm_number(v):
    return re.sub(r"\s+", "", nfkc(v or ""))


@contextmanager
def postgres_saver(dsn=None):
    """A ready PostgresSaver (tables created). Use as `with postgres_saver() as saver: graph = build_graph(deps, v, saver)`."""
    with PostgresSaver.from_conn_string(dsn or default_dsn()) as saver:
        saver.setup()
        yield saver


class PostgresLedger:
    """Same contract as InMemoryLedger, backed by the `keiri_ledger` table. One autocommit connection."""

    def __init__(self, dsn=None, seed=()):
        self.con = psycopg.connect(dsn or default_dsn(), autocommit=True)
        self.con.execute(SCHEMA)
        for r in seed:
            self._insert(r["invoice_id"], dict(r))

    def _insert(self, key, record):
        self.con.execute(
            "INSERT INTO keiri_ledger (invoice_id, supplier_reg_no, invoice_number_norm, record) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (invoice_id) DO NOTHING",
            (key, normalize_registration_number(record.get("supplier_reg_no")), _norm_number(record.get("invoice_number")),
             json.dumps(record, ensure_ascii=False)))

    def find_duplicate(self, supplier_reg_no, invoice_number, exclude_key=None):
        reg, num = normalize_registration_number(supplier_reg_no), _norm_number(invoice_number)
        if not reg or not num:
            return None
        row = self.con.execute(
            "SELECT invoice_id FROM keiri_ledger WHERE supplier_reg_no = %s AND invoice_number_norm = %s AND invoice_id <> %s "
            "ORDER BY posted_at, invoice_id LIMIT 1", (reg, num, exclude_key or "")).fetchone()
        return row[0] if row else None

    def post(self, key, record):
        self._insert(key, record)
        return key

    def entries(self):
        return [dict(r[1], invoice_id=r[0]) for r in self.con.execute("SELECT invoice_id, record FROM keiri_ledger ORDER BY posted_at, invoice_id")]

    def __len__(self):
        return self.con.execute("SELECT count(*) FROM keiri_ledger").fetchone()[0]

    def close(self):
        self.con.close()
