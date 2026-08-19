from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from dotenv import load_dotenv

from .affiliate import estimate_commission, find_commission, load_rules
from .collector import normalize_item, search_items
from .marketplace import category_path, get_best_seller_position, get_category
from .scoring import calculate_score

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_FILE = DATA_DIR / "oportunidades.csv"


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Renda Afiliado ML - MVP")
    parser.add_argument("--query", default=os.getenv("MELI_QUERY", "air fryer"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("MELI_LIMIT", "20")))
    parser.add_argument("--site", default=os.getenv("MELI_SITE_ID", "MLB"))
    args = parser.parse_args()

    raw_items = search_items(args.query, args.limit, args.site)
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

        best_seller = get_best_seller_position(item["item_id"], args.site)
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

    print(f"Consulta: {args.query}")
    print(f"Produtos analisados: {len(items)}")
    print(f"Produtos no ranking de mais vendidos: {sum(1 for item in items if item['best_seller_position'])}")
    print(f"Produtos com regra de comissão configurada: {sum(1 for item in items if item['commission_rule'])}")
    print(f"Resultado: {OUTPUT_FILE}")
    print("\nTOP 10")
    for index, item in enumerate(items[:10], start=1):
        commission = item.get("affiliate_direct_value")
        commission_text = f"R$ {commission:.2f}" if commission is not None else "n/d"
        print(
            f"{index:02d}. {item['marketplace_score']:>6} | "
            f"Comissão: {commission_text:<10} | {item['title']}"
        )


if __name__ == "__main__":
    main()
