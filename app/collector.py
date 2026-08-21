from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from .token_manager import meli_request

BASE_URL = "https://api.mercadolibre.com"
MAX_WORKERS = 5


def _offer_for_product(product_id: str) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    """Retorna detalhe do catálogo, uma oferta concreta e a origem da oferta."""
    detail = get_product(product_id)
    offer = detail.get("buy_box_winner")
    if offer:
        return offer, detail, "buy_box_winner"

    related_items = get_product_items(product_id)
    offer = next(iter(related_items), None)
    if offer:
        return offer, detail, "product_items"

    return None, detail, None


def _build_item(
    product_id: str,
    product: dict[str, Any],
    detail: dict[str, Any],
    offer: dict[str, Any],
    offer_source: str,
    query: str,
    collected_at: str,
    search_position: int | None = None,
    best_seller_position: int | None = None,
) -> dict[str, Any]:
    item = dict(offer)
    item["id"] = offer.get("item_id")
    item["title"] = detail.get("name") or product.get("name")
    item["catalog_product_id"] = product_id
    item["domain_id"] = product.get("domain_id") or detail.get("domain_id")
    item["offer_source"] = offer_source
    # O detalhe do produto normalmente traz a página de catálogo. Algumas
    # respostas de oferta também podem trazer um permalink mais específico;
    # preserve-o quando o detalhe não fornecer um endereço.
    item["permalink"] = detail.get("permalink") or offer.get("permalink")
    item["pictures"] = detail.get("pictures") or []
    first_picture = next(iter(item["pictures"]), {})
    item["thumbnail"] = first_picture.get("secure_url") or first_picture.get("url")
    item["_collection_position"] = search_position
    item["_best_seller_position"] = best_seller_position
    item["_collected_at"] = collected_at
    item["_query"] = query
    return item


def _collect_search_candidate(
    args: tuple[int, dict[str, Any], str, str]
) -> tuple[dict[str, Any] | None, str]:
    position, product, query, collected_at = args
    product_id = product.get("id")
    if not product_id:
        return None, "without_offer"

    offer, detail, offer_source = _offer_for_product(product_id)
    if not offer or not offer_source:
        return None, "without_offer"

    item = _build_item(
        product_id=product_id,
        product=product,
        detail=detail,
        offer=offer,
        offer_source=offer_source,
        query=query,
        collected_at=collected_at,
        search_position=position,
    )
    return item, offer_source


def search_items(
    query: str,
    limit: int = 20,
    site_id: str = "MLB",
    stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Busca produtos de catálogo e coleta ofertas em paralelo controlado."""
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
        "parallel_workers": MAX_WORKERS,
    }

    collected_at = datetime.now(timezone.utc).isoformat()
    candidates: list[tuple[int, dict[str, Any], str, str]] = []

    for position, product in enumerate(products, start=1):
        if dominant_domain and product.get("domain_id") != dominant_domain:
            collection_stats["filtered_by_domain"] += 1
            continue
        candidates.append((position, product, query, collected_at))

    items: list[dict[str, Any]] = []
    if candidates:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for item, status in executor.map(_collect_search_candidate, candidates):
                if status == "without_offer":
                    collection_stats["without_offer"] += 1
                    continue
                if status == "buy_box_winner":
                    collection_stats["with_buy_box"] += 1
                elif status == "product_items":
                    collection_stats["via_product_items"] += 1
                if item:
                    items.append(item)

    collection_stats["analyzed"] = len(items)
    if stats is not None:
        stats.clear()
        stats.update(collection_stats)

    return items


def _collect_ranked_candidate(
    args: tuple[dict[str, Any], str, str]
) -> tuple[dict[str, Any] | None, str]:
    entry, query, collected_at = args
    product_id = entry.get("id")
    if not product_id:
        return None, "without_offer"

    offer, detail, offer_source = _offer_for_product(product_id)
    if not offer or not offer_source:
        return None, "without_offer"

    product = {
        "id": product_id,
        "name": detail.get("name"),
        "domain_id": detail.get("domain_id"),
    }
    item = _build_item(
        product_id=product_id,
        product=product,
        detail=detail,
        offer=offer,
        offer_source=offer_source,
        query=query,
        collected_at=collected_at,
        best_seller_position=entry.get("position"),
    )
    return item, offer_source


def collect_ranked_products(
    ranked_products: list[dict[str, Any]],
    query: str,
    existing_product_ids: set[str] | None = None,
    stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Coleta em paralelo ofertas concretas para produtos do ranking."""
    existing = existing_product_ids or set()
    collected_at = datetime.now(timezone.utc).isoformat()
    items: list[dict[str, Any]] = []
    ranking_stats = {
        "ranking_products": 0,
        "ranking_duplicates": 0,
        "ranking_with_buy_box": 0,
        "ranking_via_product_items": 0,
        "ranking_without_offer": 0,
        "ranking_added": 0,
        "parallel_workers": MAX_WORKERS,
    }

    candidates: list[tuple[dict[str, Any], str, str]] = []
    for entry in ranked_products:
        if entry.get("type") != "PRODUCT":
            continue
        product_id = entry.get("id")
        if not product_id:
            continue
        ranking_stats["ranking_products"] += 1
        if product_id in existing:
            ranking_stats["ranking_duplicates"] += 1
            continue
        candidates.append((entry, query, collected_at))

    if candidates:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for item, status in executor.map(_collect_ranked_candidate, candidates):
                if status == "without_offer":
                    ranking_stats["ranking_without_offer"] += 1
                    continue
                if status == "buy_box_winner":
                    ranking_stats["ranking_with_buy_box"] += 1
                elif status == "product_items":
                    ranking_stats["ranking_via_product_items"] += 1
                if item:
                    items.append(item)

    ranking_stats["ranking_added"] = len(items)
    if stats is not None:
        stats.clear()
        stats.update(ranking_stats)

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
        "best_seller_position": item.get("_best_seller_position"),
    }
