"""Explicit, repeat-safe reprocessing of a legacy PDF through the new pipeline."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import sqlite3

from fastapi import UploadFile
from .API import create_submission, verify_submission, StoredVerification
from .extraction import selected_fields
from . import submissions


def reprocess(legacy_id, application_type, legacy_dir, project_db):
    selected_fields(application_type)  # Type is supplied by the operator, never guessed from an old model.
    legacy_dir = Path(legacy_dir).resolve()
    rows = [json.loads(line) for line in (legacy_dir/'submissions.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    old = next((r for r in rows if r['id'] == legacy_id), None)
    if old is None: raise ValueError('과거 제출 ID를 찾을 수 없습니다.')
    uploads = (legacy_dir/'uploads').resolve()
    pdf = (uploads / Path(old['saved_path']).name).resolve()
    if not pdf.is_relative_to(uploads) or not pdf.is_file(): raise ValueError('과거 PDF 경로가 올바르지 않습니다.')
    project_db = Path(project_db).resolve()
    with sqlite3.connect(project_db.as_uri()+'?mode=ro', uri=True) as db:
        person = db.execute('SELECT military_number, name FROM person WHERE military_number=?', (old.get('military_number'),)).fetchone()
    if person is None: raise ValueError('등록된 대상자를 찾을 수 없습니다.')
    existing = next((r for r in submissions.list_all() if r.get('legacy_source_id') == legacy_id), None)
    if existing and existing['application_type'] != application_type: raise ValueError('이미 다른 유형으로 재처리된 기록입니다.')
    if existing:
        result = existing
    else:
        result = create_submission(application_type, person[0], person[1], UploadFile(filename=old['filename'], file=BytesIO(pdf.read_bytes())))
        def provenance(item):
            item.update(legacy_source_id=legacy_id, legacy_original_status=old.get('status'), legacy_created_at=old.get('created_at'))
        result = submissions.update(result['id'], provenance)
    if result['verification'] is None and result['status'] == 'pending':
        facts = {'applicant_name': {'value': person[1], 'source': f'person:{person[0]}'},
                 'applicant_service_number': {'value': person[0], 'source': f'person:{person[0]}'}}
        verify_submission(result['id'], StoredVerification(context=facts))
    with sqlite3.connect(project_db) as db:
        link = db.execute('SELECT id FROM postponement WHERE classifier_submission_id=?', (result['id'],)).fetchone()
        if link is None:
            db.execute('INSERT INTO postponement (person_id,type,reason,status,category,source_file,classifier_submission_id) VALUES (?,?,?,?,?,?,?)',
                       (person[0], 'delay' if application_type.startswith('postponement.') else 'hold',
                        result['reason_category'], 'pending', application_type, result['filename'], result['id']))
    return submissions.get(result['id'])


def main():
    parser = argparse.ArgumentParser(description='과거 PDF를 새 추출·검증 단계로 재처리합니다. 기존 기록은 변경하지 않습니다.')
    parser.add_argument('--submission-id', required=True)
    parser.add_argument('--application-type', required=True)
    parser.add_argument('--legacy-dir', type=Path, default=Path(__file__).parents[1]/'classifier_agent_old/ML')
    parser.add_argument('--project-db', type=Path, default=Path(__file__).parents[1]/'project_ai_tf.db')
    args = parser.parse_args()
    result = reprocess(args.submission_id, args.application_type, args.legacy_dir, args.project_db)
    print(json.dumps({'id': result['id'], 'status': result['status'], 'extraction_status': result['extraction']['status'],
                      'verification': result['verification']['result'] if result['verification'] else None}, ensure_ascii=False))


if __name__ == '__main__': main()
