from __future__ import annotations

import unittest
from unittest.mock import patch

from app.collector import _build_item, normalize_item
from app.service import (
    apply_commercial_filters,
    brand_matches,
    broad_query_expansions,
    collect_opportunities,
    filter_brand_items,
)


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

    def test_category_mode_preserves_multiple_domains_without_single_ranking(self) -> None:
        with patch("app.service.search_items", return_value=[]) as search:
            report = collect_opportunities(
                "casa e cozinha", 50, "MLB", search_mode="category"
            )
        self.assertEqual(search.call_count, 5)
        self.assertTrue(
            all(not call.kwargs["restrict_to_dominant_domain"] for call in search.call_args_list)
        )
        self.assertTrue(report["broad_discovery"])
        self.assertEqual(report["ranking_count"], 0)
        self.assertEqual(len(report["fallback_queries"]), 4)

    def test_known_broad_categories_have_fallback_queries(self) -> None:
        self.assertIn("jogo de ferramentas", broad_query_expansions("ferramentas"))
        self.assertIn("perfume feminino", broad_query_expansions("Perfumes"))

    def test_exact_category_uses_official_ranking_instead_of_text_search(self) -> None:
        category = {
            "id": "MLB1",
            "name": "Ferramentas",
            "path_from_root": [{"id": "MLB1", "name": "Ferramentas"}],
        }
        with (
            patch("app.service.get_category", return_value=category),
            patch("app.service.get_category_best_sellers", return_value=[]) as ranking,
            patch("app.service.search_items") as text_search,
        ):
            report = collect_opportunities(
                "Ferramentas", 20, "MLB", search_mode="category", category_id="MLB1"
            )
        text_search.assert_not_called()
        ranking.assert_called_once_with("MLB1", "MLB")
        self.assertEqual(report["category_id"], "MLB1")
        self.assertEqual(report["selected_category_label"], "Ferramentas")

    def test_commercial_filters_keep_only_qualified_opportunities(self) -> None:
        items = [
            {"title": "Bosch A", "brand": "Bosch", "price": 200, "affiliate_direct_value": 30, "official_store_id": 1, "potential_score": 70},
            {"title": "Bosch B", "brand": "Bosch", "price": 400, "affiliate_direct_value": 60, "official_store_id": 2, "potential_score": 90},
            {"title": "Outra", "brand": "Outra", "price": 100, "affiliate_direct_value": 40, "official_store_id": 3, "potential_score": 95},
        ]
        filtered, stats, ordering = apply_commercial_filters(
            items,
            brand_filter="Bosch",
            max_price=300,
            min_commission=25,
            official_store_only=True,
            sort_by="potential",
        )
        self.assertEqual([item["title"] for item in filtered], ["Bosch A"])
        self.assertEqual(stats["brand"], 1)
        self.assertEqual(stats["max_price"], 1)
        self.assertEqual(ordering, "potential")

    def test_general_potential_builds_a_multi_query_pool(self) -> None:
        with patch("app.service.search_items", return_value=[]) as search:
            report = collect_opportunities(
                "", 20, "MLB", search_mode="potential", sort_by="commission"
            )
        self.assertEqual(search.call_count, 6)
        self.assertTrue(all(call.args[1] == 7 for call in search.call_args_list))
        self.assertTrue(report["general_potential"])
        self.assertEqual(report["filters"]["sort_by"], "potential")

    def test_general_potential_expands_once_for_restrictive_filters(self) -> None:
        with patch("app.service.search_items", return_value=[]) as search:
            report = collect_opportunities(
                "", 20, "MLB", search_mode="potential", official_store_only=True
            )
        self.assertEqual(search.call_count, 12)
        self.assertEqual([call.args[1] for call in search.call_args_list[:6]], [7] * 6)
        self.assertEqual([call.args[1] for call in search.call_args_list[6:]], [12] * 6)
        self.assertTrue(report["collection_stats"]["auto_expanded"])


if __name__ == "__main__":
    unittest.main()
