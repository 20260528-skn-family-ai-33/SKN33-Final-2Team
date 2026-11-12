import unittest
from app.agents.runtime import parse_json
from app.llm import LlmError


class ParseJsonTest(unittest.TestCase):
    def test_normal_json(self):
        self.assertEqual(parse_json('{"key": "value"}'), {"key": "value"})

    def test_unwraps_answer_dict_envelope(self):
        raw = '{"answer": {"skills": [{"name": "A"}]}, "type": "agent"}'
        self.assertEqual(parse_json(raw), {"skills": [{"name": "A"}]})

    def test_unwraps_answer_string_envelope(self):
        raw = '{"answer": "{\\"skills\\": [{\\"name\\": \\"A\\"}]}", "type": "agent_json"}'
        self.assertEqual(parse_json(raw), {"skills": [{"name": "A"}]})

    def test_unwraps_data_and_result_envelopes(self):
        self.assertEqual(parse_json('{"data": {"a": 1}}'), {"a": 1})
        self.assertEqual(parse_json('{"result": {"b": 2}}'), {"b": 2})

    def test_invalid_json_raises_llm_error(self):
        with self.assertRaises(LlmError):
            parse_json('not json at all')
