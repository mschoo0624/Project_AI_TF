from fastapi import FastAPI, HTTPException
from sqlalchemy import inspect, text

from user.app.database import engine, init_db

app = FastAPI(title="Project AI TF API")


@app.on_event("startup")
def startup() -> None:
    init_db()


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
