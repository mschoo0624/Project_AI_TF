from fastapi import FastAPI

app = FastAPI(title="Project AI TF API")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Project AI TF API is running"}
