"""Motore di scoring multi-segnale per prodotti Pokémon TCG sigillato.

Per ogni prodotto in products.yaml, il signal engine aggrega i segnali grezzi
provenienti dagli scrapers e produce uno **score 0-100** che esprime
l'attrattività dell'investimento.

I segnali sono normalizzati 0-1, pesati secondo weights.yaml e sommati.
Lo score finale viene poi riscalato 0-100 e accompagnato da una *breakdown*
che spiega cosa ha contribuito al risultato (utile per debug e dashboard).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from src.utils.logger import get_logger


# Set storici di riferimento per il comparable trend.
# Valori 0-1: 1.0 = set leggendario (es. Hidden Fates), 0.0 = flop.
# In futuro questo può essere calcolato dinamicamente da serie storiche prezzi.
COMPARABLE_PERFORMANCE = {
    "Hidden Fates": 1.0,
    "Shining Fates": 0.85,
    "Crown Zenith": 0.9,
    "Crown Zenith Booster Bundle": 0.85,
    "151": 0.95,
    "Evolving Skies": 1.0,
    "Surging Sparks": 0.7,
    "Stellar Crown": 0.6,
    "Paldean Fates": 0.85,
    "Twilight Masquerade": 0.5,
    "Temporal Forces": 0.45,
}

# Set notoriamente facilmente ristampati (penalità)
EASILY_REPRINTED = {"Trainer's Toolkit", "Battle Academy"}


@dataclass
class ScoringResult:
    """Risultato dello scoring per un singolo prodotto."""

    product_id: str
    score: float  # 0-100
    breakdown: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class SignalEngine:
    def __init__(self, weights: dict[str, Any]):
        self.logger = get_logger("signal_engine")
        self.signal_weights = weights.get("signals", {})

    def score_product(
        self,
        product: dict[str, Any],
        signals: list[dict[str, Any]],
    ) -> ScoringResult:
        """Calcola lo score 0-100 per un prodotto a partire dai segnali raccolti."""

        # ----- 1. Chase strength
        chase_strength = self._chase_strength(product)

        # ----- 2. Scarcity (proxy: numero menzioni "OOP"/"sold out" nei segnali news + flair)
        scarcity = self._scarcity_score(product, signals)

        # ----- 3. Hype (proxy: somma normalizzata upvotes Reddit per il set)
        hype = self._hype_score(product, signals)

        # ----- 4. Comparable trend (lookup statico, in futuro dinamico)
        comparable = self._comparable_trend_score(product)

        # ----- 5. Imminence (vicinanza data uscita = opportunità preorder)
        imminence = self._imminence_score(product)

        # ----- 6. Event tie-in (anniversari, anime/film)
        event_tie_in = self._event_tie_in_score(product, signals)

        # ----- 7. Premium MSRP (a campana: 0% premium = top; >50% premium = rischio top)
        premium_msrp = self._premium_msrp_score(product, signals)

        # ----- 8. POP PSA10 scarcity (placeholder: lo collegheremo a una fonte futura)
        pop_psa10 = product.get("pop_psa10_score", 0.5)

        # ----- 9. Reprintability penalty
        reprint_penalty = 1.0 if product.get("set_name") in EASILY_REPRINTED else 0.0

        # Aggregazione pesata
        components = {
            "chase_strength": (chase_strength, self.signal_weights.get("chase_strength_weight", 0)),
            "scarcity": (scarcity, self.signal_weights.get("scarcity_weight", 0)),
            "hype": (hype, self.signal_weights.get("hype_weight", 0)),
            "comparable_trend": (comparable, self.signal_weights.get("comparable_trend_weight", 0)),
            "imminence": (imminence, self.signal_weights.get("imminence_weight", 0)),
            "event_tie_in": (event_tie_in, self.signal_weights.get("event_tie_in_weight", 0)),
            "premium_msrp": (premium_msrp, self.signal_weights.get("premium_msrp_weight", 0)),
            "pop_psa10_scarcity": (
                pop_psa10,
                self.signal_weights.get("pop_psa10_scarcity_weight", 0),
            ),
            "reprintability_penalty": (
                reprint_penalty,
                self.signal_weights.get("reprintability_penalty_weight", 0),
            ),
        }

        raw_total = sum(val * weight for val, weight in components.values())
        max_possible = sum(abs(weight) for _, weight in components.values()) or 1.0
        score_0_100 = max(0.0, min(100.0, (raw_total / max_possible) * 100))

        breakdown = {k: round(v * w, 3) for k, (v, w) in components.items()}

        return ScoringResult(
            product_id=product["id"],
            score=round(score_0_100, 1),
            breakdown=breakdown,
            metadata={
                "chase_cards": product.get("chase_cards"),
                "comparable_sets": product.get("comparable_sets"),
                "release_date": product.get("release_date"),
                "msrp_eur": product.get("msrp_eur"),
                "current_price_eur": self._current_price(product, signals),
                "premium_over_msrp_pct": self._current_premium(product, signals),
            },
        )

    # ---------------- single signal calculators ----------------

    @staticmethod
    def _chase_strength(product: dict) -> float:
        """0-1. Più chase card riconoscibili nel set, più alto."""
        chase = product.get("chase_cards") or []
        # heuristica semplice: 0 chase = 0.2, 1 = 0.5, 2+ = 0.8, presenza "SIR"/"alt art" = +0.1
        base = {0: 0.2, 1: 0.55}.get(len(chase), 0.8)
        text = " ".join(chase).lower()
        if "sir" in text or "alt art" in text or "special illustration" in text:
            base = min(1.0, base + 0.1)
        return base

    @staticmethod
    def _scarcity_score(product: dict, signals: list[dict]) -> float:
        keywords = ["out of print", "oop", "sold out", "scarcity", "scarce", "discontinued"]
        set_name = (product.get("set_name") or "").lower()
        hits = 0
        for s in signals:
            text = (s.get("title", "") + " " + s.get("raw_text", "")).lower()
            if set_name and set_name in text and any(k in text for k in keywords):
                hits += 1
        return min(1.0, hits / 3.0)

    @staticmethod
    def _hype_score(product: dict, signals: list[dict]) -> float:
        """Proxy: media normalizzata upvotes Reddit per il set."""
        set_name = (product.get("set_name") or "").lower()
        upvotes_total = 0
        post_count = 0
        for s in signals:
            if s.get("source") != "reddit_pokeinvesting":
                continue
            text = (s.get("title", "") + " " + s.get("raw_text", "")).lower()
            if set_name and set_name in text:
                upvotes_total += s.get("metadata", {}).get("upvotes", 0) or 0
                post_count += 1
        if post_count == 0:
            return 0.3  # baseline neutro
        avg = upvotes_total / post_count
        # 200 upvotes = molto buono → 1.0
        return min(1.0, avg / 200.0)

    @staticmethod
    def _comparable_trend_score(product: dict) -> float:
        comp = product.get("comparable_sets") or []
        if not comp:
            return 0.5
        scores = [COMPARABLE_PERFORMANCE.get(c, 0.5) for c in comp]
        return sum(scores) / len(scores)

    @staticmethod
    def _imminence_score(product: dict) -> float:
        rd = product.get("release_date")
        if not rd:
            return 0.3
        try:
            release = datetime.strptime(rd, "%Y-%m-%d").date()
        except ValueError:
            return 0.3
        days = (release - date.today()).days
        if days < -180:
            return 0.1  # uscita molto vecchia, finestra preorder chiusa da tempo
        if -180 <= days < 0:
            return 0.4  # appena uscito
        if 0 <= days <= 14:
            return 1.0  # preorder window critica
        if 14 < days <= 60:
            return 0.85
        if 60 < days <= 180:
            return 0.6
        return 0.4

    @staticmethod
    def _event_tie_in_score(product: dict, signals: list[dict]) -> float:
        """Cerca menzioni di anniversario / anime / film legate al set."""
        set_name = (product.get("set_name") or "").lower()
        keywords = ["anniversary", "anniversario", "30th", "film", "movie", "anime", "tie-in"]
        for s in signals:
            text = (s.get("title", "") + " " + s.get("raw_text", "")).lower()
            if set_name and set_name in text and any(k in text for k in keywords):
                return 0.9
        return 0.3

    @staticmethod
    def _premium_msrp_score(product: dict, signals: list[dict]) -> float:
        """A campana: premium 0-20% = 1.0, premium >100% = 0.2 (rischio top).
        Premium negativo (sotto MSRP, raro) = 1.0 (occasione).
        """
        premium = None
        for s in signals:
            if s.get("product_id") == product["id"]:
                p = s.get("metadata", {}).get("premium_over_msrp_pct")
                if p is not None:
                    premium = p
                    break
        if premium is None:
            return 0.5  # nessun dato prezzo
        if premium <= 0:
            return 1.0
        if premium <= 20:
            return 0.95
        if premium <= 50:
            return 0.7
        if premium <= 100:
            return 0.4
        return 0.2

    @staticmethod
    def _current_price(product: dict, signals: list[dict]) -> float | None:
        for s in signals:
            if s.get("product_id") == product["id"]:
                meta = s.get("metadata", {})
                return meta.get("price_avg_30d") or meta.get("price_from")
        return None

    @staticmethod
    def _current_premium(product: dict, signals: list[dict]) -> float | None:
        for s in signals:
            if s.get("product_id") == product["id"]:
                return s.get("metadata", {}).get("premium_over_msrp_pct")
        return None
