"""The HTTP service on PostgreSQL: start runs, answer reviews, inspect, replay."""
import pytest
from fastapi.testclient import TestClient

import support
from keiriagent.pg import PostgresLedger
from keiriagent.service import create_app

CLEAN, ISSUE_CD = "inv_003000", "inv_003057"


@pytest.fixture
def client(pg_dsn):
    ledger = PostgresLedger(pg_dsn)
    with TestClient(create_app(support.build_deps(ledger), pg_dsn)) as c:
        c.ledger = ledger
        yield c
    ledger.close()


def test_health_and_ui(client):
    assert client.get("/health").json()["status"] == "ok"
    html = client.get("/").text
    assert "Keiri-Agent review queue" in html and "innerHTML" not in html          # no HTML injection from invoice data


def test_clean_invoice_is_posted_and_a_second_start_is_refused(client):
    r = client.post("/invoices", json={"invoice_id": CLEAN}).json()
    assert r["outcome"] == "posted" and r["decision"] == "auto_approve" and not r["paused_for_review"] and len(client.ledger) == 1
    assert client.post("/invoices", json={"invoice_id": CLEAN}).status_code == 409
    assert client.post("/invoices", json={"invoice_id": ""}).status_code == 422
    assert client.get(f"/invoices/{CLEAN}").json()["next"] == []
    assert client.get("/invoices/nope").status_code == 404 and client.get("/invoices/nope/history").status_code == 404


def test_review_flow_validates_before_resuming_and_blocks_double_answers(client):
    r = client.post("/invoices", json={"invoice_id": ISSUE_CD}).json()
    assert r["paused_for_review"] and r["outcome"] == "pending_review" and len(client.ledger) == 0
    q = client.get("/reviews").json()
    assert [x["invoice_id"] for x in q] == [ISSUE_CD] and "check_digit:invalid" in q[0]["payload"]["reasons"]
    bad = client.post(f"/reviews/{ISSUE_CD}", json={"action": "approve", "reviewer": " "})
    assert bad.status_code == 400 and client.get("/reviews").json()[0]["invoice_id"] == ISSUE_CD      # still waiting, nothing posted
    assert client.post(f"/reviews/{ISSUE_CD}", json={"action": "correct", "reviewer": "kato"}).status_code == 400
    ok = client.post(f"/reviews/{ISSUE_CD}", json={"action": "approve", "reviewer": "kato"})
    assert ok.status_code == 200 and ok.json()["outcome"] == "posted" and len(client.ledger) == 1
    assert client.post(f"/reviews/{ISSUE_CD}", json={"action": "approve", "reviewer": "kato"}).status_code == 409
    assert client.post("/reviews/unknown", json={"action": "approve", "reviewer": "kato"}).status_code == 409
    assert client.get("/reviews").json() == []


def test_history_and_replay_endpoints(client):
    client.post("/invoices", json={"invoice_id": CLEAN})
    hist = client.get(f"/invoices/{CLEAN}/history").json()
    cp = next(h for h in hist if h["next"] == ["decide"])["checkpoint_id"]
    same = client.post(f"/invoices/{CLEAN}/replay", json={"checkpoint_id": cp}).json()
    assert same["decision"] == "auto_approve" and "@replay-" in same["replay_thread"] and len(client.ledger) == 1
    what_if = client.post(f"/invoices/{CLEAN}/replay", json={"checkpoint_id": cp, "overrides": {"po_match": {"status": "no_po", "po_id": None, "reasons": ["po:no_po"]}}}).json()
    assert what_if["decision"] == "human_review" and what_if["paused_for_review"]
    assert client.get("/reviews").json() == []                                       # a what-if is not a work item
    assert client.get(f"/invoices/{CLEAN}").json()["outcome"] == "posted"            # the live run is untouched
    assert client.post(f"/invoices/{CLEAN}/replay", json={"checkpoint_id": "does-not-exist"}).status_code == 400
