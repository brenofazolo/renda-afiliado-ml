from __future__ import annotations

import unittest

from app.scoring import calculate_score, score_confidence


class ScoringEvidenceTest(unittest.TestCase):
    def test_search_position_alone_is_weak_demand_evidence(self) -> None:
        _, components = calculate_score({"position": 1}, 20)
        self.assertEqual(components["sinal_demanda"], 15.0)
        self.assertEqual(score_confidence({"position": 1}), "baixa")

    def test_weekly_trend_has_medium_confidence(self) -> None:
        _, components = calculate_score(
            {"position": 1, "discovery_source": "Tendência"}, 20
        )
        self.assertEqual(components["sinal_demanda"], 60.0)
        self.assertEqual(
            score_confidence({"discovery_source": "Tendência"}), "média"
        )

    def test_best_seller_has_high_confidence(self) -> None:
        _, components = calculate_score({"best_seller_position": 1}, 20)
        self.assertEqual(components["sinal_demanda"], 100.0)
        self.assertEqual(score_confidence({"best_seller_position": 1}), "alta")


if __name__ == "__main__":
    unittest.main()
