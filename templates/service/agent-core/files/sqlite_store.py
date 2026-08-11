from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

from .errors import ConcurrentUpdateError, DuplicateRunError
from .validation import validate_execution_record


def _canonical(record):
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SQLiteExecutionRecordStore:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists() and self.path.is_symlink():
            raise ValueError("SQLite store cannot be a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS execution_records "
            "(run_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, record_json TEXT NOT NULL)"
        )
        self._connection.commit()

    def close(self): self._connection.close()

    def get(self, run_id):
        row = self._connection.execute(
            "SELECT record_json FROM execution_records WHERE run_id = ?", (run_id,)
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def create(self, record):
        validated = copy.deepcopy(validate_execution_record(record))
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO execution_records(run_id, revision, record_json) VALUES (?, ?, ?)",
                    (validated["run_id"], validated["revision"], _canonical(validated)),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateRunError(f"Run already exists: {validated['run_id']}") from error

    def replace(self, record, *, expected_revision):
        replacement = copy.deepcopy(record)
        replacement["revision"] = expected_revision + 1
        validate_execution_record(replacement)
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE execution_records SET revision = ?, record_json = ? "
                "WHERE run_id = ? AND revision = ?",
                (replacement["revision"], _canonical(replacement), replacement["run_id"], expected_revision),
            )
        if cursor.rowcount != 1:
            raise ConcurrentUpdateError(f"Stale execution record: {replacement['run_id']}")
