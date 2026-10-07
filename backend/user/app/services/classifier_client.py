"""HTTP client for the separate Classifier_AITF service."""

import os

import httpx


CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://127.0.0.1:8001").rstrip("/")
VERIFICATION_URL = os.getenv("VERIFICATION_URL", "http://127.0.0.1:8003").rstrip("/")


def get_submission(submission_id: str) -> dict:
    response = httpx.get(f"{VERIFICATION_URL}/submissions/{submission_id}", timeout=15)
    response.raise_for_status()
    return response.json()


def verify_documents(documents: list[dict], context: dict, submission_id: str | None = None) -> dict:
    url = f"{VERIFICATION_URL}/submissions/{submission_id}/verify" if submission_id else f"{VERIFICATION_URL}/verify"
    payload = {"context": context} if submission_id else {"documents": documents, "context": context}
    response = httpx.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def classify_reason(reason_text: str) -> str:
    response = httpx.post(
        f"{CLASSIFIER_URL}/classify",
        json={"reason_text": reason_text},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["category"]


def decide_submission(submission_id: str, decision: str, note: str | None = None) -> dict:
    base = VERIFICATION_URL if submission_id.startswith('qwen_') else CLASSIFIER_URL
    response = httpx.post(
        f"{base}/submissions/{submission_id}/decision",
        json={"decision": decision, "note": note},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
