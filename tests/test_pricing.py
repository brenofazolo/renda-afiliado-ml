from __future__ import annotations

import unittest
from unittest.mock import patch

from app.collector import _with_sale_price, normalize_item


class PricingTest(unittest.TestCase):
    @patch("app.collector.get_item_sale_price")
    def test_public_promotion_becomes_effective_price(self, sale_price_mock) -> None:
        sale_price_mock.return_value = {
            "amount": 239.90,
            "regular_amount": 249.90,
            "currency_id": "BRL",
            "reference_date": "2026-08-21T12:00:00Z",
        }
        enriched = _with_sale_price(
            {"item_id": "MLB123", "price": 249.90, "currency_id": "BRL"}
        )
        normalized = normalize_item(enriched)
        self.assertEqual(normalized["price"], 239.90)
        self.assertEqual(normalized["standard_price"], 249.90)
        self.assertEqual(normalized["promotional_price"], 239.90)
        self.assertEqual(normalized["price_source"], "sale_price_api")
        self.assertEqual(normalized["discount_percent"], 4.0)

    @patch("app.collector.get_item_sale_price", return_value=None)
    def test_catalog_price_remains_safe_fallback(self, _sale_price_mock) -> None:
        enriched = _with_sale_price(
            {"item_id": "MLB123", "price": 249.90, "currency_id": "BRL"}
        )
        normalized = normalize_item(enriched)
        self.assertEqual(normalized["price"], 249.90)
        self.assertEqual(normalized["standard_price"], 249.90)
        self.assertIsNone(normalized["promotional_price"])
        self.assertEqual(normalized["price_source"], "catalog_offer")


if __name__ == "__main__":
    unittest.main()
