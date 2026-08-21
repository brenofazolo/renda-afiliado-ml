from __future__ import annotations

import time
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from .affiliate import estimate_commission, find_commission, load_rules
from .collector import collect_ranked_products, normalize_item, search_items
from .marketplace import category_path, get_category, get_category_best_sellers
from .scoring import calculate_score


def marketplace_search_url(title: str | None) -> str | None:
    if not title:
        return None
    return f"https://lista.mercadolivre.com.br/{quote_plus(title)}"


def catalog_product_url(product_id: str | None, site_id: str = "MLB") -> str | None:
    """Monta a rota oficial da página de produto quando a API omite permalink."""
    if not product_id:
        return None
    domains = {
        "MLB": "www.mercadolivre.com.br",
        "MLA": "www.mercadolibre.com.ar",
        "MLM": "www.mercadolibre.com.mx",
    }
    domain = domains.get(site_id)
    if not domain:
        return None
    return f"https://{domain}/p/{quote_plus(product_id)}"


def collect_opportunities(query: str, limit: int = 20, site_id: str = "MLB") -> dict[str, Any]:
    """Executa o pipeline do MVP e retorna resultados e diagnóstico da coleta."""
    started_at = datetime.now().astimezone()
    started_perf = time.perf_counter()
    timings: dict[str, float] = {}

    stage = time.perf_counter()
    collection_stats: dict[str, Any] = {}
    raw_search_items = search_items(query, limit, site_id, collection_stats)
    search_results = [normalize_item(item) for item in raw_search_items]
    timings["busca_e_ofertas"] = time.perf_counter() - stage

    rules = load_rules()
    category_cache: dict[str, dict] = {}

    def enrich_category(item: dict[str, Any]) -> None:
        category_id = item.get("category_id")
        if category_id:
            if category_id not in category_cache:
                category_cache[category_id] = get_category(category_id)
            category = category_cache[category_id]
            item["category_name"] = category.get("name")
            item["category_path"] = category_path(category)
        else:
            item["category_name"] = None
            item["category_path"] = None

    stage = time.perf_counter()
    for item in search_results:
        enrich_category(item)
    timings["categorias_busca"] = time.perf_counter() - stage

    category_counts = Counter(
        item.get("category_id") for item in search_results if item.get("category_id")
    )
    dominant_category_id = category_counts.most_common(1)[0][0] if category_counts else None

    stage = time.perf_counter()
    best_sellers: list[dict[str, Any]] = []
    ranking_stats: dict[str, Any] = {}
    if dominant_category_id:
        best_sellers = get_category_best_sellers(dominant_category_id, site_id)
    timings["ranking"] = time.perf_counter() - stage

    ranking_map = {
        entry.get("id"): entry.get("position")
        for entry in best_sellers
        if entry.get("type") == "PRODUCT" and entry.get("id")
    }
    existing_product_ids = {
        item.get("catalog_product_id")
        for item in search_results
        if item.get("catalog_product_id")
    }

    stage = time.perf_counter()
    raw_ranked_items = collect_ranked_products(
        best_sellers,
        query=query,
        existing_product_ids=existing_product_ids,
        stats=ranking_stats,
    )
    ranked_results = [normalize_item(item) for item in raw_ranked_items]
    timings["ofertas_ranking"] = time.perf_counter() - stage

    stage = time.perf_counter()
    for item in ranked_results:
        enrich_category(item)
    timings["categorias_ranking"] = time.perf_counter() - stage

    items = search_results + ranked_results
    dominant_category_label = None
    if dominant_category_id and dominant_category_id in category_cache:
        dominant_category_label = category_path(category_cache[dominant_category_id])

    stage = time.perf_counter()
    for item in items:
        ranking_position = ranking_map.get(item.get("catalog_product_id"))
        item["best_seller_position"] = ranking_position
        item["best_seller_category"] = dominant_category_id if ranking_position else None
        rule = find_commission(item.get("category_path") or "", rules)
        item.update(estimate_commission(item.get("price"), rule))
        item["commission_rule"] = rule.get("label") if rule else None
        score, components = calculate_score(item, len(items))
        item["marketplace_score"] = score
        item["score_status"] = "provisório"
        item["score_components"] = "; ".join(
            f"{key}={value}" for key, value in components.items()
        )
        item["search_url"] = marketplace_search_url(item.get("title"))
        item["catalog_url"] = catalog_product_url(
            item.get("catalog_product_id"), site_id
        )
    items.sort(key=lambda item: item["marketplace_score"], reverse=True)
    timings["comissao_e_score"] = time.perf_counter() - stage

    finished_at = datetime.now().astimezone()
    return {
        "query": query,
        "limit": limit,
        "site_id": site_id,
        "items": items,
        "collection_stats": collection_stats,
        "ranking_stats": ranking_stats,
        "ranking_count": len(ranking_map),
        "dominant_category_label": dominant_category_label,
        "search_results_count": len(search_results),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": time.perf_counter() - started_perf,
        "timings": timings,
    }
