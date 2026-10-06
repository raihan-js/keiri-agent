import os
from pathlib import Path

import pytest

os.environ["LANGSMITH_TRACING"] = "false"          # tests never call out
os.environ.pop("LANGSMITH_API_KEY", None)

from invoicecheck.extraction import gold_to_target

from keiriagent.data import load_synthetic_registry, read_jsonl
from keiriagent.extractors import StaticExtractor
from keiriagent.graph import Deps
from keiriagent.ledger import InMemoryLedger
from keiriagent.po import POLine, PoStore, PurchaseOrder

from support import FIX, load_gold, load_registry, po_for  # noqa: E402,F401  (po_for is re-exported for the tests)


@pytest.fixture(scope="session")
def gold():
    return load_gold()


@pytest.fixture(scope="session")
def registry():
    return load_registry()


@pytest.fixture
def make_deps(gold, registry):
    def _make(extractions=None, orders=(), ledger_seed=()):
        ext = extractions if extractions is not None else {k: gold_to_target(v) for k, v in gold.items()}
        return Deps(StaticExtractor(ext), registry, PoStore(orders), InMemoryLedger(ledger_seed))
    return _make


# ---- PostgreSQL (throwaway database per test; skipped when the server is not reachable) ----
import uuid

import psycopg


def _admin_dsn():
    from keiriagent.pg import default_dsn
    try:
        return default_dsn()
    except RuntimeError:
        return None


@pytest.fixture
def pg_dsn():
    base = _admin_dsn()
    if not base:
        pytest.skip("no KEIRI_PG_DSN")
    try:
        admin = psycopg.connect(base, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL not reachable")
    name = "keiri_test_" + uuid.uuid4().hex[:10]
    admin.execute(f"CREATE DATABASE {name}")
    head, _ = base.rsplit("/", 1)
    try:
        yield f"{head}/{name}"
    finally:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        admin.close()
