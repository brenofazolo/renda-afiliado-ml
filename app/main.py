from __future__ import annotations

import argparse
import csv
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv

from .affiliate import estimate_commission, find_commission, load_rules
from .collector import collect_ranked_products, normalize_item, search_items
from .marketplace import category_path, get_category, get_category_best_sellers
from .scoring import calculate_score

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_FILE = DATA_DIR / "oportunidades.csv"


def _format_brl(value: float | int | None) -> str:
    if value is None:
        return "n/d"
    formatted = f"{value:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {formatted}"


def _format_score(value: float | int) -> str:
    return f"{value:.2f}".replace(".", ",")


def _format_percent(value: float | int | None) -> str:
    if value is None:
        return "n/d"
    return f"{value:g}%".replace(".", ",")


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f} s".replace(".", ",")
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)} min {remainder:.2f} s".replace(".", ",")


def _marketplace_search_url(title: str | None) -> str | None:
    """Fallback navegável quando a API não fornece permalink direto.

    Este endereço é deliberadamente rotulado como busca, não como link direto
    da oferta/produto, pois endpoints de itens de terceiros podem estar
    bloqueados para a aplicação.
    """
    if not title:
        return None
    return f"https://lista.mercadolivre.com.br/{quote_plus(title)}"


def main() -> None:
    started_at = datetime.now().astimezone()
    started_perf = time.perf_counter()
    timings: dict[str, float] = {}

    load_dotenv()

    parser = argparse.ArgumentParser(description="Renda Afiliado ML - MVP")
    parser.add_argument("--query", default=os.getenv("MELI_QUERY", "air fryer"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("MELI_LIMIT", "20")))
    parser.add_argument("--site", default=os.getenv("MELI_SITE_ID", "MLB"))
    args = parser.parse_args()

    stage = time.perf_counter()
    collection_stats: dict[str, Any] = {}
    raw_search_items = search_items(args.query, args.limit, args.site, collection_stats)
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
        best_sellers = get_category_best_sellers(dominant_category_id, args.site)
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
        query=args.query,
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
        product_id = item.get("catalog_product_id")
        ranking_position = ranking_map.get(product_id)
        if ranking_position:
            item["best_seller_position"] = ranking_position
            item["best_seller_category"] = dominant_category_id
        else:
            item["best_seller_position"] = None
            item["best_seller_category"] = None

        rule = find_commission(item.get("category_path") or "", rules)
        item.update(estimate_commission(item.get("price"), rule))
        item["commission_rule"] = rule.get("label") if rule else None

        score, components = calculate_score(item, len(items))
        item["marketplace_score"] = score
        item["score_status"] = "provisório"
        item["score_components"] = "; ".join(
            f"{key}={value}" for key, value in components.items()
        )
        item["search_url"] = _marketplace_search_url(item.get("title"))

    items.sort(key=lambda item: item["marketplace_score"], reverse=True)
    timings["comissao_e_score"] = time.perf_counter() - stage

    stage = time.perf_counter()
    DATA_DIR.mkdir(exist_ok=True)
    fieldnames = list(items[0].keys()) if items else ["message"]

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)
    timings["csv"] = time.perf_counter() - stage

    finished_at = datetime.now().astimezone()
    elapsed = time.perf_counter() - started_perf

    print("RELATÓRIO DA COLETA")
    print(f"Data/hora início: {started_at.strftime('%d/%m/%Y %H:%M:%S %z')}")
    print(f"Data/hora fim: {finished_at.strftime('%d/%m/%Y %H:%M:%S %z')}")
    print(f"Tempo total de execução: {_format_duration(elapsed)}")
    print("TEMPO POR ETAPA")
    print(f"  Busca inicial + ofertas: {_format_duration(timings['busca_e_ofertas'])}")
    print(f"  Categorias da busca: {_format_duration(timings['categorias_busca'])}")
    print(f"  Ranking de mais vendidos: {_format_duration(timings['ranking'])}")
    print(f"  Ofertas dos produtos do ranking: {_format_duration(timings['ofertas_ranking'])}")
    print(f"  Categorias do ranking: {_format_duration(timings['categorias_ranking'])}")
    print(f"  Comissão + score: {_format_duration(timings['comissao_e_score'])}")
    print(f"  Gravação CSV: {_format_duration(timings['csv'])}")
    print(f"Consulta: {args.query}")
    print(f"Resultados da busca: {collection_stats.get('products_found', 0)}")
    print(f"Domínio identificado: {collection_stats.get('dominant_domain') or 'n/d'}")
    print(f"Descartados por domínio: {collection_stats.get('filtered_by_domain', 0)}")
    print(
        "Produtos da busca sem oferta acessível pela API: "
        f"{collection_stats.get('without_offer', 0)}"
    )
    print(f"Ofertas válidas vindas da busca: {len(search_results)}")
    print("  Via oferta vencedora: " f"{collection_stats.get('with_buy_box', 0)}")
    print(
        "  Via ofertas associadas ao produto: "
        f"{collection_stats.get('via_product_items', 0)}"
    )
    print(f"Categoria usada no ranking: {dominant_category_label or 'n/d'}")
    print(f"Produtos no TOP de mais vendidos da categoria: {len(ranking_map)}")
    print(
        "  Já presentes entre as ofertas da busca: "
        f"{ranking_stats.get('ranking_duplicates', 0)}"
    )
    print(
        "  Sem oferta acessível pela API: "
        f"{ranking_stats.get('ranking_without_offer', 0)}"
    )
    print(
        "  Novas ofertas válidas adicionadas pelo ranking: "
        f"{ranking_stats.get('ranking_added', 0)}"
    )
    print(f"Pool final de ofertas válidas: {len(items)}")
    print(
        "Presentes no ranking de mais vendidos: "
        f"{sum(1 for item in items if item['best_seller_position'])}"
    )
    print(
        "Com regra de comissão configurada: "
        f"{sum(1 for item in items if item['commission_rule'])}"
    )
    print(f"Arquivo CSV: {OUTPUT_FILE}")
    print(f"\nTOP OPORTUNIDADES: {len(items)}")
    for index, item in enumerate(items[:10], start=1):
        ranking_text = (
            f" | Mais vendidos: #{item['best_seller_position']}"
            if item.get("best_seller_position")
            else ""
        )
        print(
            f"{index:02d}. Score: {_format_score(item['marketplace_score'])} | "
            f"Preço: {_format_brl(item.get('price'))}{ranking_text} | {item['title']}"
        )
        print(
            "    Comissão direta: "
            f"{_format_percent(item.get('affiliate_direct_percent'))} | "
            f"{_format_brl(item.get('affiliate_direct_value'))}"
        )
        print(
            "    Comissão indireta (informativa): "
            f"{_format_percent(item.get('affiliate_indirect_percent'))} | "
            f"{_format_brl(item.get('affiliate_indirect_value'))}"
        )
        if item.get("permalink"):
            print(f"    Link direto do produto: {item['permalink']}")
        else:
            print("    Link direto do produto: n/d")
            print(f"    Busca no Mercado Livre: {item.get('search_url') or 'n/d'}")


if __name__ == "__main__":
    main()
