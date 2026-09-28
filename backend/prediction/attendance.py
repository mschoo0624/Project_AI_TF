"""Attendance-rate forecast for upcoming reserve-training rounds.

Headcount projections (planned/final) per round are provisional planning
inputs, not statistically derived — replace ATTENDANCE_PLAN as real intake
numbers become available. Attendance rate is the historical average of
attended/final for that round type, computed from the logged past sessions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ATTENDANCE_LOG_PATH = Path(__file__).resolve().parent / "data" / "attendance_log.jsonl"

# Provisional 2026 headcount plan per round; not derived from the historical log.
ATTENDANCE_PLAN: list[dict[str, Any]] = [
    {"round": "1차", "date": "2026-04-20", "planned": 190, "final": 180},
    {"round": "2차", "date": "2026-07-20", "planned": 145, "final": 137},
    {"round": "3차", "date": "2026-10-20", "planned": 83, "final": 78},
]  


def load_attendance_log() -> list[dict[str, Any]]:
    if not ATTENDANCE_LOG_PATH.is_file():
        return []
    with ATTENDANCE_LOG_PATH.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def round_average_rates(log: list[dict[str, Any]]) -> dict[str, float]:
    """Average attended/final rate per round type (e.g. "1차"), across all logged years."""
    totals: dict[str, list[float]] = {}
    for entry in log:
        round_id = entry["session"].split("-", 1)[1]
        rate = entry["attended_count"] / entry["final_count"]
        totals.setdefault(round_id, []).append(rate)
    return {round_id: sum(rates) / len(rates) for round_id, rates in totals.items()}


def generate_attendance_forecast() -> dict[str, Any]:
    log = load_attendance_log()
    rates = round_average_rates(log)

    rounds = []
    for plan in ATTENDANCE_PLAN:
        rate = rates.get(plan["round"], 0.0)
        final = plan["final"]
        attended = round(final * rate)
        rounds.append({
            "round": plan["round"],
            "date": plan["date"],
            "planned": plan["planned"],
            "final": final,
            "attended": attended,
            "absent": final - attended,
            "rate": round(rate, 3),
        })

    return {"rounds": rounds, "history_sessions": len(log)}
