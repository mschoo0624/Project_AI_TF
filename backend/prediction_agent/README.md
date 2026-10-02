# Dashboard prediction agent

This package owns dashboard population and attendance forecasts. It does not
import or require `classifier_agent` (PDF extraction and application classification).

- `ReserveForces_pop.py`: population forecasting pipeline.
- `attendance.py`: attendance forecast from `data/attendance_log.jsonl`.
- `cache.py`: startup initialization and cached dashboard results.
- `data/`: prediction inputs.
- `forecast_cache.json`, `attendance_forecast_cache.json`: generated caches.

Install standalone prediction dependencies from the repository root:

```powershell
python -m pip install -r backend/prediction_agent/requirements.txt
```

The backend's existing requirements also include these dependencies. From the
`backend` directory, the API imports `prediction_agent.cache` and initializes
both forecasts on startup. Dashboard HTTP routes remain unchanged.

Input paths and cache paths are resolved relative to this package. The existing
`RESERVE_FORCES_DATA_DIR` override remains supported; update an externally
configured path if it explicitly points to the former `backend/prediction/data`.
Population forecasting imports perform model training; attendance forecasting
can be used separately without loading the population model.
