"""The posting ledger: where an approved invoice ends up, and the source of the duplicate check.

`post` is idempotent on its key (the invoice id): a node that runs again after a crash or a resume must not post twice. The
Postgres implementation arrives with the durability milestone; the in-memory one below defines the contract the tests rely on.
"""
from typing import Optional, Protocol

from invoicecheck.checkdigit import normalize_registration_number
from invoicecheck.normalize import nfkc


def _number(v):
    import re
    return re.sub(r"\s+", "", nfkc(v or ""))


class Ledger(Protocol):
    def find_duplicate(self, supplier_reg_no: str, invoice_number: str, exclude_key: Optional[str] = None) -> Optional[str]: ...
    def post(self, key: str, record: dict) -> str: ...


class InMemoryLedger:
    def __init__(self, seed=()):
        self._rows = {}
        self._order = []
        for r in seed:
            self._add(r["invoice_id"], dict(r))

    def _add(self, key, record):
        self._rows[key] = record
        self._order.append(key)

    def find_duplicate(self, supplier_reg_no, invoice_number, exclude_key=None):
        reg, num = normalize_registration_number(supplier_reg_no), _number(invoice_number)
        if not reg or not num:
            return None
        for key in self._order:
            r = self._rows[key]
            if key != exclude_key and normalize_registration_number(r.get("supplier_reg_no")) == reg and _number(r.get("invoice_number")) == num:
                return key
        return None

    def post(self, key, record):
        if key not in self._rows:
            self._add(key, dict(record))
        return key

    def entries(self):
        return [dict(self._rows[k], invoice_id=k) for k in self._order]

    def __len__(self):
        return len(self._order)
