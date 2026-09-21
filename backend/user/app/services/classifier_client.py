"""HTTP client for the separate Classifier_AITF service."""

import os

import httpx


CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://127.0.0.1:8001").rstrip("/")


def classify_reason(reason_text: str) -> str:
    response = httpx.post(
        f"{CLASSIFIER_URL}/classify",
        json={"reason_text": reason_text},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["category"]


def decide_submission(submission_id: str, decision: str) -> dict:
    response = httpx.post(
        f"{CLASSIFIER_URL}/submissions/{submission_id}/decision",
        json={"decision": decision},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()