"""Scraper Cardmarket — prezzi sigillato (pagine prodotto pubbliche).

Nota importante: Cardmarket espone in HTML pubblico il "Price Trend" e il "30-day average".
Lo scraping è inevitabilmente fragile (cambi DOM, anti-bot Cloudflare).
Manteniamo lo scraper difensivo: se non riusciamo a estrarre, segnaliamo `None`
senza far fallire l'intera pipeline.

Per ottenere risultati stabili in produzione, considera in futuro l'API ufficiale
Cardmarket (richiede account Pro/Powerseller).
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper


PRICE_RE = re.compile(r"(\d+[\.,]\d+)\s*€?")


class CardmarketScraper(BaseScraper):
    def __init__(self, config: dict[str, Any], products: list[dict], cache_dir=None):
        super().__init__(name="cardmarket", config=config, cache_dir=cache_dir)
        # Riceve la lista prodotti da products.yaml per sapere quali URL fetchare.
        self.products = [p for p in products if p.get("cardmarket_url")]

    def fetch_signals(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        if not self.products:
            self.logger.info("nessun prodotto con cardmarket_url configurato")
            return signals

        for product in self.products:
            url = product["cardmarket_url"]
            try:
                html = self._get(url)
            except Exception as exc:
                self.logger.warning(
                    "fetch fallito per %s: %s", product.get("id"), exc
                )
                continue

            prices = self._parse_prices(html)
            if not prices:
                self.logger.debug("nessun prezzo estratto per %s", product["id"])
                continue

            signals.append(
                {
                    "source": self.name,
                    "signal_type": "price_trend",
                    "set_name": product.get("set_name"),
                    "product_id": product["id"],
                    "title": f"Cardmarket prices — {product['set_name']} ({product['product_type']})",
                    "url": url,
                    "date": None,
                    "raw_text": "",
                    "metadata": {
                        "price_from": prices.get("price_from"),
                        "price_trend_30d": prices.get("price_trend_30d"),
                        "price_avg_30d": prices.get("price_avg_30d"),
                        "msrp_eur": product.get("msrp_eur"),
                        "premium_over_msrp_pct": self._premium_pct(
                            prices.get("price_from") or prices.get("price_avg_30d"),
                            product.get("msrp_eur"),
                        ),
                    },
                }
            )

        self.logger.info("estratti %d segnali prezzo", len(signals))
        return signals

    @staticmethod
    def _parse_prices(html: str) -> dict[str, float | None]:
        """Estrazione difensiva di prezzi dalla pagina prodotto Cardmarket.

        Cardmarket usa una tabella `.info-list-table` con righe etichettate.
        Cerchiamo le label note: "Price Trend", "30-days average price", "From".
        """
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, float | None] = {
            "price_from": None,
            "price_trend_30d": None,
            "price_avg_30d": None,
        }

        # Strategia 1: tabella info
        for dt in soup.select("dt"):
            label = dt.get_text(strip=True).lower()
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            price = _parse_price_text(dd.get_text())
            if "price trend" in label:
                out["price_trend_30d"] = price
            elif "30-days average" in label or "30-day average" in label:
                out["price_avg_30d"] = price
            elif "from" in label and out["price_from"] is None:
                out["price_from"] = price

        return out

    @staticmethod
    def _premium_pct(price: float | None, msrp: float | None) -> float | None:
        if not price or not msrp or msrp == 0:
            return None
        return round(((price - msrp) / msrp) * 100, 1)


def _parse_price_text(text: str) -> float | None:
    """'25,50 €' -> 25.5"""
    m = PRICE_RE.search(text or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "."))
