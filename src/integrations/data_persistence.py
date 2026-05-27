"""Persistenza output della pipeline su filesystem (committato da GitHub Actions).

- `data/latest.json` viene letto dalla dashboard.
- `data/history/YYYY-WW.json` mantiene gli snapshot settimanali per il grafico trend.
- `data/raw_signals_latest.json` contiene i segnali grezzi (utile per debug).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("persistence")


def save_pipeline_output(
    data_dir: Path,
    recommendations: list[dict[str, Any]],
    raw_signals: list[dict[str, Any]],
    run_metadata: dict[str, Any],
) -> Path:
    """Salva latest.json + snapshot storico settimanale.

    Restituisce il path di latest.json.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    history_dir = data_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": run_metadata.get("generated_at"),
        "iso_week": run_metadata.get("iso_week"),
        "summary": {
            "preorder_count": sum(1 for r in recommendations if r["category"] == "PREORDER"),
            "accumulate_count": sum(1 for r in recommendations if r["category"] == "ACCUMULATE"),
            "hold_count": sum(1 for r in recommendations if r["category"] == "HOLD"),
            "avoid_count": sum(1 for r in recommendations if r["category"] == "AVOID"),
            "top_action": _top_action_summary(recommendations),
        },
        "recommendations": recommendations,
        "run_metadata": run_metadata,
    }

    latest_path = data_dir / "latest.json"
    latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("scritto %s", latest_path)

    # Snapshot storico settimanale
    iso_year, iso_week, _ = date.today().isocalendar()
    history_path = history_dir / f"{iso_year}-W{iso_week:02d}.json"
    history_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("scritto %s", history_path)

    # Raw signals (debug)
    raw_path = data_dir / "raw_signals_latest.json"
    raw_path.write_text(
        json.dumps(raw_signals, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("scritto %s (%d segnali grezzi)", raw_path, len(raw_signals))

    return latest_path


def _top_action_summary(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Top 3 azioni della settimana per l'evento Calendar e l'header dashboard."""
    actionable = [r for r in recs if r["category"] in ("PREORDER", "ACCUMULATE")]
    top = actionable[:3]
    return [
        {
            "set_name": r["set_name"],
            "product_type": r["product_type"],
            "category": r["category"],
            "score": r["score"],
            "budget_allocation_pct": r["budget_allocation_pct"],
            "rationale": r["rationale"],
        }
        for r in top
    ]
