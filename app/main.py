from __future__ import annotations

import argparse
import csv
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .service import collect_opportunities

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


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Renda Afiliado ML - MVP")
    parser.add_argument("--query", default=os.getenv("MELI_QUERY", "air fryer"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("MELI_LIMIT", "20")))
    parser.add_argument("--site", default=os.getenv("MELI_SITE_ID", "MLB"))
    args = parser.parse_args()

    report = collect_opportunities(args.query, args.limit, args.site)
    items = report["items"]
    collection_stats = report["collection_stats"]
    ranking_stats = report["ranking_stats"]
    timings = report["timings"]

    stage = time.perf_counter()
    DATA_DIR.mkdir(exist_ok=True)
    fieldnames = list(items[0].keys()) if items else ["message"]

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)
    timings["csv"] = time.perf_counter() - stage

    started_at = report["started_at"]
    finished_at = report["finished_at"]
    elapsed = report["elapsed_seconds"]

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
    print(f"Ofertas válidas vindas da busca: {report['search_results_count']}")
    print("  Via oferta vencedora: " f"{collection_stats.get('with_buy_box', 0)}")
    print(
        "  Via ofertas associadas ao produto: "
        f"{collection_stats.get('via_product_items', 0)}"
    )
    print(f"Categoria usada no ranking: {report['dominant_category_label'] or 'n/d'}")
    print(f"Produtos no TOP de mais vendidos da categoria: {report['ranking_count']}")
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
