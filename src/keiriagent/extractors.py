"""Extractors: where the invoice fields come from. The graph only sees this interface.

`CachedExtractor` replays the fine-tuned model's stored outputs (Invoice-Check JP `results/preds/*.jsonl`), so graph versions can be
compared on identical extractions and an evaluation costs no GPU time. A live extractor (the QLoRA adapter behind an
OpenAI-compatible server) implements the same method and is used for the demo and the restart test.
"""
import copy
import json
from typing import Optional, Protocol


class Extractor(Protocol):
    def extract(self, invoice_id: str, document: str) -> Optional[dict]: ...


class CachedExtractor:
    def __init__(self, preds_path):
        self._parsed = {}
        with open(preds_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    p = r.get("parsed")
                    self._parsed[r["id"]] = p if isinstance(p, dict) and p else None

    def extract(self, invoice_id, document=None):
        return copy.deepcopy(self._parsed.get(invoice_id))

    def __len__(self):
        return len(self._parsed)


class StaticExtractor:
    """Tests: a fixed mapping of invoice id to the extraction to return."""

    def __init__(self, mapping):
        self._m = mapping

    def extract(self, invoice_id, document=None):
        return copy.deepcopy(self._m.get(invoice_id))
