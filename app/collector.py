from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import requests

from .token_manager import meli_request

BASE_URL = "https://api.mercadolibre.com"
MAX_WORKERS = 5


def _offer_for_product(product_id: str) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    """Retorna detalhe do catálogo, uma oferta concreta e a origem da oferta."""
    detail = get_product(product_id)
    offer = detail.get("buy_box_winner")
    if offer:
        return _with_sale_price(offer), detail, "buy_box_winner"

    related_items = get_product_items(product_id)
    offer = next(iter(related_items), None)
    if offer:
        return _with_sale_price(offer), detail, "product_items"

    return None, detail, None


def _with_sale_price(offer: dict[str, Any]) -> dict[str, Any]:
    """Anexa o preço público vigente sem impedir a coleta em caso de bloqueio."""
    enriched = dict(offer)
    item_id = offer.get("item_id") or offer.get("id")
    enriched["_offer_price"] = offer.get("price")
    if not item_id:
        return enriched
    sale_price = get_item_sale_price(str(item_id))
    if sale_price:
        enriched["_sale_price_amount"] = sale_price.get("amount")
        enriched["_sale_price_regular_amount"] = sale_price.get("regular_amount")
        enriched["_sale_price_currency"] = sale_price.get("currency_id")
        enriched["_sale_price_reference_date"] = sale_price.get("reference_date")
    return enriched


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
    best_seller_category: str | None = None,
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
    attributes = detail.get("attributes") or product.get("attributes") or []
    brand_attribute = next(
        (attribute for attribute in attributes if attribute.get("id") == "BRAND"),
        {},
    )
    item["brand"] = brand_attribute.get("value_name")
    first_picture = next(iter(item["pictures"]), {})
    item["thumbnail"] = first_picture.get("secure_url") or first_picture.get("url")
    item["_collection_position"] = search_position
    item["_best_seller_position"] = best_seller_position
    item["_best_seller_category"] = best_seller_category
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
    restrict_to_dominant_domain: bool = True,
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
        if (
            restrict_to_dominant_domain
            and dominant_domain
            and product.get("domain_id") != dominant_domain
        ):
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
    entity_id = entry.get("id")
    entity_type = entry.get("type")
    if not entity_id:
        return None, "without_offer"
    try:
        if entity_type == "PRODUCT":
            offer, detail, offer_source = _offer_for_product(entity_id)
            if not offer or not offer_source:
                return None, "without_offer"
            product = {
                "id": entity_id,
                "name": detail.get("name"),
                "domain_id": detail.get("domain_id"),
            }
        else:
            item_id = entity_id if entity_type == "ITEM" else get_user_product_item_id(entity_id)
            if not item_id:
                return None, "without_offer"
            listing = get_item(item_id)
            offer = _with_sale_price({**listing, "item_id": item_id})
            detail = {
                "name": listing.get("title") or listing.get("family_name"),
                "domain_id": listing.get("domain_id"),
                "attributes": listing.get("attributes") or [],
                "pictures": listing.get("pictures") or [],
                "permalink": listing.get("permalink"),
            }
            catalog_product_id = listing.get("catalog_product_id") or ""
            product = {
                "id": catalog_product_id,
                "name": detail.get("name"),
                "domain_id": detail.get("domain_id"),
            }
            offer_source = "ranking_item" if entity_type == "ITEM" else "ranking_user_product"
        item = _build_item(
            product_id=entity_id if entity_type == "PRODUCT" else catalog_product_id,
            product=product,
            detail=detail,
            offer=offer,
            offer_source=offer_source,
            query=entry.get("_query") or query,
            collected_at=collected_at,
            best_seller_position=entry.get("position"),
            best_seller_category=entry.get("_category_id"),
        )
        item["_ranked_entity_type"] = entity_type
        return item, offer_source
    except Exception:
        return None, "without_offer"


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
        "ranking_product_entities": 0,
        "ranking_item_entities": 0,
        "ranking_user_product_entities": 0,
        "parallel_workers": MAX_WORKERS,
    }

    candidates: list[tuple[dict[str, Any], str, str]] = []
    for entry in ranked_products:
        entity_type = entry.get("type")
        if entity_type not in {"PRODUCT", "ITEM", "USER_PRODUCT"}:
            continue
        entity_id = entry.get("id")
        if not entity_id:
            continue
        ranking_stats["ranking_products"] += 1
        ranking_stats[f"ranking_{entity_type.lower()}_entities"] += 1
        if entity_id in existing:
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
                elif status in {"product_items", "ranking_item", "ranking_user_product"}:
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


def get_item(item_id: str) -> dict[str, Any]:
    response = meli_request(
        "GET", f"{BASE_URL}/items/{quote_plus(item_id)}", timeout=20
    )
    response.raise_for_status()
    return response.json()


def get_user_product_item_id(user_product_id: str) -> str | None:
    response = meli_request(
        "GET", f"{BASE_URL}/user-products/{quote_plus(user_product_id)}", timeout=20
    )
    response.raise_for_status()
    user_product = response.json()
    seller_id = user_product.get("user_id")
    if not seller_id:
        return None
    search = meli_request(
        "GET",
        f"{BASE_URL}/users/{quote_plus(str(seller_id))}/items/search",
        params={"user_product_id": user_product_id},
        timeout=20,
    )
    search.raise_for_status()
    return next(iter(search.json().get("results") or []), None)


def get_item_sale_price(item_id: str) -> dict[str, Any] | None:
    """Consulta o preço público vencedor no canal marketplace.

    Alguns tokens não têm acesso a preços de itens de terceiros. Nesses casos,
    a coleta continua com o preço já presente na oferta do catálogo.
    """
    try:
        response = meli_request(
            "GET",
            f"{BASE_URL}/items/{quote_plus(item_id)}/sale_price",
            params={"context": "channel_marketplace"},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extrai somente os campos úteis para o MVP."""
    shipping = item.get("shipping") or {}
    offer_price = item.get("_offer_price", item.get("price"))
    sale_price = item.get("_sale_price_amount")
    sale_regular_price = item.get("_sale_price_regular_amount")
    price = sale_price if sale_price is not None else offer_price
    standard_price = sale_regular_price or offer_price
    original_price = item.get("original_price")
    if standard_price and price and standard_price > price:
        original_price = standard_price

    discount = None
    if original_price and price and original_price > price:
        discount = round((1 - price / original_price) * 100, 2)

    return {
        "collected_at": item.get("_collected_at"),
        "query": item.get("_query"),
        "discovery_source": item.get("_discovery_source") or "Pesquisa",
        "position": item.get("_collection_position"),
        "catalog_product_id": item.get("catalog_product_id"),
        "domain_id": item.get("domain_id"),
        "item_id": item.get("id"),
        "offer_source": item.get("offer_source"),
        "title": item.get("title"),
        "brand": item.get("brand"),
        "category_id": item.get("category_id"),
        "seller_id": item.get("seller_id"),
        "price": price,
        "standard_price": standard_price,
        "promotional_price": price if standard_price and price and price < standard_price else None,
        "price_source": "sale_price_api" if sale_price is not None else "catalog_offer",
        "price_reference_date": item.get("_sale_price_reference_date"),
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
        "best_seller_category": item.get("_best_seller_category"),
        "ranked_entity_type": item.get("_ranked_entity_type"),
    }
