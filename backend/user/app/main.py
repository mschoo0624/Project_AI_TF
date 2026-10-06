import asyncio
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
# Importing the files from the other folders. 
from user.app.database import SessionLocal, engine, init_db
from user.app.api.dashboard import router as dashboard_router
from user.app.api.auth import router as auth_router
from user.app.api.postponements import router as postponements_router
from user.app.api.reservists import persons_router, router as reservists_router
from user.app.api.squads import router as squads_router
from user.app.api.organization import router as organization_router
from prediction.cache import initialize_attendance_cache, initialize_prediction_cache
from user.app.api.training import (
    persons_training_router,
    router as training_router,
)
from user.app.api.training_results import router as training_results_router
from user.app.api.transfers import router as transfers_router
from user.app.services.training import reconcile_all_due_training_absences
from user.app.services.training_recalculation import recalculate_ended_holds, run_jan1_rollover

logger = logging.getLogger(__name__)
_training_reconciliation_task: asyncio.Task[None] | None = None

app = FastAPI(title="Project AI TF API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(training_results_router)
app.include_router(reservists_router)
app.include_router(persons_router)
app.include_router(squads_router)
app.include_router(organization_router)
app.include_router(dashboard_router)
app.include_router(postponements_router)
app.include_router(training_router)
app.include_router(persons_training_router)
app.include_router(transfers_router)

def _reconcile_due_training_records() -> None:
    with SessionLocal() as db:
        reconcile_all_due_training_absences(db)
        run_jan1_rollover(db)
        recalculate_ended_holds(db)
        db.commit()


async def _training_reconciliation_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_reconcile_due_training_records)
        except Exception:
            logger.exception("Scheduled training reconciliation failed")
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup() -> None:
    global _training_reconciliation_task
    init_db()
    initialize_prediction_cache()
    initialize_attendance_cache()
    _training_reconciliation_task = asyncio.create_task(_training_reconciliation_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    if _training_reconciliation_task is not None:
        _training_reconciliation_task.cancel()
        try:
            await _training_reconciliation_task
        except asyncio.CancelledError:
            pass

@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Project AI TF API is running"}


@app.get("/health/db")
def check_database() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    return {"status": "ok", "database": "sqlite"}


@app.get("/db/tables")
def list_database_tables() -> dict[str, object]:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    with engine.connect() as connection:
        row_counts = {
            table: connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            for table in tables
        }

    return {"database": "sqlite", "tables": row_counts}


@app.get("/db/tables/{table_name}")
def read_database_table(table_name: str) -> dict[str, object]:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if table_name not in tables:
        raise HTTPException(status_code=404, detail="Table not found")

    columns = [column["name"] for column in inspector.get_columns(table_name)]
    if table_name == "app_user":
        columns = [column for column in columns if column != "password_hash"]

    selected_columns = ", ".join(f'"{column}"' for column in columns)
    query = text(f'SELECT {selected_columns} FROM "{table_name}"')
    with engine.connect() as connection:
        rows = [dict(row._mapping) for row in connection.execute(query)]

    return {"database": "sqlite", "table": table_name, "rows": rows}
