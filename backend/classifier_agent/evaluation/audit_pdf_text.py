"""Compare extracted text against literal demo fields in the PDF generator (no execution)."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('extraction_dir', type=Path)
    args = parser.parse_args()
    source = ROOT/'frontend/src/features/review/archive/generate_pdfs.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    bodies, default = {}, None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if 'BODY' in names:
            bodies = {k.attr.lower(): ast.literal_eval(v) for k, v in zip(node.value.keys, node.value.values)}
        elif 'DEFAULT_BODY' in names:
            default = ast.literal_eval(node.value)
    if not bodies or default is None:
        raise ValueError('Generator structure changed; review manually')
    results = []
    for path in sorted(args.extraction_dir.glob('*.lines.json')):
        name = path.name.removesuffix('.lines.json')
        text = '\n'.join(p['text'] for p in json.loads(path.read_text(encoding='utf-8'))['pages'])
        expected = bodies.get(name, default)
        fields = [{'label': label, 'value': value, 'label_found': label in text, 'value_found': value in text}
                  for label, value in expected]
        results.append({'file': name+'.pdf', 'body_fields': fields,
                        'matches_generator_fields': all(x['label_found'] and x['value_found'] for x in fields)})
    report = {'source': source.relative_to(ROOT).as_posix(),
              'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'method': 'Literal BODY/default label and value occurrence checks against full page text; not OCR accuracy or full layout validation.',
              'files': len(results), 'matched_files': sum(x['matches_generator_fields'] for x in results),
              'body_fields': sum(len(x['body_fields']) for x in results), 'results': results}
    out = args.extraction_dir/'generator_text_audit.json'
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print({k: v for k, v in report.items() if k != 'results'})


if __name__ == '__main__':
    main()
