"""검토함에서 실제로 열리는 더미 PDF 생성.

프론트엔드 전용 스크립트입니다. models.py / dataset.py 는 건드리지
않습니다 — 여기서 만드는 파일은 frontend/public/pdfs/ 에만 들어갑니다.

    python generate_pdfs.py

DocType 이름과 정확히 같은 파일명(예: employment.pdf)으로 만듭니다.
export_frontend.py 가 file_path 를 "/pdfs/{이름}.pdf" 로 내보내므로,
Vite 의 public/ 서빙 규칙에 따라 그대로 열립니다.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from models import DocType

KFONT = "HYSMyeongJo-Medium"
pdfmetrics.registerFont(UnicodeCIDFont(KFONT))
W, H = A4
OUT = Path("frontend/public/pdfs")

BODY = {
    DocType.EMPLOYMENT: [("소속", "OO경찰서"), ("직위", "경위"), ("재직기간", "2019-03 ~ 현재")],
    DocType.ENROLLMENT: [("학교", "OO대학교"), ("학과", "OO학과"), ("재학기간", "2024-03 ~ 재학중")],
    DocType.MEDICAL: [("병명", "요추 추간판탈출증"), ("진료일", "2026-04-28"),
                       ("소견", "약 4주간 안정 및 물리치료 요함")],
    DocType.DEATH: [("고인", "OOO"), ("관계", "부"), ("사망일시", "2026-05-18")],
    DocType.EXIT_ENTRY: [("출국일", "2025-03-18"), ("귀국일", "미귀국"), ("체류국", "베트남")],
    DocType.BOARDING: [("선박명", "HANARO No.7"), ("직책", "3등항해사"), ("승선일", "2026-03-02")],
    DocType.DISEMBARK: [("선박명", "HANARO No.7"), ("하선일", "2026-04-01")],
    DocType.EXAM: [("시험", "2026년도 정보처리기사 실기"), ("수험번호", "26-2-04117")],
}
DEFAULT_BODY = [("확인사항", "시연용 더미 문서입니다"), ("비고", "-")]


def make(doc_type: DocType, out: Path) -> None:
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle(doc_type.value)

    c.setFont(KFONT, 22)
    c.drawCentredString(W / 2, H - 110, doc_type.value)
    c.line(90, H - 128, W - 90, H - 128)

    y = H - 175
    c.setFont(KFONT, 12)
    for label, value in [("성명", "홍길동"), ("군번", "22-76010001")]:
        c.drawString(100, y, label); c.drawString(190, y, value); y -= 26

    y -= 10; c.line(100, y, W - 100, y); y -= 30

    for label, value in BODY.get(doc_type, DEFAULT_BODY):
        c.drawString(100, y, label); c.drawString(190, y, value); y -= 26

    y -= 30
    c.drawString(100, y, "발급일자 : 2026년 04월 19일"); y -= 22
    c.setFont(KFONT, 10)
    c.drawString(100, y, "문서확인번호 : 1734-5821-9043-2216")

    c.setFont(KFONT, 8)
    c.drawCentredString(W / 2, 55, "시연용 더미 문서 — 실제 발급 서류가 아닙니다")
    c.save()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for t in DocType:
        make(t, OUT / f"{t.name.lower()}.pdf")
    print(f"{OUT} 에 {len(list(DocType))}개 PDF 생성 완료")


if __name__ == "__main__":
    main()
