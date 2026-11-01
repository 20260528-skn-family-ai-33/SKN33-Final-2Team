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
    """팀 모델 단계는 실제 Pod 기록(backend/RunPod_Ollama_연결_절차.md · 2026-10-29): 27b false·low·medium·xhigh, 4b false·true"""

    def setUp(self):
        self.values = {'growpath-27b': [False, 'low', 'medium', 'xhigh'], 'growpath-regulation-4b': [False, True]}
        self.sent, self.shows, self.show_fails = [], 0, False

        def fake(path, payload, timeout=None):
            if path == 'api/show':
                self.shows += 1
                if self.show_fails:
                    raise llm.LlmError('Ollama 연결 실패: 시험')
                return {'thinking': {'values': self.values[payload['model']]}}
            self.sent.append(payload)
            return {'message': {'content': '{}'}, 'model': payload['model']}

        settings = dataclasses.replace(llm.S, ollama_url='http://x', ollama_model='growpath-27b', ollama_model_regulation='growpath-regulation-4b',
                                       ollama_vision='qwen3.8:27b', ollama_think='off')
        for p in (patch.object(llm, 'ollama', fake), patch.object(llm, 'S', settings), patch.dict(llm._think_cache, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def think(self, reasoning=None, role='default'):
        llm.chat('ollama', MSGS, role=role, reasoning=reasoning)
        return self.sent[-1].get('think', '(없음)')

    def test_level_the_model_takes_is_sent(self):
        self.assertEqual(self.think('xhigh'), 'xhigh')
        self.assertIs(self.think('off'), False)

    def test_level_the_model_does_not_take_falls_back_to_env_default(self):
        # 모델을 바꾼 뒤 남은 옛 선택: 화면이 '기본값 · 끔'으로 보이므로 실제 요청도 .env 기본값이어야 한다
        self.assertIs(self.think('high'), False)
        self.assertIs(self.think('on'), False)
        with patch.object(llm, 'S', dataclasses.replace(llm.S, ollama_think=None)):
            self.assertEqual(self.think('high'), '(없음)')

    def test_levels_are_asked_once_per_model(self):
        self.think('low')
        self.think('medium')
        self.assertEqual(self.shows, 1)

    def test_unknown_levels_keep_the_choice(self):
        self.show_fails = True
        self.assertEqual(self.think('high'), 'high')

    def test_regulation_model_is_always_off(self):
        with patch.object(llm, 'S', dataclasses.replace(llm.S, ollama_think='on')):
            self.assertIs(self.think('xhigh', role='regulation'), False)
            self.assertIs(self.think(None, role='regulation'), False)

    def test_vision_model_ignores_the_choice(self):
        self.assertIs(self.think('xhigh', role='vision'), False)


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
                'OPENAI_ROADMAP_TIMEOUT': '', 'OLLAMA_THINK': 'off'}
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
        for env in ({'OPENAI_REASONING_EFFORT': 'max'}, {'OLLAMA_THINK': 'false'}, {'OLLAMA_THINK': 'High Effort'}):
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
