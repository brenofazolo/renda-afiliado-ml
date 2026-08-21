from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def database_path() -> Path:
    configured = os.getenv("WEB_DATABASE_PATH", "").strip()
    return Path(configured) if configured else ROOT / "data" / "pilot.db"


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_product_id TEXT NOT NULL UNIQUE,
                item_id TEXT,
                title TEXT NOT NULL,
                thumbnail TEXT,
                price REAL,
                marketplace_score REAL,
                best_seller_position INTEGER,
                affiliate_direct_value REAL,
                affiliate_indirect_value REAL,
                product_url TEXT,
                search_url TEXT,
                query TEXT,
                decision TEXT NOT NULL DEFAULT 'approved',
                discard_reason TEXT,
                notes TEXT,
                affiliate_url TEXT,
                publication_status TEXT NOT NULL DEFAULT 'selected',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def save_selection(values: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    fields = {
        "catalog_product_id": values.get("catalog_product_id"),
        "item_id": values.get("item_id"),
        "title": values.get("title") or "Produto sem título",
        "thumbnail": values.get("thumbnail"),
        "price": values.get("price"),
        "marketplace_score": values.get("marketplace_score"),
        "best_seller_position": values.get("best_seller_position"),
        "affiliate_direct_value": values.get("affiliate_direct_value"),
        "affiliate_indirect_value": values.get("affiliate_indirect_value"),
        "product_url": values.get("product_url"),
        "search_url": values.get("search_url"),
        "query": values.get("query"),
        "decision": values.get("decision") or "approved",
        "discard_reason": values.get("discard_reason"),
        "notes": values.get("notes"),
    }
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO selections (
                catalog_product_id, item_id, title, thumbnail, price,
                marketplace_score, best_seller_position, affiliate_direct_value,
                affiliate_indirect_value, product_url, search_url, query, decision,
                discard_reason, notes, created_at, updated_at
            ) VALUES (
                :catalog_product_id, :item_id, :title, :thumbnail, :price,
                :marketplace_score, :best_seller_position, :affiliate_direct_value,
                :affiliate_indirect_value, :product_url, :search_url, :query, :decision,
                :discard_reason, :notes, :created_at, :updated_at
            )
            ON CONFLICT(catalog_product_id) DO UPDATE SET
                decision=excluded.decision,
                discard_reason=excluded.discard_reason,
                notes=COALESCE(excluded.notes, selections.notes),
                price=excluded.price,
                marketplace_score=excluded.marketplace_score,
                best_seller_position=excluded.best_seller_position,
                product_url=excluded.product_url,
                thumbnail=excluded.thumbnail,
                updated_at=excluded.updated_at
            """,
            {**fields, "created_at": now, "updated_at": now},
        )


def list_selections(decision: str = "approved") -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM selections WHERE decision = ? ORDER BY updated_at DESC",
            (decision,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_selection(selection_id: int, values: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(
            """
            UPDATE selections SET notes = ?, affiliate_url = ?,
                publication_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                values.get("notes"),
                values.get("affiliate_url"),
                values.get("publication_status") or "selected",
                datetime.now(timezone.utc).isoformat(),
                selection_id,
            ),
        )
