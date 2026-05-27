"""Scraper PokéBeach — news e conferme di uscite Pokémon TCG.

Strategia: la pagina /news di PokéBeach lista articoli con titolo, data, link.
Parsiamo i primi N articoli e li classifichiamo per tipo di segnale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError


# Keywords per classificazione segnale dal titolo
KEYWORDS_RELEASE = ["releases", "release date", "out today", "now available", "launches"]
KEYWORDS_RUMOR = ["rumor", "leak", "leaked", "spoiler", "leaked images"]
KEYWORDS_REVEAL = ["reveal", "revealed", "new set", "announced"]


class PokeBeachScraper(BaseScraper):
    def __init__(self, config: dict[str, Any], cache_dir=None):
        super().__init__(name="pokebeach", config=config, cache_dir=cache_dir)

    def fetch_signals(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        url = f"{self.base_url}{self.config.get('news_path', '/news')}"

        try:
            html = self._get(url)
        except Exception as exc:
            self.logger.error("fetch failed: %s", exc)
            return signals

        soup = BeautifulSoup(html, "lxml")

        # PokéBeach usa <article> per ogni post. Selettore difensivo.
        articles = soup.find_all("article", limit=30)
        if not articles:
            # fallback: cerca link in <main> o <div class="post">
            articles = soup.select("div.post, .news-item, .entry")[:30]

        if not articles:
            self.logger.warning("nessun articolo trovato — verifica struttura HTML")
            return signals

        for art in articles:
            title_tag = art.find(["h1", "h2", "h3"])
            link_tag = art.find("a", href=True)
            time_tag = art.find("time")

            if not title_tag or not link_tag:
                continue

            title = title_tag.get_text(strip=True)
            url_article = link_tag["href"]
            if not url_article.startswith("http"):
                url_article = self.base_url + url_article

            date_iso = None
            if time_tag and time_tag.get("datetime"):
                try:
                    date_iso = datetime.fromisoformat(
                        time_tag["datetime"].replace("Z", "+00:00")
                    ).date().isoformat()
                except ValueError:
                    pass

            signal_type = self._classify_title(title)

            signals.append(
                {
                    "source": self.name,
                    "signal_type": signal_type,
                    "set_name": self._extract_set_name(title),
                    "product_id": None,
                    "title": title,
                    "url": url_article,
                    "date": date_iso,
                    "raw_text": title,
                    "metadata": {},
                }
            )

        self.logger.info("estratti %d segnali", len(signals))
        return signals

    @staticmethod
    def _classify_title(title: str) -> str:
        t = title.lower()
        if any(k in t for k in KEYWORDS_RUMOR):
            return "rumor"
        if any(k in t for k in KEYWORDS_RELEASE):
            return "release"
        if any(k in t for k in KEYWORDS_REVEAL):
            return "reveal"
        return "news"

    @staticmethod
    def _extract_set_name(title: str) -> str | None:
        """Tentativo euristico di estrarre il nome del set dal titolo.
        Cerca pattern '... [Set Name] ...' o '... Set Name set ...'.
        """
        # patterns noti — espandere col tempo
        known = [
            "Prismatic Evolutions",
            "Journey Together",
            "Destined Rivals",
            "Surging Sparks",
            "Stellar Crown",
            "Twilight Masquerade",
            "Temporal Forces",
            "Paldean Fates",
            "151",
            "Crown Zenith",
        ]
        for s in known:
            if s.lower() in title.lower():
                return s
        return None
