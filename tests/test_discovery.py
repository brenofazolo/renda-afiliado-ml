from __future__ import annotations

import unittest

from app.collector import _build_item, normalize_item
from app.service import brand_matches, filter_brand_items


class BrandDiscoveryTest(unittest.TestCase):
    def test_catalog_brand_attribute_is_preserved(self) -> None:
        item = _build_item(
            product_id="MLB1",
            product={"name": "Coffee"},
            detail={"attributes": [{"id": "BRAND", "value_name": "O Boticário"}]},
            offer={"item_id": "MLB2", "price": 100},
            offer_source="buy_box_winner",
            query="O Boticário",
            collected_at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(normalize_item(item)["brand"], "O Boticário")

    def test_matches_official_brand_ignoring_article_and_accent(self) -> None:
        self.assertTrue(brand_matches({"brand": "Boticário"}, "O Boticário"))

    def test_rejects_another_brand_even_in_same_category(self) -> None:
        item = {
            "brand": "Jequiti",
            "title": "Perfume Colônia Miniatura Cebolinha Jequiti",
        }
        self.assertFalse(brand_matches(item, "O Boticário"))

    def test_uses_title_only_when_brand_attribute_is_missing(self) -> None:
        self.assertTrue(
            brand_matches({"title": "Kit Presente Coffee O Boticário"}, "O Boticário")
        )

    def test_brand_filter_removes_other_brands_and_reports_count(self) -> None:
        kept, removed = filter_brand_items(
            [
                {"brand": "O Boticário", "title": "Coffee"},
                {"brand": "Jequiti", "title": "Cebolinha"},
            ],
            "O Boticário",
        )
        self.assertEqual([item["title"] for item in kept], ["Coffee"])
        self.assertEqual(removed, 1)


if __name__ == "__main__":
    unittest.main()
