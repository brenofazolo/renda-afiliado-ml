from __future__ import annotations

import time
import unicodedata
from collections import Counter
from datetime import datetime
from math import ceil
from typing import Any
from urllib.parse import quote_plus

from .affiliate import estimate_commission, find_commission, load_rules
from .collector import collect_ranked_products, normalize_item, search_items
from .marketplace import category_path, get_category, get_category_best_sellers, get_trends
from .scoring import calculate_score, score_confidence

BRAND_STOP_WORDS = {"a", "as", "da", "das", "de", "do", "dos", "e", "o", "os"}
BROAD_QUERY_EXPANSIONS = {
    "ferramentas": [
        "furadeira e parafusadeira",
        "jogo de ferramentas",
        "serra elétrica",
        "chave de impacto",
    ],
    "perfumes": [
        "perfume feminino",
        "perfume masculino",
        "kit perfume",
        "body splash",
    ],
    "casa cozinha": [
        "utensílios de cozinha",
        "eletroportáteis para cozinha",
        "organização de cozinha",
        "panelas e frigideiras",
    ],
    "beleza autocuidado": [
        "skincare",
        "cuidados com cabelo",
        "maquiagem",
        "higiene pessoal",
    ],
}
POTENTIAL_DISCOVERY_QUERIES = [
    "air fryer",
    "perfumes",
    "ferramentas",
    "smartwatch",
    "beleza e autocuidado",
    "casa e cozinha",
]
POTENTIAL_INTENT_MARKERS = {
    "air fryer": {"air fryer", "fritadeira", "air fryers"},
    "perfumes": {"perfume", "perfumaria", "fragrance", "cologne", "body splash"},
    "ferramentas": {
        "ferramenta", "tool", "drill", "furadeira", "parafusadeira", "serra",
        "esmerilhadeira", "solda", "lavadora de alta pressao",
    },
    "smartwatch": {"smartwatch", "relogio inteligente", "smart watch", "wearable"},
    "beleza autocuidado": {
        "beleza e cuidado pessoal", "beauty", "skincare", "maquiagem", "cabelo",
        "higiene pessoal", "cosmetico", "perfume",
    },
    "casa cozinha": {
        "casa moveis", "cozinha", "kitchen", "cookware", "eletrodomestico",
        "utensilio", "panela", "organizacao da casa",
    },
}


def _search_tokens(value: str | None) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value or "")
    plain = "".join(character for character in normalized if not unicodedata.combining(character))
    return [
        token
        for token in "".join(character if character.isalnum() else " " for character in plain.casefold()).split()
        if token not in BRAND_STOP_WORDS
    ]


def brand_matches(item: dict[str, Any], requested_brand: str) -> bool:
    """Confirma a marca pelo atributo oficial e usa o título como fallback."""
    requested = _search_tokens(requested_brand)
    if not requested:
        return False
    candidate = _search_tokens(item.get("brand") or item.get("title"))
    return all(token in candidate for token in requested)


def filter_brand_items(
    items: list[dict[str, Any]], requested_brand: str
) -> tuple[list[dict[str, Any]], int]:
    kept = [item for item in items if brand_matches(item, requested_brand)]
    return kept, len(items) - len(kept)


def broad_query_expansions(query: str) -> list[str]:
    return BROAD_QUERY_EXPANSIONS.get(" ".join(_search_tokens(query)), [])


def commercially_relevant(item: dict[str, Any]) -> bool:
    """Valida se o produto respeita a intenção que originou sua descoberta."""
    query_key = " ".join(_search_tokens(item.get("query")))
    title = " ".join(_search_tokens(item.get("title")))
    category = " ".join(_search_tokens(item.get("category_path")))
    domain = " ".join(_search_tokens(item.get("domain_id")))
    category_context = f"{category} {domain}"
    markers = POTENTIAL_INTENT_MARKERS.get(query_key)
    if markers:
        return any(
            " ".join(_search_tokens(marker)) in category_context
            for marker in markers
        )
    query_tokens = set(_search_tokens(item.get("query")))
    if not query_tokens:
        return True
    candidate_tokens = set(_search_tokens(f"{title} {category} {domain}"))
    required = max(1, ceil(len(query_tokens) * 0.6))
    return len(query_tokens & candidate_tokens) >= required


def _merge_collection_stats(target: dict[str, Any], extra: dict[str, Any]) -> None:
    for key in (
        "products_found",
        "filtered_by_domain",
        "with_buy_box",
        "via_product_items",
        "without_offer",
        "analyzed",
    ):
        target[key] = int(target.get(key, 0)) + int(extra.get(key, 0))


def apply_commercial_filters(
    items: list[dict[str, Any]],
    brand_filter: str | None = None,
    max_price: float | None = None,
    min_commission: float | None = None,
    official_store_only: bool = False,
    sort_by: str = "potential",
    limit: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, int], str]:
    stats = {
        "before_commercial_filters": len(items),
        "brand": 0,
        "max_price": 0,
        "min_commission": 0,
        "official_store": 0,
    }
    filtered: list[dict[str, Any]] = []
    for item in items:
        if brand_filter and not brand_matches(item, brand_filter):
            stats["brand"] += 1
        elif max_price is not None and (item.get("price") is None or item["price"] > max_price):
            stats["max_price"] += 1
        elif min_commission is not None and (
            item.get("affiliate_direct_value") is None
            or item["affiliate_direct_value"] < min_commission
        ):
            stats["min_commission"] += 1
        elif official_store_only and not item.get("official_store_id"):
            stats["official_store"] += 1
        else:
            filtered.append(item)
    if sort_by == "commission":
        filtered.sort(key=lambda item: item.get("affiliate_direct_value") or 0, reverse=True)
    elif sort_by == "bestseller":
        filtered.sort(key=lambda item: (item.get("best_seller_position") is None, item.get("best_seller_position") or 9999))
    elif sort_by == "price":
        filtered.sort(key=lambda item: item.get("price") if item.get("price") is not None else float("inf"))
    else:
        sort_by = "potential"
        filtered.sort(key=lambda item: item.get("potential_score") or 0, reverse=True)
    return filtered[:limit], stats, sort_by


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


def collect_opportunities(
    query: str,
    limit: int = 20,
    site_id: str = "MLB",
    search_mode: str = "product",
    category_id: str | None = None,
    brand_filter: str | None = None,
    max_price: float | None = None,
    min_commission: float | None = None,
    official_store_only: bool = False,
    sort_by: str = "potential",
) -> dict[str, Any]:
    """Executa o pipeline do MVP e retorna resultados e diagnóstico da coleta."""
    started_at = datetime.now().astimezone()
    started_perf = time.perf_counter()
    timings: dict[str, float] = {}

    stage = time.perf_counter()
    collection_stats: dict[str, Any] = {}
    selected_category = get_category(category_id) if category_id else None
    general_potential = search_mode == "potential" and not query and not category_id
    broad_discovery = general_potential or (
        search_mode in {"category", "niche"} and not category_id
    )
    raw_search_items: list[dict[str, Any]] = []
    if general_potential:
        try:
            trend_queries = [
                entry.get("keyword", "").strip()
                for entry in get_trends(site_id)[:4]
                if entry.get("keyword", "").strip()
            ]
        except Exception:
            trend_queries = []
        seed_queries = (
            [(value, "Tendência") for value in trend_queries]
            + [(value, "Radar base") for value in POTENTIAL_DISCOVERY_QUERIES]
        )

        def collect_potential_pool(per_seed_limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            pool_stats: dict[str, Any] = {
                "products_found": 0, "dominant_domain": None,
                "filtered_by_domain": 0, "with_buy_box": 0,
                "via_product_items": 0, "without_offer": 0, "analyzed": 0,
            }
            pool: list[dict[str, Any]] = []
            known_product_ids: set[str] = set()
            for discovery_query, discovery_source in seed_queries:
                seed_stats: dict[str, Any] = {}
                seed_items = search_items(
                    discovery_query,
                    per_seed_limit,
                    site_id,
                    seed_stats,
                    restrict_to_dominant_domain=True,
                )
                _merge_collection_stats(pool_stats, seed_stats)
                for item in seed_items:
                    item["_discovery_source"] = discovery_source
                    product_id = item.get("catalog_product_id")
                    if product_id and product_id in known_product_ids:
                        continue
                    if product_id:
                        known_product_ids.add(product_id)
                    pool.append(item)
            return pool, pool_stats

        # O limite pedido representa resultados finais. Na descoberta geral precisamos
        # examinar uma base maior porque ofertas inacessíveis e produtos repetidos são
        # removidos antes da ordenação pelo potencial.
        per_query_limit = min(
            12,
            max(4, ceil((limit * 2) / len(seed_queries))),
        )
        raw_search_items, collection_stats = collect_potential_pool(per_query_limit)
        collection_stats["trend_queries"] = trend_queries
        collection_stats["trends_available"] = bool(trend_queries)

        # Uma única segunda coleta, com teto seguro, evita que filtros restritivos
        # (especialmente loja oficial) deixem a tela quase vazia por falta de base.
        filters_are_restrictive = any(
            (brand_filter, max_price is not None, min_commission is not None, official_store_only)
        )
        normalized_preview = [normalize_item(item) for item in raw_search_items]
        preview_qualified = sum(
            1 for item in normalized_preview
            if (not brand_filter or brand_matches(item, brand_filter))
            and (max_price is None or (item.get("price") is not None and item["price"] <= max_price))
            and (not official_store_only or item.get("official_store_id"))
        )
        minimum_useful_pool = min(limit, 8)
        if (
            filters_are_restrictive
            and (min_commission is not None or preview_qualified < minimum_useful_pool)
            and per_query_limit < 12
        ):
            initial_candidates = collection_stats.get("products_found", len(raw_search_items))
            expanded_seed_limit = min(12, max(8, per_query_limit * 2))
            raw_search_items, collection_stats = collect_potential_pool(expanded_seed_limit)
            collection_stats["auto_expanded"] = True
            collection_stats["initial_candidates"] = initial_candidates
            collection_stats["trend_queries"] = trend_queries
            collection_stats["trends_available"] = bool(trend_queries)
        else:
            collection_stats["auto_expanded"] = False
    elif not category_id:
        raw_search_items = search_items(
            query, limit, site_id, collection_stats,
            restrict_to_dominant_domain=not broad_discovery,
        )
    if category_id:
        collection_stats.update(
            products_found=0,
            dominant_domain=None,
            filtered_by_domain=0,
            with_buy_box=0,
            via_product_items=0,
            without_offer=0,
            analyzed=0,
        )
    search_results = [normalize_item(item) for item in raw_search_items]
    fallback_queries: list[str] = []
    fallback_added = 0
    minimum_broad_results = min(limit, 8)
    expansions = broad_query_expansions(query) if broad_discovery else []
    if len(search_results) < minimum_broad_results and expansions:
        known_ids = {
            item.get("catalog_product_id") for item in search_results if item.get("catalog_product_id")
        }
        per_expansion_limit = min(10, max(5, limit // len(expansions)))
        for expansion in expansions:
            if len(search_results) >= limit:
                break
            extra_stats: dict[str, Any] = {}
            extra_raw_items = search_items(
                expansion,
                per_expansion_limit,
                site_id,
                extra_stats,
                restrict_to_dominant_domain=False,
            )
            fallback_queries.append(expansion)
            _merge_collection_stats(collection_stats, extra_stats)
            for item in (normalize_item(raw) for raw in extra_raw_items):
                product_id = item.get("catalog_product_id")
                if product_id and product_id in known_ids:
                    continue
                if product_id:
                    known_ids.add(product_id)
                search_results.append(item)
                fallback_added += 1
                if len(search_results) >= limit:
                    break
        domain_counts_after_expansion = Counter(
            item.get("domain_id") for item in search_results if item.get("domain_id")
        )
        collection_stats["dominant_domain"] = (
            domain_counts_after_expansion.most_common(1)[0][0]
            if domain_counts_after_expansion
            else None
        )
        collection_stats["analyzed"] = len(search_results)
    brand_filtered_search = 0
    if search_mode == "brand":
        search_results, brand_filtered_search = filter_brand_items(search_results, query)
    timings["busca_e_ofertas"] = time.perf_counter() - stage

    rules = load_rules()
    category_cache: dict[str, dict] = {}
    if category_id and selected_category:
        category_cache[category_id] = selected_category

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
    if general_potential:
        relevant_results = [item for item in search_results if commercially_relevant(item)]
        collection_stats["irrelevant"] = len(search_results) - len(relevant_results)
        search_results = relevant_results
        collection_stats["analyzed"] = len(search_results)
    timings["categorias_busca"] = time.perf_counter() - stage

    category_counts = Counter(
        item.get("category_id") for item in search_results if item.get("category_id")
    )
    dominant_category_id = category_id or (
        category_counts.most_common(1)[0][0] if category_counts else None
    )

    stage = time.perf_counter()
    best_sellers: list[dict[str, Any]] = []
    ranking_stats: dict[str, Any] = {}
    if dominant_category_id and not broad_discovery:
        best_sellers = get_category_best_sellers(dominant_category_id, site_id)
        if category_id:
            collection_stats["products_found"] = len(best_sellers)
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
    brand_filtered_ranking = 0
    if search_mode == "brand":
        ranked_results, brand_filtered_ranking = filter_brand_items(ranked_results, query)
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
        item["potential_score"] = score
        item["score_status"] = "provisório"
        item["score_confidence"] = score_confidence(item)
        item["score_components"] = "; ".join(
            f"{key}={value}" for key, value in components.items()
        )
        item["search_url"] = marketplace_search_url(item.get("title"))
        item["catalog_url"] = catalog_product_url(
            item.get("catalog_product_id"), site_id
        )
    if search_mode == "potential":
        sort_by = "potential"
    items, filter_stats, sort_by = apply_commercial_filters(
        items,
        brand_filter=brand_filter,
        max_price=max_price,
        min_commission=min_commission,
        official_store_only=official_store_only,
        sort_by=sort_by,
        limit=limit,
    )
    timings["comissao_e_score"] = time.perf_counter() - stage

    finished_at = datetime.now().astimezone()
    return {
        "query": query,
        "search_mode": search_mode,
        "category_id": category_id,
        "selected_category_label": category_path(selected_category) if selected_category else None,
        "limit": limit,
        "site_id": site_id,
        "items": items,
        "collection_stats": collection_stats,
        "ranking_stats": ranking_stats,
        "ranking_count": len(ranking_map),
        "dominant_category_label": dominant_category_label,
        "search_results_count": len(search_results),
        "brand_filtered_count": brand_filtered_search + brand_filtered_ranking,
        "broad_discovery": broad_discovery,
        "general_potential": general_potential,
        "fallback_queries": fallback_queries,
        "fallback_added": fallback_added,
        "filters": {
            "brand": brand_filter,
            "max_price": max_price,
            "min_commission": min_commission,
            "official_store_only": official_store_only,
            "sort_by": sort_by,
        },
        "filter_stats": filter_stats,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": time.perf_counter() - started_perf,
        "timings": timings,
    }
