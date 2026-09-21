"""Startup-time forecast generation and read-only dashboard cache."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

CACHE_PATH = Path(__file__).resolve().parent / "forecast_cache.json"

_cache: dict[str, Any] | None = None
_lock = Lock()


def initialize_prediction_cache() -> dict[str, Any]:
    """Run the forecasting pipeline once for this server process and persist the result."""
    global _cache
    if _cache is not None:
        return _cache

    with _lock:
        if _cache is not None:
            return _cache

        # Importing the model performs its one-time training. Keep that work inside
        # application startup rather than inside dashboard request handling.
        from prediction.ReserveForces_pop import generate_dashboard_data

        payload = generate_dashboard_data()
        CACHE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        _cache = payload
        return payload


def get_prediction_cache() -> dict[str, Any]:
    """Return the in-memory forecast without retraining any model."""
    if _cache is None:
        raise RuntimeError("Prediction cache has not been initialized")
    return _cache
