"""Traceable layout sources and conservative whitespace/date normalization."""
import re
from datetime import date


def compact(text):
    return re.sub(r'\s+', '', text)


def dates(text):
    # Normalize digit spacing only inside a complete date, not arbitrary numbers.
    pattern = r'(?<!\d)(\d(?:[ \t]*\d){3})\s*(?:년|[-./])\s*(\d(?:[ \t]*\d)?)\s*(?:월|[-./])\s*(\d(?:[ \t]*\d)?)(?!\d)'
    found = []
    for m in re.finditer(pattern, text):
        try:
            value = date(*(int(compact(v)) for v in m.groups())).isoformat()
        except ValueError:
            continue
        found.append((value, m.group(0)))
    return found


def normalized(text):
    for value, original in dates(text):
        text = text.replace(original, value)
    return re.sub(r'\s+', ' ', text).strip()


def make_sources(page, tables):
    """Use cells first; preserve every remaining word as a positioned line."""
    sources, boxes = [], set()
    def add(text, box, **extra):
        if not text.strip(): return
        sources.append({'id': f'p{page.page_number}s{len(sources)+1}', 'text': text,
                        'normalized_text': normalized(text),
                        'bbox': [round(v, 3) for v in box], **extra})
    # Open-ended government forms often omit the outside vertical borders.
    # Close only bands backed by two actual horizontal rules; use actual dividers.
    horizontals = sorted([e for e in page.edges if e.get('orientation') == 'h' and e['x1']-e['x0'] > 100], key=lambda e: e['top'])
    unique = []
    for edge in horizontals:
        if not unique or abs(unique[-1]['top']-edge['top']) > 2: unique.append(edge)
    bands = []
    for upper, lower in zip(unique, unique[1:]):
        top, bottom = upper['top'], lower['top']
        left, right = max(upper['x0'], lower['x0']), min(upper['x1'], lower['x1'])
        if not 10 < bottom-top < 150 or right-left < 100: continue
        xs = [left, right] + [e['x0'] for e in page.edges if e.get('orientation') == 'v' and
              left+2 < e['x0'] < right-2 and e['top'] <= top+2 and e['bottom'] >= bottom-2]
        xs = sorted(set(round(x, 1) for x in xs))
        row = []
        for a,b in zip(xs,xs[1:]):
            if b-a < 3: continue
            region = page.filter(lambda c: c.get('object_type') == 'char' and a <= (c['x0']+c['x1'])/2 < b and top <= (c['top']+c['bottom'])/2 < bottom)
            row.append({'text': region.extract_text() or '', 'bbox': [a,top,b,bottom]})
        bands.append(row)
    if bands:
        tables = [{'number': 0, 'rows': bands}]
    for table in tables:
        for r, row in enumerate(table['rows'], 1):
            for col, cell in enumerate(row, 1):
                if not cell or tuple(cell['bbox']) in boxes: continue
                box = tuple(cell['bbox']); boxes.add(box)
                x0, top, x1, bottom = box
                chars = page.filter(lambda c: c.get('object_type') == 'char' and
                    x0 <= (c['x0']+c['x1'])/2 < x1 and top <= (c['top']+c['bottom'])/2 < bottom)
                text = chars.extract_text() or ''
                label = next((c['text'] for c in reversed(row[:col-1]) if c and c['text'].strip()), '')
                add(text, box, kind='cell', table=table['number'], row=r, column=col,
                    label=label[:120], font_size=max((c['size'] for c in chars.chars), default=0))
    remaining = []
    for word in page.extract_words(extra_attrs=['size']):
        cx, cy = (word['x0']+word['x1'])/2, (word['top']+word['bottom'])/2
        if not any(a <= cx < c and b <= cy < d for a,b,c,d in boxes): remaining.append(word)
    lines = []
    for word in sorted(remaining, key=lambda w: (w['top'], w['x0'])):
        line = next((line for line in lines if abs(line[0]['top']-word['top']) < 3), None)
        if line is None: lines.append([word])
        else: line.append(word)
    for line in lines:
        line.sort(key=lambda w: w['x0'])
        add(' '.join(w['text'] for w in line),
            (min(w['x0'] for w in line),min(w['top'] for w in line),max(w['x1'] for w in line),max(w['bottom'] for w in line)),
            kind='line', font_size=round(max(w['size'] for w in line), 2))
    return sources


def sources_for(page):
    return page.get('sources') or [{'id': f'p{page["number"]}l{i}', 'text': text,
             'normalized_text': normalized(text), 'kind': 'line', 'bbox': None}
             for i, text in enumerate(page['text'].splitlines(), 1) if text.strip()]
