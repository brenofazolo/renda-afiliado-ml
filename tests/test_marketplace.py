from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.marketplace import get_trends


class MarketplaceTrendsTest(unittest.TestCase):
    def test_get_trends_uses_official_site_endpoint(self) -> None:
        response = Mock()
        response.json.return_value = [{"keyword": "cafeteira"}]
        with patch("app.marketplace.meli_request", return_value=response) as request:
            trends = get_trends("MLB")
        request.assert_called_once_with(
            "GET", "https://api.mercadolibre.com/trends/MLB", timeout=20
        )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(trends[0]["keyword"], "cafeteira")

    def test_get_trends_rejects_unexpected_payload(self) -> None:
        response = Mock()
        response.json.return_value = {"unexpected": True}
        with patch("app.marketplace.meli_request", return_value=response):
            self.assertEqual(get_trends("MLB"), [])


if __name__ == "__main__":
    unittest.main()
