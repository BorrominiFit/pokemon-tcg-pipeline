"""Entry point della pipeline Pokémon TCG investing.

Sequenza:
  1. carica config (sources.yaml, weights.yaml, products.yaml)
  2. esegue scraper abilitati → raccoglie segnali grezzi
  3. signal engine → score 0-100 per prodotto
  4. strategy builder → categoria + allocazione budget
  5. persistenza JSON (dashboard) + snapshot storico
  6. evento Google Calendar (se non DRY_RUN)

Esecuzione:
    python -m src.main

Variabili ambiente rilevanti:
    DRY_RUN=true          → salta Calendar API, esegue tutto il resto
    DASHBOARD_URL=...     → URL della dashboard inserita nell'evento Calendar
    GOOGLE_CALENDAR_ID    → default "primary"
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from src.analyzers.signal_engine import SignalEngine
from src.analyzers.strategy_builder import StrategyBuilder, recommendations_to_dicts
from src.integrations.data_persistence import save_pipeline_output
from src.utils.logger import get_logger


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "src" / "config"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_scrapers(sources_cfg: dict, products: list[dict]) -> list:
    """Importa dinamicamente gli scraper attivati in sources.yaml."""
    from src.scrapers.pokebeach import PokeBeachScraper
    from src.scrapers.pokeguardian import PokeGuardianScraper
    from src.scrapers.cardmarket import CardmarketScraper
    from src.scrapers.pokemon_official import PokemonOfficialScraper
    from src.scrapers.reddit_pokeinvesting import RedditPokeInvestingScraper

    registry = {
        "pokebeach": lambda cfg: PokeBeachScraper(cfg, cache_dir=CACHE_DIR),
        "pokeguardian": lambda cfg: PokeGuardianScraper(cfg, cache_dir=CACHE_DIR),
        "cardmarket": lambda cfg: CardmarketScraper(cfg, products, cache_dir=CACHE_DIR),
        "pokemon_official": lambda cfg: PokemonOfficialScraper(cfg, cache_dir=CACHE_DIR),
        "reddit_pokeinvesting": lambda cfg: RedditPokeInvestingScraper(
            cfg, cache_dir=CACHE_DIR
        ),
    }

    scrapers = []
    for key, cfg in sources_cfg.get("sources", {}).items():
        if not cfg.get("enabled", False):
            continue
        builder = registry.get(cfg.get("module", key))
        if builder is None:
            continue
        scrapers.append(builder(cfg))
    return scrapers


def run(dry_run: bool = False) -> dict[str, Any]:
    logger = get_logger("main")
    logger.info("=== Pokémon TCG Weekly Strategy — start ===")

    # ---- 1. Carica configurazioni
    sources_cfg = load_yaml(CONFIG_DIR / "sources.yaml")
    weights_cfg = load_yaml(CONFIG_DIR / "weights.yaml")
    products_cfg = load_yaml(CONFIG_DIR / "products.yaml")
    products = products_cfg.get("products", [])
    products_by_id = {p["id"]: p for p in products}
    logger.info("caricati %d prodotti monitorati", len(products))

    # ---- 2. Esegui scrapers
    scrapers = build_scrapers(sources_cfg, products)
    raw_signals: list[dict[str, Any]] = []
    for s in scrapers:
        try:
            raw_signals.extend(s.fetch_signals())
        except Exception as exc:
            logger.exception("scraper %s ha fallito: %s", s.name, exc)
    logger.info("totale segnali grezzi raccolti: %d", len(raw_signals))

    # ---- 3. Signal engine
    engine = SignalEngine(weights_cfg)
    scoring_results = [engine.score_product(p, raw_signals) for p in products]

    # ---- 4. Strategy builder
    builder = StrategyBuilder(weights_cfg)
    recommendations = builder.build(scoring_results, products_by_id)
    rec_dicts = recommendations_to_dicts(recommendations)

    # ---- 5. Persistenza
    iso_year, iso_week, _ = date.today().isocalendar()
    run_metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "iso_week": f"{iso_year}-W{iso_week:02d}",
        "n_raw_signals": len(raw_signals),
        "n_products": len(products),
        "dry_run": dry_run,
    }
    save_pipeline_output(DATA_DIR, rec_dicts, raw_signals, run_metadata)

    # ---- 6. Google Calendar (skip se dry-run)
    if dry_run:
        logger.info("DRY_RUN attivo: skip Google Calendar")
        return {"recommendations": rec_dicts, "calendar_event_id": None}

    from src.integrations.google_calendar import GoogleCalendarPublisher

    # .strip() difensivo: i Secret di GitHub a volte includono trailing newline
    # quando si incolla un valore da una pagina web.
    dashboard_url = os.environ.get("DASHBOARD_URL", "https://example.github.io/").strip()
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary").strip()

    # Top 3 azioni per il body
    top_actions = [
        {
            "category": r.category,
            "set_name": r.set_name,
            "product_type": r.product_type,
            "score": r.score,
            "budget_allocation_pct": r.budget_allocation_pct,
            "rationale": r.rationale,
        }
        for r in recommendations
        if r.category in ("PREORDER", "ACCUMULATE")
    ][:3]

    try:
        publisher = GoogleCalendarPublisher(calendar_id=calendar_id)
        event_id = publisher.publish_weekly_event(top_actions, dashboard_url)
        logger.info("evento Calendar creato: %s", event_id)
    except Exception as exc:
        logger.exception("creazione evento Calendar fallita: %s", exc)
        event_id = None

    logger.info("=== Pipeline completata ===")
    return {"recommendations": rec_dicts, "calendar_event_id": event_id}


if __name__ == "__main__":
    dry = os.environ.get("DRY_RUN", "false").lower() in {"1", "true", "yes"}
    try:
        run(dry_run=dry)
    except Exception:
        get_logger("main").exception("pipeline fallita")
        sys.exit(1)
