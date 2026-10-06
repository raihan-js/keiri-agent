#!/usr/bin/env python3
"""Download the gold labels and the synthetic registry of the Invoice-Check JP dataset (public, CC-BY-4.0) into data/invoice-check-jp/.

The images (0.58 GB) are only needed for the live-extractor demo and are not fetched here:
    hf download raihan-js/invoice-check-jp --repo-type dataset --include "images/test/*" --local-dir data/invoice-check-jp
"""
from pathlib import Path

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parent.parent
FILES = ["gold_val.jsonl", "gold_test.jsonl", "gold_holdout.jsonl", "registry_synthetic.jsonl", "README.md"]

if __name__ == "__main__":
    for f in FILES:
        p = hf_hub_download("raihan-js/invoice-check-jp", f, repo_type="dataset", local_dir=ROOT / "data" / "invoice-check-jp")
        print(f, Path(p).stat().st_size)
