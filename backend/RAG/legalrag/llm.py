"""
LLM client for any OpenAI-compatible Chat Completions API.

  OpenAI  : OPENAI_API_KEY=sk-...                  OPENAI_MODEL=gpt-4o-mini
  Ollama  : OPENAI_BASE_URL=http://localhost:11434/v1   OPENAI_MODEL=qwen2.5:7b   (free, local)
  others  : any server exposing /v1/chat/completions (vLLM, LM Studio, ...)
"""
from __future__ import annotations

from typing import Dict, Iterator, List

from legalrag.config import Config


def _supports_temperature(model: str) -> bool:
    # reasoning-style models reject a custom temperature
    m = model.lower()
    return not (m.startswith(("o1", "o3", "o4", "gpt-5")))


class LLMClient:
    def __init__(self, cfg: Config):
        from openai import OpenAI

        self.cfg = cfg
        self.model = cfg.llm_model
        self.client = OpenAI(
            api_key=cfg.llm_api_key or "not-needed",   # Ollama ignores the key
            base_url=cfg.llm_base_url or None,
            timeout=cfg.llm_timeout,
            max_retries=2,
        )

    def _kwargs(self, messages: List[Dict[str, str]]) -> Dict:
        kw = {"model": self.model, "messages": messages}
        if _supports_temperature(self.model):
            kw["temperature"] = self.cfg.llm_temperature
        return kw

    def chat(self, messages: List[Dict[str, str]]) -> str:
        resp = self.client.chat.completions.create(**self._kwargs(messages))
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages: List[Dict[str, str]]) -> Iterator[str]:
        stream = self.client.chat.completions.create(stream=True, **self._kwargs(messages))
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
