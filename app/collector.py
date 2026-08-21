from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from .token_manager import meli_request

BASE_URL = "https://api.mercadolibre.com"


def search_items(
    query: str,
    limit: int = 20,
    site_id: str = "MLB",
    stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Busca produtos de catálogo e devolve uma oferta concreta de cada produto."""
    limit = max(1, min(limit, 50))
    response = meli_request(
        "GET",
        f"{BASE_URL}/products/search",
        params={"status": "active", "site_id": site_id, "q": query, "limit": limit},
        timeout=20,
    )
    response.raise_for_status()

    products = response.json().get("results", [])
    domain_counts = Counter(
        product.get("domain_id") for product in products if product.get("domain_id")
    )
    dominant_domain = domain_counts.most_common(1)[0][0] if domain_counts else None

    collection_stats: dict[str, Any] = {
        "products_found": len(products),
        "dominant_domain": dominant_domain,
        "filtered_by_domain": 0,
        "with_buy_box": 0,
        "via_product_items": 0,
        "without_offer": 0,
        "analyzed": 0,
    }

    collected_at = datetime.now(timezone.utc).isoformat()
    items: list[dict[str, Any]] = []

    for position, product in enumerate(products, start=1):
        if dominant_domain and product.get("domain_id") != dominant_domain:
            collection_stats["filtered_by_domain"] += 1
            continue

        product_id = product.get("id")
        if not product_id:
            collection_stats["without_offer"] += 1
            continue

        detail = get_product(product_id)
        offer = detail.get("buy_box_winner")
        offer_source = "buy_box_winner"

        if offer:
            collection_stats["with_buy_box"] += 1
        else:
            related_items = get_product_items(product_id)
            offer = next(iter(related_items), None)
            offer_source = "product_items"
            if offer:
                collection_stats["via_product_items"] += 1

        if not offer:
            collection_stats["without_offer"] += 1
            continue

        item = dict(offer)
        item["id"] = offer.get("item_id")
        item["title"] = detail.get("name") or product.get("name")
        item["catalog_product_id"] = product_id
        item["domain_id"] = product.get("domain_id") or detail.get("domain_id")
        item["offer_source"] = offer_source
        item["permalink"] = None
        item["pictures"] = detail.get("pictures") or []
        first_picture = next(iter(item["pictures"]), {})
        item["thumbnail"] = first_picture.get("secure_url") or first_picture.get("url")
        item["_collection_position"] = position
        item["_collected_at"] = collected_at
        item["_query"] = query
        items.append(item)

    collection_stats["analyzed"] = len(items)
    if stats is not None:
        stats.clear()
        stats.update(collection_stats)

    return items


def get_product(product_id: str) -> dict[str, Any]:
    """Consulta o detalhe de um produto de catálogo."""
    response = meli_request(
        "GET",
        f"{BASE_URL}/products/{quote_plus(product_id)}",
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_product_items(product_id: str) -> list[dict[str, Any]]:
    """Consulta as ofertas associadas a um produto de catálogo.

    A API pode retornar 404 para produtos ativos que não possuem publicações
    consultáveis. Nesse caso, o produto é ignorado e a coleta continua.
    """
    response = meli_request(
        "GET",
        f"{BASE_URL}/products/{quote_plus(product_id)}/items",
        timeout=20,
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("results", [])


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
        "domain_id": item.get("domain_id"),
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
