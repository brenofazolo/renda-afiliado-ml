from __future__ import annotations

from typing import Any


def _clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def calculate_score(item: dict[str, Any], total_results: int) -> tuple[float, dict[str, float]]:
    """Score provisório de oportunidade para o MVP.

    O score combina sinais de marketplace e, quando configurada, a comissão
    direta de afiliado. Não representa ainda um modelo estatístico treinado.
    """
    position = item.get("position") or total_results
    search_position_score = _clamp(100 * (1 - (position - 1) / max(total_results, 1)))

    best_seller_position = item.get("best_seller_position")
    if best_seller_position:
        best_seller_score = _clamp(100 * (1 - (best_seller_position - 1) / 19))
    else:
        best_seller_score = 0

    if best_seller_position:
        demand_score = 40 + (best_seller_score * 0.60)
    elif item.get("discovery_source") == "Tendência":
        demand_score = 45 + (search_position_score * 0.15)
    else:
        # Posição na busca é descoberta, não prova de venda.
        demand_score = search_position_score * 0.15

    discount = item.get("discount_percent")
    discount_score = _clamp(float(discount or 0) * 2.5)

    price = item.get("price")
    if price is None:
        price_score = 50
    elif 30 <= price <= 300:
        price_score = 100
    elif price < 30:
        price_score = 70
    elif price <= 700:
        price_score = 75
    else:
        price_score = 50

    price_offer_score = (discount_score * 0.6) + (price_score * 0.4)

    commission = item.get("affiliate_direct_percent")
    commission_score = _clamp(float(commission or 0) / 16 * 100)

    shipping_score = 100 if item.get("free_shipping") else 40
    quality_score = 100 if item.get("condition") in {"new", "Novo", "new_item"} else 60
    visual_score = _clamp((item.get("pictures_count") or 0) * 20)
    store_score = 100 if item.get("official_store_id") else 50

    components = {
        "sinal_demanda": demand_score,
        "preco_oferta": price_offer_score,
        "comissao_afiliado": commission_score,
        "frete": shipping_score,
        "condicao": quality_score,
        "potencial_visual": visual_score,
        "loja_oficial": store_score,
    }

    score = (
        components["sinal_demanda"] * 0.25
        + components["preco_oferta"] * 0.20
        + components["comissao_afiliado"] * 0.15
        + components["frete"] * 0.10
        + components["condicao"] * 0.10
        + components["potencial_visual"] * 0.10
        + components["loja_oficial"] * 0.10
    )

    return round(score, 2), {k: round(v, 2) for k, v in components.items()}


def score_confidence(item: dict[str, Any]) -> str:
    """Indica a força da evidência usada, separada do valor do score."""
    if item.get("best_seller_position"):
        return "alta"
    if item.get("discovery_source") == "Tendência":
        return "média"
    return "baixa"
