"""Explicit, read-only business-DB evaluation of the two user-provided PDFs.

Run as a module; never creates submissions or changes business records.
"""
from pathlib import Path
import argparse
from datetime import datetime
import hashlib
import json
import os
import sqlite3
import time

from backend.classifier_agent.extraction import extract_application, ask_qwen
from backend.classifier_agent.pdf_extract import extract_pdf
from backend.classifier_agent.verification import verify_application


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reuse-responses', type=Path, help='Reuse only byte-identical saved model requests; new requests still call Qwen.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    out = Path(__file__).parent / 'runs' / ('user_pdfs_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True, exist_ok=False)
    def save(name, obj):
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    cases = [('medical', '홍길동.pdf', 'postponement.illness'), ('exam', '홍진호.pdf', 'postponement.exam')]
    save('manifest.json', {'model': os.getenv('CLASSIFIER_MODEL', 'qwen3:4b-instruct'),
        'cases': cases, 'scope': 'Actual PDFs -> production pdfplumber/Qwen extraction -> production rules. Read-only DB identity lookup. No submission, approval or training writes.',
        'context_policy': 'No invented training dates, identity, counts, authenticity or document acceptance. Use only a unique exact-name match from DB after extraction.',
        'fresh_context_per_request': True,
        'reused_run': str(args.reuse_responses) if args.reuse_responses else None})
    print('RESULT_DIR=' + str(out.relative_to(root)), flush=True)
    results = []
    for case, filename, kind in cases:
        start = time.monotonic()
        path = root / 'frontend/public/pdfs' / filename
        print(case + ': reading PDF', flush=True)
        pdf = extract_pdf(path)
        save(case + '.pdf.json', pdf)
        save(case + '.input.json', {'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'application_type': kind})
        calls = []
        cached = {}
        if args.reuse_responses:
            for previous in json.loads((args.reuse_responses / (case + '.calls.json')).read_text(encoding='utf-8')):
                if 'response' in previous:
                    cached[json.dumps(previous['messages'], ensure_ascii=False)] = previous['response']
        def client(messages):
            item = {'messages': messages}
            calls.append(item)
            save(case + '.calls.json', calls)
            print(f'{case}: Qwen batch {len(calls)}', flush=True)
            try:
                key = json.dumps(messages, ensure_ascii=False)
                item['reused_response'] = key in cached
                item['response'] = cached[key] if key in cached else ask_qwen(messages)
                return item['response']
            except Exception as exc:
                item['error'] = str(exc)
                raise
            finally:
                save(case + '.calls.json', calls)
        try:
            extraction = extract_application(path, kind, client=client)
            save(case + '.extraction.json', extraction)
            name = extraction['fields'].get('subject_name', {})
            context = {}
            matches = []
            if name.get('status') == 'observed' and isinstance(name.get('value'), str):
                dbpath = root / 'backend/project_ai_tf.db'
                with sqlite3.connect(dbpath.resolve().as_uri() + '?mode=ro', uri=True) as db:
                    matches = db.execute('SELECT military_number, name FROM person WHERE name=?', (name['value'].strip(),)).fetchall()
                if len(matches) == 1:
                    number, person_name = matches[0]
                    context = {k: {'value': v, 'source': 'person:' + number} for k, v in [('applicant_name', person_name), ('applicant_service_number', number)]}
            save(case + '.context.json', {'context': context, 'exact_name_matches': len(matches)})
            verification = verify_application([extraction], context)
            save(case + '.verification.json', verification)
            result = {'case': case, 'file': filename, 'extraction_status': extraction['status'],
                      'result': verification['result_label'], 'name_matches': len(matches),
                      'fields': extraction['fields'], 'missing_information': verification['missing_information']}
        except Exception as exc:
            result = {'case': case, 'file': filename, 'error': str(exc), 'error_type': type(exc).__name__}
        result['elapsed_seconds'] = round(time.monotonic() - start, 2)
        results.append(result)
        save('summary.json', results)
        print(case + ': ' + result.get('error', result.get('result', 'done')), flush=True)
    print('COMPLETE', flush=True)


if __name__ == '__main__':
    main()
