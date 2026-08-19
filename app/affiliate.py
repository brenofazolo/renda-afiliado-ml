from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "config" / "affiliate_commissions.json"


def load_rules() -> list[dict[str, Any]]:
    with RULES_FILE.open(encoding="utf-8") as file:
        return json.load(file).get("rules", [])


def find_commission(category_path: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Procura uma regra por trecho da hierarquia da categoria.

    Exemplo de regra futura:
    {"match": "Beleza", "direct_percent": 16, "indirect_percent": 8}
    """
    normalized_path = category_path.casefold()
    for rule in rules:
        match = str(rule.get("match", "")).casefold().strip()
        if match and match in normalized_path:
            return rule
    return None


def estimate_commission(price: float | None, rule: dict[str, Any] | None) -> dict[str, float | None]:
    if not price or not rule:
        return {
            "affiliate_direct_percent": None,
            "affiliate_indirect_percent": None,
            "affiliate_direct_value": None,
            "affiliate_indirect_value": None,
        }

    direct = rule.get("direct_percent")
    indirect = rule.get("indirect_percent")

    return {
        "affiliate_direct_percent": direct,
        "affiliate_indirect_percent": indirect,
        "affiliate_direct_value": round(price * direct / 100, 2) if direct is not None else None,
        "affiliate_indirect_value": round(price * indirect / 100, 2) if indirect is not None else None,
    }
