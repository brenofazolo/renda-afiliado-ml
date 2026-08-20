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
    """Busca produtos de catálogo e devolve uma oferta concreta de cada produto."""
    limit = max(1, min(limit, 50))
    response = requests.get(
        f"{BASE_URL}/products/search",
        params={"status": "active", "site_id": site_id, "q": query, "limit": limit},
        headers=_headers(),
        timeout=20,
    )
    response.raise_for_status()

    collected_at = datetime.now(timezone.utc).isoformat()
    items: list[dict[str, Any]] = []

    for position, product in enumerate(response.json().get("results", []), start=1):
        product_id = product.get("id")
        if not product_id:
            continue

        detail = get_product(product_id)
        offer = detail.get("buy_box_winner")
        offer_source = "buy_box_winner"

        if not offer:
            related_items = get_product_items(product_id)
            offer = next(iter(related_items), None)
            offer_source = "product_items"

        if not offer:
            continue

        item = dict(offer)
        item["id"] = offer.get("item_id")
        item["title"] = detail.get("name") or product.get("name")
        item["catalog_product_id"] = product_id
        item["offer_source"] = offer_source
        item["permalink"] = detail.get("permalink")
        item["pictures"] = detail.get("pictures") or []
        first_picture = next(iter(item["pictures"]), {})
        item["thumbnail"] = first_picture.get("secure_url") or first_picture.get("url")
        item["_collection_position"] = position
        item["_collected_at"] = collected_at
        item["_query"] = query
        items.append(item)

    return items


def get_product(product_id: str) -> dict[str, Any]:
    """Consulta o detalhe de um produto de catálogo."""
    response = requests.get(
        f"{BASE_URL}/products/{quote_plus(product_id)}",
        headers=_headers(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_product_items(product_id: str) -> list[dict[str, Any]]:
    """Consulta as ofertas associadas a um produto de catálogo."""
    response = requests.get(
        f"{BASE_URL}/products/{quote_plus(product_id)}/items",
        headers=_headers(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("results", [])


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
        "catalog_product_id": item.get("catalog_product_id"),
        "item_id": item.get("id"),
        "offer_source": item.get("offer_source"),
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
