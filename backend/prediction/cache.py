"""Startup-time forecast generation and read-only dashboard cache."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

CACHE_PATH = Path(__file__).resolve().parent / "forecast_cache.json"
ATTENDANCE_CACHE_PATH = Path(__file__).resolve().parent / "attendance_forecast_cache.json"

_cache: dict[str, Any] | None = None
_lock = Lock()
_attendance_cache: dict[str, Any] | None = None
_attendance_lock = Lock()


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


def initialize_attendance_cache() -> dict[str, Any]:
    """Compute the attendance-rate forecast once for this server process and persist it."""
    global _attendance_cache
    if _attendance_cache is not None:
        return _attendance_cache

    with _attendance_lock:
        if _attendance_cache is not None:
            return _attendance_cache

        from prediction.attendance import generate_attendance_forecast

        payload = generate_attendance_forecast()
        ATTENDANCE_CACHE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        _attendance_cache = payload
        return payload


def get_attendance_cache() -> dict[str, Any]:
    """Return the in-memory attendance forecast without recomputing it."""
    if _attendance_cache is None:
        raise RuntimeError("Attendance cache has not been initialized")
    return _attendance_cache
