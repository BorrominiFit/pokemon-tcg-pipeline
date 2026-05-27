"""Costruisce la strategia d'acquisto settimanale a partire dagli scoring.

Output: lista prodotti classificati in PREORDER / ACCUMULATE / HOLD / AVOID,
con allocazione percentuale del budget e motivazione testuale.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.analyzers.signal_engine import ScoringResult
from src.utils.logger import get_logger


@dataclass
class Recommendation:
    product_id: str
    set_name: str
    product_type: str
    score: float
    category: str  # PREORDER | ACCUMULATE | HOLD | AVOID
    rationale: str
    budget_allocation_pct: float  # quota suggerita del budget settimanale per questo prodotto
    breakdown: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class StrategyBuilder:
    def __init__(self, weights_config: dict[str, Any]):
        self.logger = get_logger("strategy_builder")
        self.thresholds = weights_config.get("thresholds", {})
        self.budget_alloc = weights_config.get("budget_allocation", {})

    def build(
        self,
        scoring_results: list[ScoringResult],
        products_by_id: dict[str, dict],
    ) -> list[Recommendation]:
        """Costruisce la lista di raccomandazioni ordinate per score decrescente."""
        # 1. classifica
        for r in scoring_results:
            r.metadata["category"] = self._categorize(r.score)

        # 2. raggruppa per categoria
        groups = {"PREORDER": [], "ACCUMULATE": [], "HOLD": [], "AVOID": []}
        for r in scoring_results:
            groups[r.metadata["category"]].append(r)

        # 3. allocazione budget: distribuisce la quota della categoria proporzionalmente allo score
        recommendations: list[Recommendation] = []
        for cat, items in groups.items():
            if not items:
                continue
            cat_pct = self._category_pct(cat)
            total_score = sum(it.score for it in items) or 1
            for it in items:
                product = products_by_id.get(it.product_id, {})
                product_pct = round((it.score / total_score) * cat_pct, 2) if cat != "AVOID" else 0.0
                recommendations.append(
                    Recommendation(
                        product_id=it.product_id,
                        set_name=product.get("set_name", ""),
                        product_type=product.get("product_type", ""),
                        score=it.score,
                        category=cat,
                        rationale=self._rationale(it, product),
                        budget_allocation_pct=product_pct,
                        breakdown=it.breakdown,
                        metadata=it.metadata,
                    )
                )

        # 4. ordina globalmente per score decrescente
        recommendations.sort(key=lambda r: r.score, reverse=True)
        self.logger.info(
            "strategia generata: %d raccomandazioni totali",
            len(recommendations),
        )
        return recommendations

    def _categorize(self, score: float) -> str:
        if score >= self.thresholds.get("preorder_min_score", 75):
            return "PREORDER"
        if score >= self.thresholds.get("accumulate_min_score", 60):
            return "ACCUMULATE"
        if score >= self.thresholds.get("hold_min_score", 45):
            return "HOLD"
        return "AVOID"

    def _category_pct(self, category: str) -> float:
        mapping = {
            "PREORDER": self.budget_alloc.get("preorder_pct", 60),
            "ACCUMULATE": self.budget_alloc.get("accumulate_pct", 35),
            "HOLD": self.budget_alloc.get("hold_pct", 5),
            "AVOID": self.budget_alloc.get("avoid_pct", 0),
        }
        return mapping.get(category, 0)

    @staticmethod
    def _rationale(scoring: ScoringResult, product: dict) -> str:
        """Spiegazione testuale dei principali driver dello score."""
        b = scoring.breakdown
        top_drivers = sorted(b.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        parts = []
        for name, val in top_drivers:
            if val >= 0:
                parts.append(f"{name.replace('_', ' ')} +{val:.2f}")
            else:
                parts.append(f"{name.replace('_', ' ')} {val:.2f}")
        msrp = product.get("msrp_eur")
        cur = scoring.metadata.get("current_price_eur")
        price_line = ""
        if cur and msrp:
            premium = scoring.metadata.get("premium_over_msrp_pct")
            price_line = f" Prezzo Cardmarket ~{cur}€ (premium {premium}% su MSRP {msrp}€)."
        return "Driver principali: " + " | ".join(parts) + "." + price_line


def recommendations_to_dicts(recs: list[Recommendation]) -> list[dict[str, Any]]:
    return [asdict(r) for r in recs]
