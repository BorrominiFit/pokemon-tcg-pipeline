"""Cache su disco per le risposte HTTP (evita di martellare le fonti durante lo sviluppo)."""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional


class DiskCache:
    """Cache JSON su disco con TTL in secondi.

    Usata durante sviluppo e in produzione per non rifare scraping inutili nel giro
    di pochi minuti se un run fallisce a metà e viene rilanciato.
    """

    def __init__(self, cache_dir: Path, ttl_seconds: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _key_to_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{h}.json"

    def get(self, key: str) -> Optional[dict]:
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data.get("_cached_at", 0) > self.ttl_seconds:
                return None
            return data.get("value")
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: dict) -> None:
        path = self._key_to_path(key)
        payload = {"_cached_at": time.time(), "value": value}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
