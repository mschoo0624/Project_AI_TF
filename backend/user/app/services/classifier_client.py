"""HTTP client for the classifier routes in the integrated business server."""

import os
import re

import httpx


VERIFICATION_URL = os.getenv("VERIFICATION_URL", "http://127.0.0.1:8002/classifier-api").rstrip("/")


def validate_submission_id(submission_id: str) -> None:
    if not re.fullmatch(r'qwen_[0-9a-f]{32}', submission_id):
        from fastapi import HTTPException
        raise HTTPException(422, '현재 분류기로 제출된 문서만 처리할 수 있습니다.')


def get_submission(submission_id: str) -> dict:
    validate_submission_id(submission_id)
    response = httpx.get(f"{VERIFICATION_URL}/submissions/{submission_id}", timeout=15)
    response.raise_for_status()
    return response.json()


def verify_documents(documents: list[dict], context: dict, submission_id: str | None = None) -> dict:
    if submission_id: validate_submission_id(submission_id)
    url = f"{VERIFICATION_URL}/submissions/{submission_id}/verify" if submission_id else f"{VERIFICATION_URL}/verify"
    payload = {"context": context} if submission_id else {"documents": documents, "context": context}
    response = httpx.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def decide_submission(submission_id: str, decision: str, note: str | None = None) -> dict:
    validate_submission_id(submission_id)
    response = httpx.post(
        f"{VERIFICATION_URL}/submissions/{submission_id}/decision",
        json={"decision": decision, "note": note},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
