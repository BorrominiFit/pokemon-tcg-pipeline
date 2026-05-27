"""Scraper PokéGuardian — news principalmente set JP (utili per anticipare EU)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper


class PokeGuardianScraper(BaseScraper):
    def __init__(self, config: dict[str, Any], cache_dir=None):
        super().__init__(name="pokeguardian", config=config, cache_dir=cache_dir)

    def fetch_signals(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        url = f"{self.base_url}{self.config.get('news_path', '/news')}"

        try:
            html = self._get(url)
        except Exception as exc:
            self.logger.error("fetch failed: %s", exc)
            return signals

        soup = BeautifulSoup(html, "lxml")
        # Pokeguardian usa post in card. Selettore difensivo.
        articles = soup.select("article, .post, .news-card")[:25]

        for art in articles:
            title_tag = art.find(["h1", "h2", "h3"])
            link_tag = art.find("a", href=True)

            if not title_tag or not link_tag:
                continue

            title = title_tag.get_text(strip=True)
            url_article = link_tag["href"]
            if not url_article.startswith("http"):
                url_article = self.base_url + url_article

            date_iso = None
            time_tag = art.find("time")
            if time_tag and time_tag.get("datetime"):
                try:
                    date_iso = datetime.fromisoformat(
                        time_tag["datetime"].replace("Z", "+00:00")
                    ).date().isoformat()
                except ValueError:
                    pass

            signals.append(
                {
                    "source": self.name,
                    "signal_type": "jp_news",
                    "set_name": None,
                    "product_id": None,
                    "title": title,
                    "url": url_article,
                    "date": date_iso,
                    "raw_text": title,
                    "metadata": {"region_hint": "JP"},
                }
            )

        self.logger.info("estratti %d segnali", len(signals))
        return signals
