from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import requests

BASE_URL = "https://api.mercadolibre.com"


def _headers() -> dict[str, str]:
    token = os.getenv("MELI_ACCESS_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def search_items(query: str, limit: int = 20, site_id: str = "MLB") -> list[dict[str, Any]]:
    """Busca itens no marketplace e devolve os resultados brutos."""
    limit = max(1, min(limit, 50))
    url = f"{BASE_URL}/sites/{site_id}/search"
    params = {"q": query, "limit": limit}

    response = requests.get(url, params=params, headers=_headers(), timeout=20)
    response.raise_for_status()
    payload = response.json()

    collected_at = datetime.now(timezone.utc).isoformat()
    results = payload.get("results", [])

    for position, item in enumerate(results, start=1):
        item["_collection_position"] = position
        item["_collected_at"] = collected_at
        item["_query"] = query

    return results


def get_item(item_id: str) -> dict[str, Any]:
    """Consulta o detalhe de um anúncio."""
    url = f"{BASE_URL}/items/{quote_plus(item_id)}"
    response = requests.get(url, headers=_headers(), timeout=20)
    response.raise_for_status()
    return response.json()


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extrai somente os campos úteis para o MVP."""
    shipping = item.get("shipping") or {}
    original_price = item.get("original_price")
    price = item.get("price")

    discount = None
    if original_price and price and original_price > price:
        discount = round((1 - price / original_price) * 100, 2)

    return {
        "collected_at": item.get("_collected_at"),
        "query": item.get("_query"),
        "position": item.get("_collection_position"),
        "item_id": item.get("id"),
        "title": item.get("title"),
        "category_id": item.get("category_id"),
        "seller_id": item.get("seller_id"),
        "price": price,
        "original_price": original_price,
        "discount_percent": discount,
        "currency": item.get("currency_id"),
        "condition": item.get("condition") or item.get("item_condition"),
        "available_quantity": item.get("available_quantity"),
        "official_store_id": item.get("official_store_id"),
        "listing_type_id": item.get("listing_type_id"),
        "free_shipping": shipping.get("free_shipping"),
        "logistic_type": shipping.get("logistic_type"),
        "permalink": item.get("permalink"),
        "thumbnail": item.get("thumbnail"),
        "pictures_count": len(item.get("pictures") or []),
        "tags": ",".join(item.get("tags") or []),
    }
