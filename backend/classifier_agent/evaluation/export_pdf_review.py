"""Make inspectable per-PDF results without repairing model output."""
import argparse
import json
from pathlib import Path

from evaluation_common import same_value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    cases = {c['id']: c for c in json.loads((args.run/'cases.json').read_text(encoding='utf-8'))}
    fields = json.loads((args.run/'common_fields.json').read_text(encoding='utf-8'))['fields']
    results = []
    for line in (args.run/'results.jsonl').read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        c = cases[r['id']]
        try:
            obj = json.loads(r['raw_response'])
        except ValueError:
            obj = None
        comparisons = []
        for key, gold in c['expected'].items():
            present = isinstance(obj, dict) and key in obj
            raw_field = obj[key] if present else None
            value = raw_field.get('value') if isinstance(raw_field, dict) else raw_field
            value_present = present and (not isinstance(raw_field, dict) or 'value' in raw_field)
            comparisons.append({'key': key, 'label': fields[key]['label'], 'expected': gold['value'],
                                'accepted_values': gold['accepted_values'], 'value_present': value_present,
                                'model_value': value, 'raw_model_field': raw_field,
                                'value_correct': value_present and any(same_value(value, v) for v in gold['accepted_values']),
                                'strict_score': r['score']['fields'][key]})
        results.append({'filename': c['filename'], 'pdf_sha256': c['pdf_sha256'],
                        'application_type_assumption': c['application_type'],
                        'input_text': c['document'], 'seconds': r['seconds'],
                        'raw_response': r['raw_response'], 'parsed_response': obj,
                        'comparisons': comparisons})
    out = args.run/'pdf_results.review.json'
    with out.open('x', encoding='utf-8') as stream:
        json.dump({'scope': 'Raw model output and fixed-gold comparisons; no automatic correction or eligibility decision.',
                   'files': results}, stream, ensure_ascii=False, indent=2)
    print(out)


if __name__ == '__main__':
    main()
