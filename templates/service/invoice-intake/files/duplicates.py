from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def duplicate_fingerprint(fields, content_fingerprints=()):
    names = ("supplier_tax_id", "invoice_number", "issue_date", "total", "currency")
    values = [fields[name]["value"] for name in names]
    if all(value not in (None, "") for value in values):
        payload = json.dumps([str(value).strip().upper() for value in values], separators=(",", ":"))
        return "invoice-key:sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    values = sorted(set(content_fingerprints))
    return f"content:sha256:{values[0]}" if values else None


class InMemoryDuplicateLookup:
    def __init__(self): self._values = {}
    def find(self, fingerprint): return tuple(sorted(self._values.get(fingerprint, ())))
    def register(self, fingerprint, run_ref):
        if fingerprint: self._values.setdefault(fingerprint, set()).add(run_ref)


class SQLiteDuplicateLookup:
    def __init__(self, path):
        path = Path(path)
        for candidate in (path, path.parent):
            if candidate.exists() and candidate.is_symlink(): raise ValueError("Unsafe duplicate store path")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute("CREATE TABLE IF NOT EXISTS invoice_fingerprints (fingerprint TEXT NOT NULL, run_ref TEXT NOT NULL, PRIMARY KEY (fingerprint, run_ref))")
        self._connection.commit()
    def find(self, fingerprint):
        if not fingerprint: return ()
        rows = self._connection.execute("SELECT run_ref FROM invoice_fingerprints WHERE fingerprint = ? ORDER BY run_ref", (fingerprint,)).fetchall()
        return tuple(row[0] for row in rows)
    def register(self, fingerprint, run_ref):
        if fingerprint:
            with self._connection: self._connection.execute("INSERT OR IGNORE INTO invoice_fingerprints VALUES (?, ?)", (fingerprint, run_ref))
    def close(self): self._connection.close()
