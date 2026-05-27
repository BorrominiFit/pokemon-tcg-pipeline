"""Classe base per tutti gli scraper.

Tutti gli scraper concreti ereditano da BaseScraper e implementano `fetch_signals`.
La classe base gestisce: HTTP session con retry, User-Agent, timeout, rate limit, cache.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.utils.cache import DiskCache
from src.utils.logger import get_logger


class ScraperError(Exception):
    """Errore generico di scraping (rete, parsing, rate-limit)."""


class BaseScraper(ABC):
    """Base comune per tutti gli scraper.

    Ogni scraper concreto:
      1. eredita da BaseScraper
      2. imposta `name` e altri campi via __init__
      3. implementa `fetch_signals()` che restituisce una lista di dict normalizzati
    """

    def __init__(self, name: str, config: dict[str, Any], cache_dir: Path | None = None):
        self.name = name
        self.config = config
        self.base_url = config.get("base_url", "").rstrip("/")
        self.timeout = config.get("timeout_seconds", 20)
        self.rate_limit_seconds = config.get("rate_limit_seconds", 1)
        self.logger = get_logger(f"scraper.{name}")

        user_agent = os.environ.get(
            "SCRAPER_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        self.cache: DiskCache | None = None
        if cache_dir is not None:
            self.cache = DiskCache(cache_dir / name, ttl_seconds=3600)

    @retry(
        retry=retry_if_exception_type((requests.RequestException, ScraperError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    def _get(self, url: str, params: dict | None = None) -> str:
        """GET con retry esponenziale e rate-limit."""
        cache_key = f"{url}?{params}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached and "html" in cached:
                self.logger.debug("cache hit %s", url)
                return cached["html"]

        self.logger.debug("GET %s", url)
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code == 429:
            raise ScraperError(f"Rate limited on {url}")
        resp.raise_for_status()

        time.sleep(self.rate_limit_seconds)
        if self.cache:
            self.cache.set(cache_key, {"html": resp.text})
        return resp.text

    def _get_json(self, url: str, params: dict | None = None) -> dict:
        """GET con header JSON, restituisce dict."""
        self.logger.debug("GET JSON %s", url)
        headers = {"Accept": "application/json"}
        resp = self.session.get(url, params=params, timeout=self.timeout, headers=headers)
        resp.raise_for_status()
        time.sleep(self.rate_limit_seconds)
        return resp.json()

    @abstractmethod
    def fetch_signals(self) -> list[dict[str, Any]]:
        """Restituisce una lista di segnali normalizzati.

        Schema atteso di ogni segnale:
        {
            "source": str,           # nome scraper
            "signal_type": str,      # "release" | "rumor" | "price_trend" | "sentiment" | "news"
            "set_name": str | None,
            "product_id": str | None,
            "title": str,
            "url": str,
            "date": str | None,      # ISO 8601
            "raw_text": str,
            "metadata": dict,
        }
        """
        raise NotImplementedError
