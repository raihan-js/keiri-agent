#!/usr/bin/env python3
"""Freeze the 300-invoice evaluation sample: a seeded random sample of the Invoice-Check JP TEST split, chosen from invoice ids alone
(no extraction, no label, no score is read). Writes data/eval300_ids.json, which is committed, and prints the input hashes."""
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED, N = 0, 300


def sha(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


if __name__ == "__main__":
    gold = ROOT / "data/invoice-check-jp/gold_test.jsonl"
    ids = sorted(json.loads(l)["invoice_id"] for l in gold.read_text(encoding="utf-8").splitlines() if l.strip())
    sample = sorted(random.Random(SEED).sample(ids, N))
    out = {"seed": SEED, "n": N, "source": "raihan-js/invoice-check-jp gold_test.jsonl (600)", "ids": sample}
    (ROOT / "data/eval300_ids.json").write_text(json.dumps(out, indent=1) + "\n")
    print("froze", len(sample), "ids;", sample[0], "...", sample[-1])
    inputs = {"gold_test.jsonl": gold, "registry_synthetic.jsonl": ROOT / "data/invoice-check-jp/registry_synthetic.jsonl",
              "qlora_test.jsonl (invoice-check-jp/results/preds)": ROOT.parent / "invoice-check-jp/results/preds/qlora_test.jsonl"}
    for k, p in inputs.items():
        print(f"sha256 {sha(p)}  {k}")
