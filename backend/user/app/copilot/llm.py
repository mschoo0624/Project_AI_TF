"""Tool selection through the internal Ollama server (OpenAI-compatible /v1).

The LLM only picks a tool name and JSON arguments; answers are built from templates.
Local-only: requests to anything other than localhost or a private address are refused,
same policy as classifier_agent/ML/extraction.py.
"""

from __future__ import annotations

import ipaddress
import json
import os
from urllib.parse import urlparse

import httpx

from user.app.copilot.tools import TOOLS

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
COPILOT_MODEL = os.environ.get("COPILOT_MODEL", "qwen2.5:7b")
TIMEOUT_SECONDS = float(os.environ.get("COPILOT_LLM_TIMEOUT", "60"))

SYSTEM_PROMPT = (
	"너는 예비군 업무 Copilot이다. 사용자 요청에 맞는 도구를 하나만 골라 호출한다. "
	"맞는 도구가 없으면 도구를 호출하지 말고 '지원하지 않는 요청'이라고만 답한다. "
	"요청에 없는 조건은 인자로 넣지 않는다."
)


class LLMUnavailable(RuntimeError):
	pass


def _ensure_local(host: str) -> None:
	hostname = urlparse(host).hostname or ""
	if hostname == "localhost":
		return
	try:
		address = ipaddress.ip_address(hostname)
	except ValueError:
		raise LLMUnavailable(f"OLLAMA_HOST({host})는 내부 주소(IP)여야 합니다.") from None
	if not (address.is_loopback or address.is_private):
		raise LLMUnavailable(f"OLLAMA_HOST({host})가 내부 주소가 아니라 호출하지 않습니다.")


def _tool_specs() -> list[dict]:
	return [
		{
			"type": "function",
			"function": {
				"name": tool.name,
				"description": tool.description,
				"parameters": tool.args_model.model_json_schema(),
			},
		}
		for tool in TOOLS.values()
	]


def choose_tool(message: str) -> tuple[str, dict] | None:
	"""Return (tool name, raw arguments) or None when the model calls no tool."""
	_ensure_local(OLLAMA_HOST)
	payload = {
		"model": COPILOT_MODEL,
		"messages": [
			{"role": "system", "content": SYSTEM_PROMPT},
			{"role": "user", "content": message},
		],
		"tools": _tool_specs(),
		"temperature": 0,
	}
	try:
		response = httpx.post(f"{OLLAMA_HOST.rstrip('/')}/v1/chat/completions", json=payload, timeout=TIMEOUT_SECONDS)
		response.raise_for_status()
	except httpx.HTTPError as error:
		raise LLMUnavailable(f"Copilot 모델 서버({OLLAMA_HOST}, {COPILOT_MODEL})에 연결하지 못했습니다: {error}") from error

	calls = response.json()["choices"][0]["message"].get("tool_calls") or []
	if not calls:
		return None
	function = calls[0]["function"]
	arguments = function.get("arguments") or "{}"
	return function["name"], json.loads(arguments) if isinstance(arguments, str) else arguments
