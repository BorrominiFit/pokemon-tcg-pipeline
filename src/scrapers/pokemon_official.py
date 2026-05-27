"""Scraper sito ufficiale Pokémon EU — conferme release.

Strategia: pagina pubblica delle news/release del TCG EU. Cerchiamo annunci di set
con data di uscita confermata.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper


class PokemonOfficialScraper(BaseScraper):
    def __init__(self, config: dict[str, Any], cache_dir=None):
        super().__init__(name="pokemon_official", config=config, cache_dir=cache_dir)

    def fetch_signals(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        locale_path = self.config.get("locale_path", "/it/gioco-di-carte-collezionabili")
        url = f"{self.base_url}{locale_path}"

        try:
            html = self._get(url)
        except Exception as exc:
            self.logger.error("fetch failed: %s", exc)
            return signals

        soup = BeautifulSoup(html, "lxml")
        # Pokemon.com usa molti componenti dinamici React-rendered;
        # cerchiamo i set link in modo difensivo.
        candidates = soup.select("a[href*='gioco-di-carte-collezionabili']")[:50]
        seen = set()
        for a in candidates:
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not text or len(text) < 4 or href in seen:
                continue
            seen.add(href)
            if not href.startswith("http"):
                href = self.base_url + href
            signals.append(
                {
                    "source": self.name,
                    "signal_type": "official_listing",
                    "set_name": None,
                    "product_id": None,
                    "title": text,
                    "url": href,
                    "date": None,
                    "raw_text": text,
                    "metadata": {"locale": "it"},
                }
            )

        self.logger.info("estratti %d segnali", len(signals))
        return signals
