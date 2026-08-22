from __future__ import annotations

import unittest
from unittest.mock import patch

from app.collector import _collect_ranked_candidate, normalize_item


LISTING = {
    "id": "MLB123",
    "title": "Fone Bluetooth",
    "category_id": "MLB1",
    "domain_id": "MLB-HEADPHONES",
    "catalog_product_id": "MLB-PRODUCT-1",
    "price": 99.9,
    "currency_id": "BRL",
    "condition": "new",
    "pictures": [{"secure_url": "https://example.com/fone.jpg"}],
    "attributes": [{"id": "BRAND", "value_name": "Marca"}],
    "permalink": "https://example.com/item",
}


class MixedRankingCollectorTest(unittest.TestCase):
    @patch("app.collector.get_item_sale_price", return_value=None)
    @patch("app.collector.get_item", return_value=LISTING)
    def test_collects_item_ranking(self, _get_item, _sale_price) -> None:
        raw, status = _collect_ranked_candidate(({
            "id": "MLB123", "type": "ITEM", "position": 2,
            "_category_id": "MLB1", "_query": "fone bluetooth",
        }, "", "2026-01-01T00:00:00Z"))
        assert raw
        item = normalize_item(raw)
        self.assertEqual(status, "ranking_item")
        self.assertEqual(item["item_id"], "MLB123")
        self.assertEqual(item["best_seller_position"], 2)
        self.assertEqual(item["best_seller_category"], "MLB1")

    @patch("app.collector.get_item_sale_price", return_value=None)
    @patch("app.collector.get_item", return_value=LISTING)
    @patch("app.collector.get_user_product_item_id", return_value="MLB123")
    def test_resolves_user_product_to_item(
        self, _resolve, _get_item, _sale_price
    ) -> None:
        raw, status = _collect_ranked_candidate(({
            "id": "MLBU456", "type": "USER_PRODUCT", "position": 3,
            "_category_id": "MLB1", "_query": "fone bluetooth",
        }, "", "2026-01-01T00:00:00Z"))
        assert raw
        item = normalize_item(raw)
        self.assertEqual(status, "ranking_user_product")
        self.assertEqual(item["item_id"], "MLB123")
        self.assertEqual(item["ranked_entity_type"], "USER_PRODUCT")


if __name__ == "__main__":
    unittest.main()
