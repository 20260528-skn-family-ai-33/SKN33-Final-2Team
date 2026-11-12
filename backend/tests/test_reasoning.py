"""외부 DB·LLM 없이 추론 정도가 모델 호출에 실리는 값과 설정 기본값을 검증한다(#28 · PR #40 리뷰)."""
from __future__ import annotations

import dataclasses
import os
import socket
import unittest
import urllib.error
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import config, llm

MSGS = [{'role': 'user', 'content': 'hi'}]


class OllamaThinkTest(unittest.TestCase):
    """RunPod-Ollama 는 모든 생성을 추론 없이 부른다: 역할·직원/관리자 단계·.env 와 관계없이 think: false"""

    def setUp(self):
        self.sent, self.shows = [], 0

        def fake(path, payload, timeout=None):
            if path == 'api/show':
                self.shows += 1
                return {'thinking': {'values': [False, 'low', 'medium', 'xhigh']}}
            self.sent.append(payload)
            return {'message': {'content': '{}'}, 'model': payload['model']}

        settings = dataclasses.replace(llm.S, ollama_url='http://x', ollama_model='growpath-27b', ollama_model_regulation='growpath-regulation-4b',
                                       ollama_vision='qwen3.8:27b')
        for p in (patch.object(llm, 'ollama', fake), patch.object(llm, 'S', settings)):
            p.start()
            self.addCleanup(p.stop)

    def think(self, reasoning=None, role='default'):
        llm.chat('ollama', MSGS, role=role, reasoning=reasoning)
        return self.sent[-1].get('think', '(없음)')

    def test_every_role_and_choice_sends_think_false(self):
        # 보내지 않으면(None) qwen 계열은 모델 기본값(켬)을 쓰므로 False 가 실제로 실려야 한다
        for role in ('default', 'roadmap', 'resources', 'regulation', 'vision'):
            for reasoning in (None, 'off', 'on', 'low', 'xhigh', 'high'):
                with self.subTest(role=role, reasoning=reasoning):
                    self.assertIs(self.think(reasoning, role=role), False)
        self.assertEqual(self.shows, 0)  # 단계를 고르지 않으므로 모델 단계(/api/show)도 묻지 않는다

    def test_env_no_longer_turns_thinking_on(self):
        with patch.dict(os.environ, {'OLLAMA_THINK': 'on'}), patch.dict(config._FILE, {}, clear=True):
            settings = config.load()
        self.assertFalse(hasattr(settings, 'ollama_think'))
        with patch.object(llm, 'S', dataclasses.replace(settings, ollama_url='http://x')):
            self.assertIs(self.think(), False)

    def test_ping_does_not_ask_reasoning_levels(self):
        def fake(path, payload, timeout=None):
            self.shows += path == 'api/show'
            return {'api/version': {'version': '0.40'}, 'api/tags': {'models': [{'name': 'growpath-27b'}]},
                    'api/ps': {'models': []}}.get(path, {})

        with patch.object(llm, 'ollama', fake):
            res = llm.ping('ollama')
        self.assertEqual(self.shows, 0)
        self.assertTrue(all('think' not in m for m in res['models']))

    def test_only_chatbot_model_requests_automatic_gpu_selection(self):
        for role in ('default', 'roadmap', 'regulation', 'vision'):
            with self.subTest(role=role):
                llm.chat('ollama', MSGS, role=role)
                if role == 'regulation':
                    self.assertEqual(self.sent[-1]['options']['num_gpu'], -1)
                else:
                    self.assertNotIn('num_gpu', self.sent[-1].get('options', {}))

    def test_chatbot_gpu_selection_preserves_context_and_temperature(self):
        with patch.object(llm, 'S', dataclasses.replace(llm.S, ollama_num_ctx=16384)):
            llm.chat('ollama', MSGS, role='regulation', temperature=0)
            self.assertEqual(self.sent[-1]['options'], {'num_gpu': -1, 'num_ctx': 16384, 'temperature': 0})

    def test_roadmap_and_resources_set_num_predict_and_context(self):
        for role in ('roadmap', 'resources'):
            with self.subTest(role=role):
                llm.chat('ollama', MSGS, role=role)
                self.assertIn('num_predict', self.sent[-1]['options'])
                self.assertIn('num_ctx', self.sent[-1]['options'])

    def test_json_left_only_in_thinking_is_recovered_without_retry(self):
        calls = []

        def fake_chat(path, payload, timeout=None):
            calls.append(payload)
            return {'message': {'content': '', 'thinking': '정리하면 {"recovered": true}'}, 'model': payload['model']}

        with patch.object(llm, 'ollama', fake_chat):
            res = llm.chat('ollama', MSGS, reasoning='medium')
        self.assertEqual(res['content'], '{"recovered": true}')
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0]['think'], False)


class OpenAiReasoningTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.timeouts = []

        def fake(path, payload, timeout=90):
            self.sent.append(payload)
            self.timeouts.append(timeout)
            return {'choices': [{'message': {'content': '{}'}}], 'model': payload['model']}

        settings = dataclasses.replace(llm.S, openai_key='x', openai_model='gpt-6-luna', openai_vision='gpt-4o', openai_json=True,
                                       openai_reasoning_levels=config.OPENAI_DEFAULT_LEVELS, openai_reasoning=None,
                                       openai_roadmap_timeout=180)
        for p in (patch.object(llm, 'openai', fake), patch.object(llm, 'S', settings)):
            p.start()
            self.addCleanup(p.stop)

    def effort(self, reasoning=None, role='default'):
        llm.chat('openai', MSGS, role=role, reasoning=reasoning)
        return self.sent[-1].get('reasoning_effort', '(없음)')

    def test_level_in_the_list_is_sent(self):
        self.assertEqual(self.effort('low'), 'low')
        self.assertEqual(self.effort('xhigh', role='regulation'), 'xhigh')
        self.assertNotIn('options', self.sent[-1])
        self.assertNotIn('num_gpu', self.sent[-1])

    def test_level_not_in_the_list_falls_back(self):
        self.assertEqual(self.effort('max'), '(없음)')
        with patch.object(llm, 'S', dataclasses.replace(llm.S, openai_reasoning='medium')):
            self.assertEqual(self.effort('max'), 'medium')

    def test_other_vision_model_gets_nothing(self):
        self.assertEqual(self.effort('low', role='vision'), '(없음)')

    def test_only_roadmap_uses_configurable_timeout_and_keeps_user_effort(self):
        for role, timeout in [('roadmap', 180), ('default', 90), ('regulation', 90), ('vision', 90)]:
            with self.subTest(role=role):
                self.assertEqual(self.effort('low', role=role), '(없음)' if role == 'vision' else 'low')
                self.assertEqual(self.timeouts[-1], timeout)
        with patch.object(llm, 'S', dataclasses.replace(llm.S, openai_roadmap_timeout=90)):
            self.assertEqual(self.effort('high', role='roadmap'), 'high')
            self.assertEqual(self.timeouts[-1], 90)

    def test_roadmap_does_not_silently_lower_default_or_selected_effort(self):
        self.assertEqual(self.effort(role='roadmap'), '(없음)')
        with patch.object(llm, 'S', dataclasses.replace(llm.S, openai_reasoning='medium')):
            self.assertEqual(self.effort(role='roadmap'), 'medium')
            self.assertEqual(self.effort('high', role='roadmap'), 'high')


class OpenAiTimeoutTest(unittest.TestCase):
    def test_timeout_is_reported_without_retry_for_each_role(self):
        settings = dataclasses.replace(llm.S, openai_key='test-key', openai_roadmap_timeout=180)
        for role, timeout in [('roadmap', 180), ('default', 90)]:
            for error in (socket.timeout(), urllib.error.URLError(socket.timeout())):
                with self.subTest(role=role, error=type(error).__name__), patch.object(llm, 'S', settings), \
                        patch.object(llm, '_http', side_effect=error) as http:
                    with self.assertRaisesRegex(llm.LlmError, f'시간 초과: {timeout}초'):
                        llm.chat('openai', MSGS, role=role)
                    http.assert_called_once()
                    self.assertEqual(http.call_args.args[-1], timeout)


class SettingsTest(unittest.TestCase):
    def load(self, **env):
        base = {'OPENAI_MODEL': '', 'OPENAI_REASONING_LEVELS': '', 'OPENAI_REASONING_EFFORT': '',
                'OPENAI_ROADMAP_TIMEOUT': ''}
        with patch.dict(os.environ, dict(base, **env)), patch.dict(config._FILE, {}, clear=True):
            return config.load()

    def test_default_openai_model_uses_checked_levels(self):
        s = self.load()
        self.assertEqual((s.openai_model, s.openai_reasoning_levels, s.openai_model_reasoning),
                         ('gpt-6-luna', ('none', 'low', 'medium', 'high', 'xhigh'), 'medium'))

    def test_other_openai_model_needs_levels_in_env(self):
        s = self.load(OPENAI_MODEL='gpt-4o')
        self.assertEqual((s.openai_reasoning_levels, s.openai_model_reasoning), ((), None))
        self.assertEqual(self.load(OPENAI_MODEL='gpt-4o', OPENAI_REASONING_LEVELS='low,high').openai_reasoning_levels, ('low', 'high'))

    def test_bad_values_stop_startup(self):
        for env in ({'OPENAI_REASONING_EFFORT': 'max'}, {'OPENAI_REASONING_EFFORT': 'false'}, {'OPENAI_REASONING_EFFORT': 'High Effort'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                self.load(**env)

    def test_roadmap_timeout_default_override_and_boundaries(self):
        self.assertEqual(self.load().openai_roadmap_timeout, 180)
        for value in ('1', '90', '180', '600'):
            with self.subTest(value=value):
                self.assertEqual(self.load(OPENAI_ROADMAP_TIMEOUT=value).openai_roadmap_timeout, int(value))
        for value in ('0', '-1', '601', '1.5', 'invalid'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'OPENAI_ROADMAP_TIMEOUT'):
                self.load(OPENAI_ROADMAP_TIMEOUT=value)


if __name__ == '__main__':
    unittest.main()
