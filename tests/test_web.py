from __future__ import annotations

import os
import re
import tempfile
import unittest


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
        from app.storage import list_selections

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
        self.assertIn(b"Produto teste", self.client.get("/selections").data)

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


if __name__ == "__main__":
    unittest.main()
