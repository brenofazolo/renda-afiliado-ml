from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .affiliate import estimate_commission, find_commission, load_rules
from .collector import normalize_item, search_items
from .marketplace import category_path, get_best_seller_position, get_category
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


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Renda Afiliado ML - MVP")
    parser.add_argument("--query", default=os.getenv("MELI_QUERY", "air fryer"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("MELI_LIMIT", "20")))
    parser.add_argument("--site", default=os.getenv("MELI_SITE_ID", "MLB"))
    args = parser.parse_args()

    collection_stats: dict[str, Any] = {}
    raw_items = search_items(args.query, args.limit, args.site, collection_stats)
    items = [normalize_item(item) for item in raw_items]
    rules = load_rules()

    category_cache: dict[str, dict] = {}

    for item in items:
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

        best_seller = get_best_seller_position(item["catalog_product_id"], args.site)
        item["best_seller_position"] = best_seller.get("position") if best_seller else None
        item["best_seller_category"] = best_seller.get("label") if best_seller else None

        rule = find_commission(item.get("category_path") or "", rules)
        item.update(estimate_commission(item.get("price"), rule))
        item["commission_rule"] = rule.get("match") if rule else None

        score, components = calculate_score(item, len(items))
        item["marketplace_score"] = score
        item["score_status"] = "provisório"
        item["score_components"] = "; ".join(
            f"{key}={value}" for key, value in components.items()
        )

    items.sort(key=lambda item: item["marketplace_score"], reverse=True)

    DATA_DIR.mkdir(exist_ok=True)
    fieldnames = list(items[0].keys()) if items else ["message"]

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)

    print("RELATÓRIO DA COLETA")
    print(f"Consulta: {args.query}")
    print(f"Resultados da busca: {collection_stats.get('products_found', 0)}")
    print(f"Domínio identificado: {collection_stats.get('dominant_domain') or 'n/d'}")
    print(f"Descartados por domínio: {collection_stats.get('filtered_by_domain', 0)}")
    print(
        "Produtos sem oferta acessível pela API: "
        f"{collection_stats.get('without_offer', 0)}"
    )
    print(f"Ofertas válidas: {len(items)}")
    print(
        "  Via oferta vencedora: "
        f"{collection_stats.get('with_buy_box', 0)}"
    )
    print(
        "  Via ofertas associadas ao produto: "
        f"{collection_stats.get('via_product_items', 0)}"
    )
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
        print(
            f"{index:02d}. Score: {_format_score(item['marketplace_score'])} | "
            f"Preço: {_format_brl(item.get('price'))} | "
            f"Comissão: {_format_brl(item.get('affiliate_direct_value'))} | "
            f"{item['title']}"
        )


if __name__ == "__main__":
    main()
