from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from dotenv import load_dotenv

from .collector import normalize_item, search_items
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

    for item in items:
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
    print(f"Resultado: {OUTPUT_FILE}")
    print("\nTOP 10")
    for index, item in enumerate(items[:10], start=1):
        print(
            f"{index:02d}. {item['marketplace_score']:>6} | "
            f"R$ {item['price']!s:<10} | {item['title']}"
        )


if __name__ == "__main__":
    main()
