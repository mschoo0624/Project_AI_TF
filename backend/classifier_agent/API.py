import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import ML.extraction as extraction
import ML.reason_classifier as reason_classifier
import ML.submissions as submissions

app = FastAPI()

# 프론트엔드 Vite 개발 서버(별도 포트)에서 직접 호출할 수 있도록 허용.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=submissions.UPLOAD_DIR), name="uploads")

class ExtractRequest(BaseModel):
    doc_text: str
    source_file: str | None = None

@app.post("/extract")
def extract(req: ExtractRequest):
    return extraction.extract_pdf(req.doc_text, source_file=req.source_file)

class ClassifyRequest(BaseModel):
    reason_text: str

@app.post("/classify")
def classify(req: ClassifyRequest):
    try:
        return {"category": reason_classifier.predict(req.reason_text)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# --- 서류 업로드 → 추출 → 분류 → 관리자 승인/반려 ---

@app.post("/submissions")
def upload_submission(file: UploadFile = File(...), military_number: str | None = Form(None)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    saved_name = f"{uuid.uuid4().hex}_{file.filename}"
    saved_path = submissions.UPLOAD_DIR / saved_name
    with saved_path.open("wb") as out:
        out.write(file.file.read())

    doc_text = extraction.extract_text_from_pdf(saved_path)

    try:
        fields = extraction.extract_pdf(doc_text, source_file=file.filename)
    except RuntimeError as exc:
        fields = {"error": str(exc), "source_file": file.filename, "anomaly_flags": []}

    try:
        category = reason_classifier.predict(doc_text)
    except FileNotFoundError:
        category = None

    return submissions.create(
        filename=file.filename,
        saved_path=f"/uploads/{saved_name}",
        extraction_fields=fields,
        reason_category=category,
        military_number=military_number,
    )


@app.get("/submissions")
def list_submissions():
    return submissions.list_all()


@app.get("/submissions/{submission_id}")
def get_submission(submission_id: str):
    submission = submissions.get(submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="제출 건을 찾을 수 없습니다.")
    return submission


class DecisionRequest(BaseModel):
    decision: str  # "approved" | "declined"
    note: str | None = None

@app.post("/submissions/{submission_id}/decision")
def decide_submission(submission_id: str, req: DecisionRequest):
    try:
        updated = submissions.decide(submission_id, req.decision, req.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="제출 건을 찾을 수 없습니다.")
    return updated