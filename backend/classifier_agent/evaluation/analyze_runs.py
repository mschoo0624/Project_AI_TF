"""Add transparent value-only diagnostics without changing strict raw scores."""
import argparse
import json
from pathlib import Path

from evaluation_common import same_value


def analyze(folder):
    cases = {c['id']: c for c in json.loads((folder/'cases.json').read_text(encoding='utf-8'))}
    results = [json.loads(line) for line in (folder/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    count = correct = null_count = null_correct = false_count = false_correct = 0
    errors = []
    groups = {name: {'fields': 0, 'correct': 0} for name in ['common_identity', 'type_specific_present', 'type_specific_null']}
    for result in results:
        case = cases[result['id']]
        try:
            obj = json.loads(result['raw_response'])
        except ValueError:
            obj = {}
        if not isinstance(obj, dict):
            obj = {}
        for field, gold in case['expected'].items():
            count += 1
            predicted = obj.get(field)
            if isinstance(predicted, dict):
                present = 'value' in predicted
                predicted = predicted.get('value')
            else:
                present = field in obj
            ok = present and any(same_value(predicted, value) for value in gold['accepted_values'])
            correct += ok
            group = ('common_identity' if field in {'subject_name', 'subject_service_number', 'issued_on'}
                     else 'type_specific_null' if gold['value'] is None else 'type_specific_present')
            groups[group]['fields'] += 1
            groups[group]['correct'] += ok
            if gold['value'] is None:
                null_count += 1
                null_correct += ok
            if gold['value'] is False:
                false_count += 1
                false_correct += ok
            if not ok:
                errors.append({'case': case['id'], 'field': field, 'present': present,
                               'expected': gold['accepted_values'], 'actual': predicted,
                               'document': case['document']})
    result = {'label': 'Diagnostic only: ignoring required nesting/evidence. Not an extraction contract pass rate.',
              'fields': count, 'correct_values': correct, 'expected_null': null_count,
              'correct_null': null_correct, 'explicit_false': false_count, 'correct_false': false_correct,
              'groups': groups, 'errors': errors}
    (folder/'value_only_diagnostic.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folders', type=Path, nargs='+')
    args = parser.parse_args()
    for folder in args.folders:
        result = analyze(folder)
        print(folder.name, {k: v for k, v in result.items() if k not in {'errors', 'label'}})
