"""Integrazione Google Calendar — creazione evento settimanale strategico.

Usa Service Account (preferito per cron headless senza OAuth interattivo).
Il calendario di destinazione deve essere condiviso col service account in scrittura
(vedi README sezione "Setup Google Calendar API").
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.utils.logger import get_logger


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleCalendarPublisher:
    def __init__(self, calendar_id: str = "primary", timezone: str = "Europe/Rome"):
        self.logger = get_logger("google_calendar")
        # strip difensivo: rimuove eventuali newline/spazi accidentali nei Secret
        self.calendar_id = (calendar_id or "primary").strip()
        self.timezone = timezone
        self.service = self._build_service()

    def _build_service(self):
        creds_raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if not creds_raw:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON non impostato. "
                "Esegui in dry-run (DRY_RUN=true) o configura il secret."
            )

        # Può essere: (a) JSON inline, (b) path a file
        if creds_raw.startswith("{"):
            info = json.loads(creds_raw)
        elif os.path.exists(creds_raw):
            info = json.loads(open(creds_raw, encoding="utf-8").read())
        else:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON non è né JSON valido né path esistente"
            )

        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def publish_weekly_event(
        self,
        recommendations_summary: list[dict[str, Any]],
        dashboard_url: str,
        event_date: date | None = None,
    ) -> str:
        """Crea un evento Calendar lunedì alle 08:00 con riepilogo top 3 azioni.

        Restituisce l'ID dell'evento creato.
        """
        if event_date is None:
            event_date = _next_monday()

        start_dt = datetime.combine(event_date, time(hour=8, minute=0))
        end_dt = start_dt + timedelta(minutes=30)

        title = f"📊 Pokémon TCG Weekly Strategy – {event_date.isoformat()}"
        body = self._format_body(recommendations_summary, dashboard_url)

        event_payload = {
            "summary": title,
            "description": body,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": self.timezone},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": self.timezone},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 24 * 60},  # 1 giorno prima
                    {"method": "popup", "minutes": 60},  # 1 ora prima
                    {"method": "email", "minutes": 24 * 60},
                ],
            },
            # Marcatura visiva — colore arancione = priorità alta
            "colorId": "6",
            "transparency": "opaque",
        }

        try:
            created = (
                self.service.events()
                .insert(calendarId=self.calendar_id, body=event_payload)
                .execute()
            )
        except HttpError as exc:
            self.logger.error("Calendar API HttpError: %s", exc)
            raise

        self.logger.info("evento creato: %s (%s)", created.get("id"), created.get("htmlLink"))
        return created.get("id", "")

    @staticmethod
    def _format_body(summary: list[dict[str, Any]], dashboard_url: str) -> str:
        if not summary:
            top_block = "Nessuna azione PREORDER/ACCUMULATE questa settimana — controlla la dashboard."
        else:
            lines = []
            for i, item in enumerate(summary, 1):
                lines.append(
                    f"{i}. [{item['category']}] {item['set_name']} ({item['product_type']}) "
                    f"— score {item['score']}, budget {item['budget_allocation_pct']}%"
                )
                lines.append(f"   → {item['rationale']}")
            top_block = "\n".join(lines)

        return (
            "Top 3 azioni della settimana:\n\n"
            f"{top_block}\n\n"
            f"Dashboard completa: {dashboard_url}"
        )


def _next_monday(reference: date | None = None) -> date:
    """Restituisce la data del prossimo lunedì (o oggi se è già lunedì)."""
    reference = reference or date.today()
    days_ahead = (0 - reference.weekday()) % 7
    if days_ahead == 0 and datetime.now().time() > time(8, 0):
        # se siamo già lunedì dopo le 8:00 → prossimo lunedì
        days_ahead = 7
    return reference + timedelta(days=days_ahead)
