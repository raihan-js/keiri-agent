#!/usr/bin/env python3
"""Write a Mermaid diagram of each graph version to docs/graphs/<version>.mmd, generated from the compiled graphs (never drawn by hand)."""
from pathlib import Path

from keiriagent.decide import VERSIONS
from keiriagent.extractors import StaticExtractor
from keiriagent.graph import Deps, build_graph
from keiriagent.ledger import InMemoryLedger
from keiriagent.po import PoStore

OUT = Path(__file__).resolve().parent.parent / "docs" / "graphs"

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for v in VERSIONS:
        g = build_graph(Deps(StaticExtractor({}), None, PoStore(), InMemoryLedger()), v)
        (OUT / f"{v}.mmd").write_text(g.get_graph().draw_mermaid(), encoding="utf-8")
        print("wrote", OUT / f"{v}.mmd")
