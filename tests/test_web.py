from __future__ import annotations

import os
import re
import tempfile
import unittest
from unittest.mock import patch


class WebWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.environ.update(
            WEB_USERNAME="teste",
            WEB_PASSWORD="segredo",
            WEB_SECRET_KEY="chave-segura-de-teste",
            WEB_DATABASE_PATH=os.path.join(cls.temp_dir.name, "pilot.db"),
        )
        from app.web import create_app

        cls.app = create_app()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        self.client = self.app.test_client()
        login = self.client.get("/login")
        match = re.search(r'name="csrf_token" value="([^"]+)', login.get_data(as_text=True))
        assert match
        self.csrf_token = match.group(1)
        response = self.client.post(
            "/login",
            data={
                "username": "teste",
                "password": "segredo",
                "csrf_token": self.csrf_token,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_shortlist_workflow_and_csrf(self) -> None:
        from app.storage import (
            latest_search_run,
            list_selections,
            recent_queries,
            save_search_run,
        )

        self.assertEqual(self.client.post("/selection/save", data={}).status_code, 400)
        response = self.client.post(
            "/selection/save",
            data={
                "csrf_token": self.csrf_token,
                "catalog_product_id": "MLB1",
                "item_id": "MLB2",
                "title": "Produto teste",
                "thumbnail": "https://example.com/a.jpg",
                "price": "99.90",
                "marketplace_score": "88.2",
                "best_seller_position": "2",
                "official_store_id": "123",
                "affiliate_direct_value": "12",
                "affiliate_indirect_value": "6",
                "product_url": "https://example.com/p",
                "search_url": "https://example.com/s",
                "query": "teste",
                "decision": "approved",
            },
        )
        self.assertEqual(response.status_code, 302)
        rows = list_selections()
        self.assertEqual(rows[0]["title"], "Produto teste")
        page = self.client.get("/selections")
        self.assertIn(b"Produto teste", page.data)
        self.assertIn(b"Loja oficial", page.data)

        response = self.client.post(
            f"/selections/{rows[0]['id']}/update",
            data={
                "csrf_token": self.csrf_token,
                "publication_status": "published",
                "affiliate_url": "https://example.com/afiliado",
                "notes": "ok",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list_selections()[0]["publication_status"], "published")
        updated_page = self.client.get("/selections")
        self.assertIn(b"Publicado", updated_page.data)
        self.assertIn(b"Abrir link de afiliado", updated_page.data)

        report = {"items": [{"title": "Produto persistido"}], "elapsed_seconds": 1.2}
        save_search_run("nicho teste", 20, report)
        restored = latest_search_run()
        assert restored
        self.assertEqual(restored["query"], "nicho teste")
        self.assertEqual(restored["report"]["items"][0]["title"], "Produto persistido")
        self.assertIn("nicho teste", recent_queries())

    def test_discovery_mode_and_preset_controls(self) -> None:
        page = self.client.get("/")
        self.assertIn(b'name="search_mode"', page.data)
        self.assertIn("Filtros comerciais".encode(), page.data)
        self.assertIn("Potencial de Renda".encode(), page.data)
        self.assertIn("Máximo de resultados".encode(), page.data)
        self.assertIn(b'value="potential"', page.data)
        self.assertIn(b'navigation.js', page.data)
        self.assertIn(b'rel="icon"', page.data)
        with patch("app.web.collect_opportunities", return_value={}) as collect:
            response = self.client.post(
                "/",
                data={
                    "csrf_token": self.csrf_token,
                    "query": "beleza e autocuidado",
                    "search_mode": "niche",
                    "limit": "12",
                },
            )
        self.assertEqual(response.status_code, 302)
        collect.assert_called_once_with(
            "beleza e autocuidado",
            12,
            "MLB",
            search_mode="niche",
            category_id=None,
            brand_filter=None,
            max_price=None,
            min_commission=None,
            official_store_only=False,
            sort_by="potential",
        )

    def test_help_and_category_tree_pages(self) -> None:
        help_page = self.client.get("/help")
        self.assertEqual(help_page.status_code, 200)
        self.assertIn("Como trabalhar com a ferramenta".encode(), help_page.data)
        with (
            patch(
                "app.web.get_site_categories",
                return_value=[{"id": "MLB1", "name": "Ferramentas"}],
            ),
            patch(
                "app.web.get_category",
                return_value={
                    "id": "MLB1",
                    "name": "Ferramentas",
                    "path_from_root": [{"id": "MLB1", "name": "Ferramentas"}],
                    "children_categories": [{"id": "MLB2", "name": "Ferramentas elétricas"}],
                },
            ),
        ):
            page = self.client.get("/categories?category_id=MLB1")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Consultar esta categoria".encode(), page.data)
        self.assertIn("Ferramentas elétricas".encode(), page.data)

        with (
            patch(
                "app.web.get_site_categories",
                return_value=[{"id": "MLB1", "name": "Ferramentas"}],
            ),
            patch(
                "app.web.get_category",
                return_value={
                    "id": "MLB1",
                    "name": "Ferramentas",
                    "path_from_root": [{"id": "MLB1", "name": "Ferramentas"}],
                    "children_categories": [],
                },
            ),
        ):
            roots = self.client.get("/api/categories")
            children = self.client.get("/api/categories/MLB1")
        self.assertEqual(roots.get_json()[0]["name"], "Ferramentas")
        self.assertEqual(children.get_json()["path"][0]["id"], "MLB1")

    def test_active_login_redirects_and_idle_session_expires(self) -> None:
        self.assertEqual(self.client.get("/login").status_code, 302)
        with self.client.session_transaction() as current_session:
            current_session["last_activity"] = 0
        response = self.client.get("/", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sua sessão expirou".encode(), response.data)
        with self.client.session_transaction() as current_session:
            self.assertFalse(current_session.get("authenticated"))

    def test_legacy_null_category_does_not_break_discover(self) -> None:
        from app.storage import save_search_run

        save_search_run(
            "consulta antiga",
            20,
            {
                "category_id": None,
                "filters": {"brand": None},
                "items": [],
                "collection_stats": {
                    "products_found": 0,
                    "dominant_domain": None,
                    "filtered_by_domain": 0,
                    "without_offer": 0,
                },
                "ranking_stats": {},
                "ranking_count": 0,
                "dominant_category_label": None,
                "elapsed_seconds": 0,
            },
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_general_potential_accepts_empty_query(self) -> None:
        with patch("app.web.collect_opportunities", return_value={}) as collect:
            response = self.client.post(
                "/",
                data={
                    "csrf_token": self.csrf_token,
                    "query": "",
                    "search_mode": "potential",
                    "limit": "20",
                    "sort_by": "commission",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(collect.call_args.args[:3], ("", 20, "MLB"))
        self.assertEqual(collect.call_args.kwargs["search_mode"], "potential")
        self.assertEqual(collect.call_args.kwargs["sort_by"], "potential")

    def test_commercial_filters_are_parsed_and_forwarded(self) -> None:
        with patch("app.web.collect_opportunities", return_value={}) as collect:
            response = self.client.post(
                "/",
                data={
                    "csrf_token": self.csrf_token,
                    "query": "ferramentas",
                    "search_mode": "category",
                    "category_id": "MLB1",
                    "limit": "20",
                    "brand_filter": "Bosch",
                    "max_price": "1.299,90",
                    "min_commission": "25,50",
                    "official_store_only": "on",
                    "sort_by": "commission",
                },
            )
        self.assertEqual(response.status_code, 302)
        collect.assert_called_once_with(
            "ferramentas",
            20,
            "MLB",
            search_mode="category",
            category_id="MLB1",
            brand_filter="Bosch",
            max_price=1299.9,
            min_commission=25.5,
            official_store_only=True,
            sort_by="commission",
        )

    def test_refresh_uses_saved_report_and_clear_removes_it(self) -> None:
        from app.storage import latest_search_run, save_search_run

        save_search_run("persistida", 20, {})
        with patch("app.web.collect_opportunities") as collect:
            refreshed = self.client.get("/")
        self.assertEqual(refreshed.status_code, 200)
        collect.assert_not_called()
        cleared = self.client.post(
            "/search/clear", data={"csrf_token": self.csrf_token}
        )
        self.assertEqual(cleared.status_code, 302)
        self.assertIsNone(latest_search_run())


if __name__ == "__main__":
    unittest.main()
