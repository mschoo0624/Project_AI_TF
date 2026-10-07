"""Checks that evaluation cannot reward missing fields or invented evidence."""
import json
import unittest

from evaluation_common import score, build_messages


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.case = {'application_type': 'test', 'document': '입원하지 않음',
                     'expected': {'inpatient_status': {'value': False, 'accepted_values': [False],
                                                      'evidence_must_include': ['입원하지 않음']}}}

    def result(self, value, evidence):
        return json.dumps({'inpatient_status': {'value': value, 'evidence': evidence}})

    def test_false_is_not_zero_or_string(self):
        self.assertTrue(score(self.case, self.result(False, ['입원하지 않음']))['case_pass'])
        for value in [0, 'false', None]:
            self.assertFalse(score(self.case, self.result(value, ['입원하지 않음']))['case_pass'])

    def test_evidence_must_be_real_and_relevant(self):
        for quotes in [[], ['입원'], ['입원하지 않았습니다']]:
            self.assertFalse(score(self.case, self.result(False, quotes))['case_pass'])

    def test_missing_null_field_is_not_correct(self):
        self.case['expected']['inpatient_status'] = {'value': None, 'accepted_values': [None], 'evidence_must_include': []}
        self.assertFalse(score(self.case, '{}')['case_pass'])
        self.assertTrue(score(self.case, self.result(None, []))['case_pass'])

    def test_no_gold_leakage(self):
        self.case['expected']['inpatient_status']['accepted_values'] = ['SECRET_GOLD']
        prompt = build_messages(self.case, {'inpatient_status': {'type': 'boolean'}})
        self.assertNotIn('SECRET_GOLD', json.dumps(prompt))

    def test_invalid_json_and_extra_keys(self):
        self.assertFalse(score(self.case, '```json\n{}\n```')['json_valid'])
        self.assertFalse(score(self.case, '{"extra": 1}')['case_pass'])


if __name__ == '__main__':
    unittest.main()
