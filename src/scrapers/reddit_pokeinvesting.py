"""Scraper Reddit r/PokeInvesting — community sentiment.

Reddit espone un endpoint JSON pubblico (.json) che non richiede autenticazione
per la lettura dei top post. Lo usiamo come proxy del sentiment community su
prodotti correnti.
"""

from __future__ import annotations

from typing import Any

from src.scrapers.base import BaseScraper


class RedditPokeInvestingScraper(BaseScraper):
    def __init__(self, config: dict[str, Any], cache_dir=None):
        super().__init__(name="reddit_pokeinvesting", config=config, cache_dir=cache_dir)

    def fetch_signals(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        subreddit = self.config.get("subreddit", "PokeInvesting")
        limit = self.config.get("top_limit", 30)
        url = f"{self.base_url}/r/{subreddit}/top.json"
        params = {"limit": limit, "t": "week"}

        try:
            data = self._get_json(url, params=params)
        except Exception as exc:
            self.logger.error("fetch failed: %s", exc)
            return signals

        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            title = post.get("title", "")
            score = post.get("score", 0)
            comments = post.get("num_comments", 0)
            permalink = f"{self.base_url}{post.get('permalink', '')}"
            created_iso = None
            if post.get("created_utc"):
                from datetime import datetime, timezone
                created_iso = (
                    datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
                    .date()
                    .isoformat()
                )

            signals.append(
                {
                    "source": self.name,
                    "signal_type": "sentiment",
                    "set_name": None,
                    "product_id": None,
                    "title": title,
                    "url": permalink,
                    "date": created_iso,
                    "raw_text": post.get("selftext", "")[:500],
                    "metadata": {
                        "upvotes": score,
                        "comments": comments,
                        "flair": post.get("link_flair_text"),
                    },
                }
            )

        self.logger.info("estratti %d post r/%s", len(signals), subreddit)
        return signals
