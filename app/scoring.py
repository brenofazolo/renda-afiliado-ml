from __future__ import annotations

from typing import Any


def _clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def calculate_score(item: dict[str, Any], total_results: int) -> tuple[float, dict[str, float]]:
    """Calcula um score inicial de marketplace, não de afiliado.

    Importante: comissão e elegibilidade de afiliado não entram aqui porque
    não são assumidas como dados públicos do anúncio.
    """
    position = item.get("position") or total_results
    position_score = _clamp(100 * (1 - (position - 1) / max(total_results, 1)))

    discount = item.get("discount_percent")
    discount_score = _clamp(float(discount or 0) * 2.5)

    price = item.get("price")
    # Faixa de preço intermediária recebe um pequeno bônus heurístico.
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

    shipping_score = 100 if item.get("free_shipping") else 40
    quality_score = 100 if item.get("condition") in {"new", "Novo", "new_item"} else 60
    visual_score = _clamp((item.get("pictures_count") or 0) * 20)
    store_score = 100 if item.get("official_store_id") else 50

    components = {
        "relevancia_busca": position_score,
        "atratividade_preco": (discount_score * 0.6) + (price_score * 0.4),
        "frete": shipping_score,
        "condicao": quality_score,
        "potencial_visual": visual_score,
        "loja_oficial": store_score,
    }

    score = (
        components["relevancia_busca"] * 0.30
        + components["atratividade_preco"] * 0.25
        + components["frete"] * 0.10
        + components["condicao"] * 0.10
        + components["potencial_visual"] * 0.10
        + components["loja_oficial"] * 0.15
    )

    return round(score, 2), {k: round(v, 2) for k, v in components.items()}
