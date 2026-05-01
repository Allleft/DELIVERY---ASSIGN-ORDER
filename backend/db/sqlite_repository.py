"""SQLite-backed repository for Office Dispatch Workbench MVP (Phase 2D-1)."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import date, datetime, UTC
from pathlib import Path
from typing import Any

from .repository import Record


_EMPTY_RESULT: Record = {"plans": [], "order_assignments": [], "exceptions": []}


class SQLiteDispatchRepository:
    """SQLite persistence implementation compatible with DispatchRepository."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def create_batch(self, dispatch_date: str | date, created_by: str, notes: str | None = None) -> Record:
        now = _utc_now_iso()
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO dispatch_batches (
                    dispatch_date, status, created_by, notes,
                    created_at, updated_at, generated_at, locked_at, locked_by
                )
                VALUES (?, 'DRAFT', ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (_normalize_dispatch_date(dispatch_date), created_by, notes, now, now),
            )
            batch_id = int(cursor.lastrowid)
            self._conn.execute(
                "INSERT OR REPLACE INTO dispatch_generated_results (batch_id, payload_json) VALUES (?, ?)",
                (batch_id, _serialize_json(_EMPTY_RESULT)),
            )
        batch = self.get_batch(batch_id)
        if batch is None:
            raise RuntimeError(f"Created batch {batch_id} not found.")
        return batch

    def list_batches(self) -> list[Record]:
        rows = self._conn.execute(
            """
            SELECT batch_id, dispatch_date, status, created_by, notes,
                   created_at, updated_at, generated_at, locked_at, locked_by
            FROM dispatch_batches
            ORDER BY batch_id ASC
            """
        ).fetchall()
        return [_row_to_batch(row) for row in rows]

    def get_batch(self, batch_id: int) -> Record | None:
        row = self._conn.execute(
            """
            SELECT batch_id, dispatch_date, status, created_by, notes,
                   created_at, updated_at, generated_at, locked_at, locked_by
            FROM dispatch_batches
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()
        return _row_to_batch(row) if row is not None else None

    def update_batch(self, batch_id: int, **updates: object) -> Record | None:
        if not updates:
            return self.get_batch(batch_id)
        if self.get_batch(batch_id) is None:
            return None

        assignments: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            assignments.append(f"{key} = ?")
            values.append(value)

        assignments.append("updated_at = ?")
        values.append(_utc_now_iso())
        values.append(batch_id)

        with self._conn:
            self._conn.execute(
                f"UPDATE dispatch_batches SET {', '.join(assignments)} WHERE batch_id = ?",
                tuple(values),
            )
        return self.get_batch(batch_id)

    def replace_batch_orders(self, batch_id: int, orders: list[Record]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM dispatch_orders WHERE batch_id = ?", (batch_id,))
            for order in orders:
                item = deepcopy(order)
                item["batch_id"] = batch_id
                order_id = str(item.get("order_id", "")).strip()
                self._conn.execute(
                    """
                    INSERT INTO dispatch_orders (batch_id, order_id, order_json)
                    VALUES (?, ?, ?)
                    """,
                    (batch_id, order_id, _serialize_json(item)),
                )

    def list_batch_orders(self, batch_id: int) -> list[Record]:
        rows = self._conn.execute(
            """
            SELECT order_json
            FROM dispatch_orders
            WHERE batch_id = ?
            ORDER BY rowid ASC
            """,
            (batch_id,),
        ).fetchall()
        return [_deserialize_json(row["order_json"]) for row in rows]

    def list_active_drivers(self) -> list[Record]:
        rows = self._conn.execute(
            "SELECT driver_json FROM drivers WHERE is_available = 1 ORDER BY driver_id ASC"
        ).fetchall()
        return [_deserialize_json(row["driver_json"]) for row in rows]

    def list_active_vehicles(self) -> list[Record]:
        rows = self._conn.execute(
            "SELECT vehicle_json FROM vehicles WHERE is_available = 1 ORDER BY vehicle_id ASC"
        ).fetchall()
        return [_deserialize_json(row["vehicle_json"]) for row in rows]

    def clear_generated_results(self, batch_id: int) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO dispatch_generated_results (batch_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (batch_id, _serialize_json(_EMPTY_RESULT)),
            )

    def save_generated_results(self, batch_id: int, payload: Record) -> None:
        normalized: Record = {
            "plans": deepcopy(list(payload.get("plans", []))),
            "order_assignments": deepcopy(list(payload.get("order_assignments", []))),
            "exceptions": deepcopy(list(payload.get("exceptions", []))),
        }
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO dispatch_generated_results (batch_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (batch_id, _serialize_json(normalized)),
            )

    def get_generated_results(self, batch_id: int) -> Record:
        row = self._conn.execute(
            "SELECT payload_json FROM dispatch_generated_results WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        if row is None:
            return deepcopy(_EMPTY_RESULT)
        payload = _deserialize_json(row["payload_json"])
        return {
            "plans": list(payload.get("plans", [])),
            "order_assignments": list(payload.get("order_assignments", [])),
            "exceptions": list(payload.get("exceptions", [])),
        }

    # Test fixtures helpers
    def seed_driver(self, driver: Record) -> None:
        item = deepcopy(driver)
        driver_id = int(item["driver_id"])
        is_available = 1 if bool(item.get("is_available", True)) else 0
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO drivers (driver_id, is_available, driver_json)
                VALUES (?, ?, ?)
                ON CONFLICT(driver_id) DO UPDATE SET
                    is_available = excluded.is_available,
                    driver_json = excluded.driver_json
                """,
                (driver_id, is_available, _serialize_json(item)),
            )

    def seed_vehicle(self, vehicle: Record) -> None:
        item = deepcopy(vehicle)
        vehicle_id = int(item["vehicle_id"])
        is_available = 1 if bool(item.get("is_available", True)) else 0
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO vehicles (vehicle_id, is_available, vehicle_json)
                VALUES (?, ?, ?)
                ON CONFLICT(vehicle_id) DO UPDATE SET
                    is_available = excluded.is_available,
                    vehicle_json = excluded.vehicle_json
                """,
                (vehicle_id, is_available, _serialize_json(item)),
            )

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dispatch_batches (
                    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dispatch_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    notes TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    generated_at TEXT NULL,
                    locked_at TEXT NULL,
                    locked_by TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS dispatch_orders (
                    dispatch_order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL,
                    order_id TEXT NOT NULL,
                    order_json TEXT NOT NULL,
                    UNIQUE(batch_id, order_id)
                );

                CREATE TABLE IF NOT EXISTS drivers (
                    driver_id INTEGER PRIMARY KEY,
                    is_available INTEGER NOT NULL DEFAULT 1,
                    driver_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS vehicles (
                    vehicle_id INTEGER PRIMARY KEY,
                    is_available INTEGER NOT NULL DEFAULT 1,
                    vehicle_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dispatch_generated_results (
                    batch_id INTEGER PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );
                """
            )


def _normalize_dispatch_date(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _serialize_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _deserialize_json(raw: str) -> Record:
    return json.loads(raw)


def _row_to_batch(row: sqlite3.Row) -> Record:
    return {
        "batch_id": int(row["batch_id"]),
        "dispatch_date": row["dispatch_date"],
        "status": row["status"],
        "created_by": row["created_by"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "generated_at": row["generated_at"],
        "locked_at": row["locked_at"],
        "locked_by": row["locked_by"],
    }
