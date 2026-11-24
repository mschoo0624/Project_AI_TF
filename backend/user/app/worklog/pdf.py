from __future__ import annotations

from collections import Counter
import os
from pathlib import Path

import pymupdf as fitz
from .classification import postponement_label


FONT = fitz.Font('korea')
FONT_NAME = 'worklog'


CATEGORIES = {
    'transfer_in': '전입자 처리', 'transfer_out': '전출자 처리', 'travel': '출국·귀국 처리',
    'postponement': '보류·연기 처리', 'personnel': '인원 관리', 'assignment': '전투편성',
    'training': '교육훈련', 'prosecution': '고발장', 'organization': '편제 관리',
}


def template_path() -> Path:
    configured = os.environ.get('WORKLOG_TEMPLATE_PATH')
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / 'frontend/public/pdfs/양식/일일 업무일지 양식.pdf'


def _value(value) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return '예' if value else '아니요'
    return str(value)


def _cell(page, rect, value, size=12):
    text = _value(value)
    if not text:
        return
    box = fitz.Rect(rect) + (3, 2, -3, -2)
    while size >= 7:
        shape = page.new_shape()
        if shape.insert_textbox(box, text, fontsize=size, fontname=FONT_NAME) >= 0:
            shape.commit()
            return
        size -= 1
    start, end = 0, len(text)
    fitted = None
    while start <= end:
        length = (start + end) // 2
        shape = page.new_shape()
        if shape.insert_textbox(box, text[:length] + '…', fontsize=7, fontname=FONT_NAME) >= 0:
            fitted = shape
            start = length + 1
        else:
            end = length - 1
    if fitted is not None:
        fitted.commit()


def _postponement_type(event: dict) -> str:
    details = event.get('details') or {}
    kind = postponement_label(details.get('신청 구분'))
    if kind:
        return kind
    for change in details.get('변경 항목', []):
        if change.get('항목') in ('신청 구분', '신청 유형'):
            kind = postponement_label(change.get('이후') or change.get('이전'))
            if kind:
                return kind
    return '보류/연기'


def _fill_form(document, snapshot: dict, revision: int, preview: bool):
    page = document[0]
    page.insert_font(fontname=FONT_NAME, fontbuffer=FONT.buffer)
    # The supplied form is 910 x 1280; preserve its original drawing and headings.
    page.draw_rect(fitz.Rect(195, 140, 500, 190), color=None, fill=(1, 1, 1))
    year, month, day = map(int, snapshot['date'].split('-'))
    page.insert_text((207, 172), f'{year}년 {month}월 {day}일', fontsize=21, fontname=FONT_NAME)
    counts = Counter(event['category'] for event in snapshot['events'])
    _cell(page, (15, 240, 165, 325), '업무 처리 내역', 16)
    state = '미리보기 · 저장 전' if preview else f'저장본 {revision}'
    summary = f"처리 {len(snapshot['events'])}건 · {state}\n"
    summary += ' / '.join(f'{CATEGORIES.get(key, key)} {count}건' for key, count in counts.items())
    if snapshot['notes']:
        summary += f"\n비고: {snapshot['notes']}"
    _cell(page, (165, 240, 895, 325), summary, 15)
    people = {key: [] for key in ('transfer_in', 'transfer_out', 'travel', 'postponement')}
    for event in snapshot['events']:
        if event['category'] in people:
            people[event['category']].extend(
                {**person, 'postponement_type': _postponement_type(event)}
                if event['category'] == 'postponement' else person
                for person in event['people']
            )
    for index, person in enumerate(people['transfer_in'][:11]):
        top = 350 + 25 * index
        for left, right, key in ((85, 165, 'name'), (245, 325, 'unit'), (485, 615, 'address'), (615, 745, 'phone'), (745, 895, 'email')):
            _cell(page, (left, top, right, top + 25), person.get(key))
    for index, person in enumerate(people['transfer_out'][:12]):
        base = 85 + 405 * (index // 6)
        top = 650 + 25 * (index % 6)
        _cell(page, (base, top, base + 80, top + 25), person.get('name'))
        _cell(page, (base + 80, top, base + 160, top + 25), person.get('position'))
    for index, person in enumerate(people['travel'][:18]):
        base = 85 + 405 * (index // 9)
        top = 845 + 25 * (index % 9)
        _cell(page, (base, top, base + 80, top + 25), person.get('name'))
    for index, person in enumerate(people['postponement'][:8]):
        base = 85 + 405 * (index // 4)
        top = 1110 + 30 * (index % 4)
        _cell(page, (base, top, base + 55, top + 30), person.get('name'))
        _cell(page, (base + 155, top, base + 195, top + 30), person.get('position'), 9)
        _cell(page, (base + 355, top, base + 405, top + 30), person['postponement_type'])


def render_pdf(snapshot: dict, *, revision: int, confirmed_by: str, preview: bool = False) -> bytes:
    path = template_path()
    if not path.is_file():
        raise FileNotFoundError(path)
    with fitz.open(path) as document:
        _fill_form(document, snapshot, revision, preview)
        title_state = '미리보기 · 저장 전' if preview else f'저장본 {revision}'
        document.set_metadata({'title': f"{snapshot['date']} 일일 업무일지 ({title_state})", 'author': '' if preview else confirmed_by})
        document.subset_fonts()
        return document.tobytes(garbage=4, deflate=True)
