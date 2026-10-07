"""Electronic PDF extraction. No OCR, LLM, database or legacy dependencies."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError


class PDFExtractionError(ValueError):
    """A document cannot be read as an electronic PDF."""


DEFAULT_LABELS = (
    "성명", "이름", "군번", "생년월일", "소속", "직위", "직급", "직종",
    "담당업무", "재직기간", "학교명", "학과", "학적상태", "진단명", "치료기간",
    "발급일", "발급기관",
)


def _box(value: Any) -> list[float] | None:
    return [round(float(v), 3) for v in value] if value is not None else None


def _label(value: str) -> str:
    return "".join(value.split()).rstrip(":：")


def extract_pdf(
    path: str | Path, *, table_strategy: str = "lines",
    labels: tuple[str, ...] = DEFAULT_LABELS,
) -> dict[str, Any]:
    """Extract page text, word boxes, tables and explicit right-cell field candidates.

    Bounding boxes use PDF points and a top-left origin: x0, top, x1, bottom.
    Null cells are table-grid placeholders, not invented empty text. Field
    candidates only link exact labels to the immediately adjacent right cell;
    they are not semantic interpretation or verified application facts.
    """
    source = Path(path)
    if not source.is_file():
        raise PDFExtractionError("PDF 파일을 찾을 수 없습니다.")
    if table_strategy not in {"lines", "text"}:
        raise PDFExtractionError("표 추출 방식은 lines 또는 text여야 합니다.")
    label_map = {_label(label): label for label in labels}
    settings = {"vertical_strategy": table_strategy, "horizontal_strategy": table_strategy}
    pages = []
    try:
        with source.open("rb") as file:
            if b"%PDF-" not in file.read(1024):
                raise PDFExtractionError("올바른 PDF 파일이 아닙니다.")
        with pdfplumber.open(source, unicode_norm="NFC") as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                words = [
                    {"text": word["text"], "bbox": _box((word["x0"], word["top"], word["x1"], word["bottom"]))}
                    for word in page.extract_words()
                ]
                tables = []
                fields = []
                # Image-only pages are reported, never silently accepted as extracted.
                if text.strip():
                    for number, table in enumerate(page.find_tables(settings), start=1):
                        rows_text = table.extract()
                        rows = []
                        for row_index, row in enumerate(table.rows):
                            cells = []
                            for column_index, bbox in enumerate(row.cells):
                                cells.append(None if bbox is None else {
                                    "text": rows_text[row_index][column_index] or "",
                                    "bbox": _box(bbox),
                                })
                            rows.append(cells)
                            for column_index, cell in enumerate(cells[:-1]):
                                if cell is None:
                                    continue
                                label = label_map.get(_label(cell["text"]))
                                value = cells[column_index + 1]
                                if label and value and value["text"].strip() and _label(value["text"]) not in label_map:
                                    fields.append({
                                        "label": label, "raw_label": cell["text"],
                                        "value": value["text"], "method": "adjacent_right_cell",
                                        "table": number, "row": row_index + 1,
                                        "label_column": column_index + 1,
                                        "label_bbox": cell["bbox"], "value_bbox": value["bbox"],
                                    })
                        tables.append({"number": number, "bbox": _box(table.bbox), "rows": rows})
                warnings = []
                if not text.strip():
                    warnings.append("텍스트 레이어가 없거나 읽을 수 없는 페이지입니다. 스캔·빈 페이지 등은 수동 확인이 필요합니다. OCR은 수행하지 않습니다.")
                elif page.images:
                    warnings.append("이미지가 포함되어 있습니다. 이미지 안의 글자는 추출하지 않습니다.")
                pages.append({
                    "number": page.page_number, "width": float(page.width),
                    "height": float(page.height), "status": "extracted" if text.strip() else "no_text",
                    "text": text, "words": words, "tables": tables,
                    "field_candidates": fields, "warnings": warnings,
                })
    except PDFPasswordIncorrect as exc:
        raise PDFExtractionError("암호로 보호된 PDF는 지원하지 않습니다.") from exc
    except (PDFSyntaxError, OSError) as exc:
        raise PDFExtractionError("PDF를 읽을 수 없습니다. 파일 형식과 접근 권한을 확인하세요.") from exc
    readable = sum(page["status"] == "extracted" for page in pages)
    return {
        "schema_version": 1, "source_file": source.name,
        "status": "no_text" if not readable else "extracted" if readable == len(pages) else "partial",
        "table_strategy": table_strategy,
        "coordinate_system": "PDF points; top-left origin; bbox=[x0, top, x1, bottom]",
        "page_count": len(pages), "pages": pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="전자 PDF의 표·텍스트·셀 좌표를 JSON으로 추출합니다.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="생략하면 표준 출력으로 반환")
    parser.add_argument("--table-strategy", choices=("lines", "text"), default="lines")
    args = parser.parse_args()
    if args.output and args.output.resolve() == args.pdf.resolve():
        parser.error("출력 경로는 입력 PDF와 달라야 합니다.")
    try:
        result = extract_pdf(args.pdf, table_strategy=args.table_strategy)
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            # Refuse to overwrite a prior result by accident.
            with args.output.open("x", encoding="utf-8") as file:
                file.write(payload + "\n")
        else:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            print(payload)
        return 0 if result["status"] == "extracted" else 2
    except (PDFExtractionError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
