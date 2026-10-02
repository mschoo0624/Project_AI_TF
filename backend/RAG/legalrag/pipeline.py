"""
RAG pipeline = Retriever (find relevant articles) + LLM (write an answer from them).

    from legalrag.pipeline import RagPipeline
    rag = RagPipeline()
    result = rag.ask("예비군 훈련은 1년에 최대 며칠까지 받을 수 있나요?")
    print(result["answer"])
"""

from __future__ import annotations

from typing import Dict, Iterator, Optional

from legalrag.config import Config
from legalrag.prompts import DISCLAIMER, build_messages
from legalrag.retriever import Retriever
from legalrag.utils import get_logger

logger = get_logger(__name__)

NO_LLM_MESSAGE = (
    "LLM이 설정되지 않아 관련 조문만 보여드립니다. "
    "답변 생성을 사용하려면 OPENAI_API_KEY (또는 Ollama용 OPENAI_BASE_URL)을 설정하세요."
)


class RagPipeline:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self.retriever = Retriever(self.cfg)
        self.llm = None
        if self.cfg.llm_enabled:
            from legalrag.llm import LLMClient

            self.llm = LLMClient(self.cfg)
            logger.info("LLM: %s (%s)", self.cfg.llm_model, self.cfg.llm_base_url or "OpenAI")
        else:
            logger.warning("No LLM configured -> retrieval-only mode")

    def search(self, question: str, top_k: Optional[int] = None):
        return self.retriever.search(question, top_k)

    def ask(self, question: str, top_k: Optional[int] = None) -> Dict:
        hits = self.search(question, top_k)
        if self.llm is None:
            answer = NO_LLM_MESSAGE
        else:
            messages = build_messages(question, hits, self.retriever.reference_date())
            try:
                answer = self.llm.chat(messages).strip() + "\n\n" + DISCLAIMER
            except Exception as e:  # quota, network, wrong model name, ...
                logger.error("LLM call failed: %s", e)
                answer = _llm_error_message(e)
        return {"question": question, "answer": answer, "hits": [h.to_dict() for h in hits]}

    def ask_stream(self, question: str, top_k: Optional[int] = None) -> Iterator[Dict]:
        """Yields {"type": "hits", ...} first, then {"type": "token", "text": ...} pieces."""
        hits = self.search(question, top_k)
        yield {"type": "hits", "hits": [h.to_dict() for h in hits]}
        if self.llm is None:
            yield {"type": "token", "text": NO_LLM_MESSAGE}
            return
        messages = build_messages(question, hits, self.retriever.reference_date())
        try:
            for piece in self.llm.chat_stream(messages):
                yield {"type": "token", "text": piece}
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            yield {"type": "error", "text": _llm_error_message(e)}
            return
        yield {"type": "token", "text": "\n\n" + DISCLAIMER}


def _llm_error_message(e: Exception) -> str:
    msg = str(e)
    if "insufficient_quota" in msg or "credit" in msg:
        reason = "OpenAI 계정에 크레딧이 없습니다 (platform.openai.com 결제 설정 확인)."
    elif "401" in msg or "invalid_api_key" in msg:
        reason = "API 키가 올바르지 않습니다."
    else:
        reason = f"{type(e).__name__}: {msg[:300]}"
    return f"LLM 답변 생성 실패 — {reason}\n아래 검색된 조문을 참고하세요."
