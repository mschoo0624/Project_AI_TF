"""Synthetic PDF fixtures for parser mechanics, not application eligibility."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifier_agent.pdf_extract import PDFExtractionError, extract_pdf


def make_pdf(path, *, blank=False):
    # Minimal PDF with ToUnicode mapping: no extra fixture-generation packages.
    texts = ['성명', '홍길동', '성명', '김철수']
    chars = list(dict.fromkeys(''.join(texts)))
    codes = {char: i + 33 for i, char in enumerate(chars)}
    mappings = '\n'.join(f'<{codes[c]:02X}> <{c.encode("utf-16-be").hex()}>' for c in chars)
    cmap = ('/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n'
            '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n'
            '/CMapName /TestUnicode def\n/CMapType 2 def\n'
            '1 begincodespacerange\n<00> <FF>\nendcodespacerange\n'
            f'{len(chars)} beginbfchar\n{mappings}\nendbfchar\n'
            'endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend').encode()
    commands = ['0.5 w']
    for x in [50, 200, 350]:
        commands.append(f'{x} 450 m {x} 550 l S')
    for y in [450, 500, 550]:
        commands.append(f'50 {y} m 350 {y} l S')
    for text, (x, y) in zip(texts, [(60, 520), (210, 520), (60, 470), (210, 470)]):
        encoded = ''.join(f'{codes[c]:02X}' for c in text)
        commands.append(f'BT /F1 12 Tf {x} {y} Td <{encoded}> Tj ET')
    content = b'' if blank else '\n'.join(commands).encode()
    def stream(data):
        return f'<< /Length {len(data)} >>\nstream\n'.encode() + data + b'\nendstream'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 600] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /ToUnicode 6 0 R >>',
        stream(content), stream(cmap),
    ]
    data = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n')
    start = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode())
    path.write_bytes(data)


def test_korean_table_coordinates_and_repeated_fields(tmp_path):
    path = tmp_path / 'form.pdf'
    make_pdf(path)
    before = path.read_bytes()
    result = extract_pdf(path)
    assert result['status'] == 'extracted'
    page = result['pages'][0]
    assert '홍길동' in page['text']
    assert page['tables'][0]['bbox'] == [50, 50, 350, 150]
    assert page['tables'][0]['rows'][0][1]['text'] == '홍길동'
    assert [f['value'] for f in page['field_candidates']] == ['홍길동', '김철수']
    assert path.read_bytes() == before


def test_blank_page_is_not_successful_extraction(tmp_path):
    path = tmp_path / 'blank.pdf'
    make_pdf(path, blank=True)
    result = extract_pdf(path)
    assert result['status'] == 'no_text'
    assert result['pages'][0]['warnings']
    assert result['pages'][0]['field_candidates'] == []


def test_invalid_and_missing_pdf(tmp_path):
    with pytest.raises(PDFExtractionError):
        extract_pdf(tmp_path / 'missing.pdf')
    path = tmp_path / 'invalid.pdf'
    path.write_text('not a PDF')
    with pytest.raises(PDFExtractionError):
        extract_pdf(path)
