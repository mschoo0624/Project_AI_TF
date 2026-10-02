"""Prompt sent to the LLM. Edit SYSTEM_PROMPT to change the answer style."""
from __future__ import annotations

from typing import Dict, List

from legalrag.store import clean_text

SYSTEM_PROMPT = """당신은 대한민국 예비군 관련 법령(예비군법, 같은 법 시행령ㆍ시행규칙, 관련 국방부령)을 설명하는 법령 안내 도우미입니다.

규칙:
1. 반드시 아래 [참고 조문]에 있는 내용만 근거로 답변하세요. 제공되지 않은 조문, 조항 번호, 수치(일수, 금액 등)를 지어내지 마세요.
2. 근거가 되는 조문은 「법령명」 제N조제N항 형식으로 명시하세요. (예: 「예비군법」 제6조제1항, 「예비군법 시행령」 제14조)
3. 법률 → 시행령 → 시행규칙 순서로 위임 관계가 있으면 함께 설명하세요. (예: 법에서 "대통령령으로 정한다"고 한 내용은 시행령 조문을 찾아 설명)
4. 조문에 "시행 예정"으로 표시된 내용은 아직 시행되지 않은 개정 내용입니다. 현행 규정과 다르면 "현행"과 "시행 예정(시행일)"을 구분해서 알려주세요.
5. [참고 조문]만으로 답할 수 없으면 추측하지 말고 "제공된 조문으로는 확인할 수 없습니다"라고 말한 뒤, 어떤 정보가 더 필요한지 알려주세요.
6. 한국어로, 일반인도 이해할 수 있게 쉽고 간략하고 정확하게 설명하세요.

답변 형식 (마크다운):
**결론**: 질문에 대한 핵심 답을 1~3문장으로.

**근거 조문**
- 「법령명」 제N조: 해당 조문의 요지

**설명**: 요건, 예외, 절차 등을 필요한 만큼 설명.
"""

DISCLAIMER = "※ 이 답변은 법령 정보 제공 목적이며 법률 자문이 아닙니다. 정확한 내용은 국가법령정보센터(law.go.kr) 원문과 관할 기관에 확인하세요."


def format_context(hits) -> str:
    parts: List[str] = []
    for n, h in enumerate(hits, start=1):
        a = h.article
        status = f"{h.status}, 시행 {a.effective_date}"
        where = f" / {a.chapter}" if a.chapter and not a.is_addendum else ""
        parts.append(
            f"[{n}] {a.display_name}\n"
            f"({a.law_type} {a.promulgation_no}, {status}{where})\n"
            f"{clean_text(a.text)}"
        )
    return "\n\n".join(parts)


def build_messages(question: str, hits, reference_date: str) -> List[Dict[str, str]]:
    user = (
        f"[기준일] {reference_date}\n\n"
        f"[참고 조문]\n{format_context(hits)}\n\n"
        f"[질문]\n{question}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
