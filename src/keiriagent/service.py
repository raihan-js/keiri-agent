"""HTTP service around the graph: start a run, list and answer reviews, inspect a run, replay it. Plus the review page at `/`.

Every graph call uses durability="sync". A reviewer's answer is validated BEFORE the graph is resumed (a bad answer is a 400, the run stays paused),
and only a run that is actually paused at `review` can be answered (409 otherwise), so a double click cannot resume twice.
"""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from .graph import build_graph
from .ops import DURABILITY, dry_run_graph, history, pending_reviews, replay, run_config
from .review import validate_review

UI = Path(__file__).with_name("review_ui.html")


class StartRequest(BaseModel):
    invoice_id: str = Field(..., min_length=1)
    document: str | None = None


class ReviewAnswer(BaseModel):
    action: str
    reviewer: str
    corrections: dict | None = None
    note: str | None = None


class ReplayRequest(BaseModel):
    checkpoint_id: str
    overrides: dict | None = None


def _summary(out):
    return {"invoice_id": out.get("invoice_id"), "decision": out.get("decision"), "decision_reasons": out.get("decision_reasons", []),
            "outcome": out.get("outcome"), "paused_for_review": "__interrupt__" in out, "ledger_id": out.get("ledger_id")}


def create_app(deps, dsn, version="v3_verify_po"):
    state = {}

    @asynccontextmanager
    async def lifespan(app):
        pool = ConnectionPool(dsn, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}, max_size=10, open=True)
        saver = PostgresSaver(pool)
        saver.setup()
        state["graph"] = build_graph(deps, version, saver)
        state["dry"] = dry_run_graph(deps, version, saver)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(title="Keiri-Agent", version="0.1.0", lifespan=lifespan,
                  description="LangGraph back-office agent for synthetic Japanese qualified invoices. Not an accounting product; no tax advice.")

    @app.get("/health")
    def health():
        return {"status": "ok", "version": version}

    @app.get("/", response_class=HTMLResponse)
    def ui():
        return UI.read_text(encoding="utf-8")

    @app.post("/invoices")
    def start(req: StartRequest):
        g = state["graph"]
        existing = g.get_state(run_config(req.invoice_id))
        if existing.values:
            raise HTTPException(409, f"{req.invoice_id} already has a run; inspect it at /invoices/{req.invoice_id}")
        return _summary(g.invoke({"invoice_id": req.invoice_id, "document": req.document or ""}, run_config(req.invoice_id), **DURABILITY))

    @app.get("/invoices/{invoice_id}")
    def show(invoice_id: str):
        snap = state["graph"].get_state(run_config(invoice_id))
        if not snap.values:
            raise HTTPException(404, "no such run")
        return {**snap.values, "next": list(snap.next)}

    @app.get("/invoices/{invoice_id}/history")
    def hist(invoice_id: str):
        h = history(state["graph"], invoice_id)
        if not h:
            raise HTTPException(404, "no such run")
        return h

    @app.post("/invoices/{invoice_id}/replay")
    def do_replay(invoice_id: str, req: ReplayRequest):
        if not history(state["graph"], invoice_id):
            raise HTTPException(404, "no such run")
        new_id = f"{invoice_id}@replay-{uuid.uuid4().hex[:6]}"
        try:
            out = replay(state["dry"], invoice_id, req.checkpoint_id, new_id, req.overrides)
        except Exception as e:                                       # unknown checkpoint, bad override: a client error, not a crash
            raise HTTPException(400, f"replay failed: {type(e).__name__}: {e}")
        return {"replay_thread": new_id, **_summary(out)}

    @app.get("/reviews")
    def reviews():
        return pending_reviews(state["graph"], dsn)

    @app.post("/reviews/{invoice_id}")
    def answer(invoice_id: str, body: ReviewAnswer):
        g = state["graph"]
        try:
            validate_review(body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e))
        if g.get_state(run_config(invoice_id)).next != ("review",):
            raise HTTPException(409, "this invoice is not waiting for a review")
        return _summary(g.invoke(Command(resume=body.model_dump()), run_config(invoice_id), **DURABILITY))

    return app
