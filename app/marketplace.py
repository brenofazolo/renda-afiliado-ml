from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from .token_manager import meli_request

BASE_URL = "https://api.mercadolibre.com"


def get_category(category_id: str) -> dict[str, Any]:
    response = meli_request(
        "GET",
        f"{BASE_URL}/categories/{quote_plus(category_id)}",
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_best_seller_position(product_id: str, site_id: str = "MLB") -> dict[str, Any] | None:
    """Consulta a posição do produto no ranking de mais vendidos.

    A API retorna 404 quando o produto não está no top 20 de nenhuma categoria.
    Nesse caso, retornamos None e seguimos normalmente.
    """
    response = meli_request(
        "GET",
        f"{BASE_URL}/highlights/{site_id}/product/{quote_plus(product_id)}",
        timeout=20,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def get_category_best_sellers(category_id: str, site_id: str = "MLB") -> list[dict[str, Any]]:
    """Retorna os até 20 itens/produtos mais vendidos da categoria."""
    response = meli_request(
        "GET",
        f"{BASE_URL}/highlights/{site_id}/category/{quote_plus(category_id)}",
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("content", [])


def category_path(category: dict[str, Any]) -> str:
    path = category.get("path_from_root") or []
    return " > ".join(node.get("name", "") for node in path if node.get("name"))
