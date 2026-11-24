"""결재 답변에 붙이는 관련 법령.

법령 챗봇(RAG)의 검색만 쓴다. LLM으로 요약하거나 판단하지 않고, 찾은 조문의 이름만 그대로 보여 준다.
법령 챗봇이 아직 로딩 중이거나 쓸 수 없으면 아무것도 붙이지 않는다(결재 답변은 그대로 나간다).
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

RAG_MODULE = "RAG.legalrag.server"
QUERIES = {
	"연기": "예비군 훈련 연기 사유와 신청 절차, 증빙 서류",
	"보류": "예비군 훈련 보류 사유와 증빙 서류",
}
PER_KIND = 3
MAX_SHOWN = 4

# 법령은 자주 바뀌지 않으므로 한 번 찾은 결과를 프로세스가 사는 동안 재사용한다. 못 찾은 경우는 저장하지 않는다.
_cache: dict[str, list[str]] = {}


def _pipeline():
	module = sys.modules.get(RAG_MODULE)  # 법령 챗봇을 불러오지 않은 환경(테스트 등)에서는 쓰지 않는다.
	return getattr(module, "_rag", None) if module is not None else None


def _lookup(kind: str) -> list[str]:
	if kind in _cache:
		return _cache[kind]
	query = QUERIES.get(kind)
	rag = _pipeline()
	if query is None or rag is None:
		return []
	try:
		hits = rag.search(query, PER_KIND)
	except Exception:  # 법령 검색 실패가 결재 답변을 막으면 안 된다.
		logger.warning("관련 법령을 찾지 못했습니다 (%s)", kind, exc_info=True)
		return []
	lines = []
	for hit in hits[:PER_KIND]:
		info = hit.to_dict()
		passages = ", ".join(str(label) for label in info.get("passages") or [] if label and label != "전문")
		lines.append(f"· {info['title']}" + (f" {passages}" if passages else ""))
	if lines:
		_cache[kind] = lines
	return lines


def reference_block(kinds: list[str]) -> str:
	"""답변 끝에 붙일 문단. 붙일 법령이 없으면 빈 문자열."""
	seen: list[str] = []
	for kind in kinds:
		for line in _lookup(kind):
			if line not in seen:
				seen.append(line)
	if not seen:
		return ""
	return ("\n\n참고 법령 (법령 챗봇 자동 검색, 해석은 담당자가 확인)\n" + "\n".join(seen[:MAX_SHOWN])
		+ "\n조문 내용은 법령 탭에서 확인하세요.")
