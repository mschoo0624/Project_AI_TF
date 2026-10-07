"""Extract existing demo PDFs, retain coordinates, and prepare fixed-model inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from backend.classifier_agent.pdf_extract import extract_pdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf-dir', type=Path, default=ROOT/'frontend/public/pdfs')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    expected_file = Path(__file__).with_name('cases.frontend_pdfs.expected.json')
    gold = json.loads(expected_file.read_text(encoding='utf-8'))
    (args.output/'expected.json').write_bytes(expected_file.read_bytes())
    (args.output/'preparer_source.py.txt').write_bytes(Path(__file__).read_bytes())
    extractor = ROOT/'backend/classifier_agent/pdf_extract.py'
    (args.output/'pdf_extract.py.txt').write_bytes(extractor.read_bytes())
    assert {p.name for p in args.pdf_dir.glob('*.pdf')} == {x['filename'] for x in gold['cases']}
    cases, stats = [], []
    for item in gold['cases']:
        source = args.pdf_dir/item['filename']
        start = time.perf_counter()
        lines = extract_pdf(source, table_strategy='lines')
        text_tables = extract_pdf(source, table_strategy='text')
        elapsed = time.perf_counter()-start
        for strategy, extraction in [('lines', lines), ('text', text_tables)]:
            (args.output/(item['id']+'.'+strategy+'.json')).write_text(
                json.dumps(extraction, ensure_ascii=False, indent=2), encoding='utf-8')
        # Full page text stays authoritative. Guessed table cells can truncate content.
        document = '\n\n'.join(f'[PAGE {p["number"]}]\n{p["text"]}' for p in lines['pages'])
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        anchors = [q for g in item['expected'].values() for q in g['evidence_must_include']]
        missing = [q for q in anchors if q not in document]
        if lines['status'] != 'extracted' or missing:
            raise ValueError(f'{source.name}: unreadable or missing expected source anchors: {missing}')
        (args.output/(item['id']+'.input.txt')).write_text(document, encoding='utf-8')
        cases.append({**item, 'document': document, 'pdf_sha256': source_hash,
                      'origin': 'existing_repository_demo_pdf_via_pdfplumber'})
        stats.append({'filename': source.name, 'sha256': source_hash,
                      'pages': lines['page_count'], 'status': lines['status'],
                      'text_chars': sum(len(p['text']) for p in lines['pages']),
                      'lines_tables': sum(len(p['tables']) for p in lines['pages']),
                      'text_tables': sum(len(p['tables']) for p in text_tables['pages']),
                      'expected_source_anchors': len(anchors), 'missing_anchors': missing,
                      'both_strategies_seconds': elapsed})
    case_data = {'version': 1, 'synthetic': True,
                 'scope': 'PDF -> pdfplumber full page text -> Qwen stage-2 extraction on repository demo PDFs. No eligibility or authenticity decisions.',
                 'source_pipeline': {'pdf_dir': args.pdf_dir.as_posix(),
                                     'extractor_sha256': hashlib.sha256(extractor.read_bytes()).hexdigest(),
                                     'gold_sha256': hashlib.sha256(expected_file.read_bytes()).hexdigest(),
                                     'model_input': 'full page text; guessed tables retained separately, not passed to model'},
                 'cases': cases}
    (args.output/'cases.json').write_text(json.dumps(case_data, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'extraction_summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
