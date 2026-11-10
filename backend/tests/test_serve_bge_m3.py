"""임베딩 서버가 색인 도구에 실제 추론 정밀도·토큰 수를 알려 주는지 모델 없이 확인한다."""
import importlib.util
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import bge_model


@unittest.skipUnless(importlib.util.find_spec('torch'), 'torch가 설치된 임베딩 서버 환경에서만 실행한다')
class ServeBgeM3ResponseTest(unittest.TestCase):
    def respond(self, precision):
        import torch
        from tools import serve_bge_m3 as server

        def tokenizer(texts, **options):
            self.assertEqual(options, {'padding': True, 'truncation': False, 'return_tensors': 'pt'})
            return {'input_ids': torch.tensor([[101, 7, 102, 0], [101, 7, 8, 102]]),
                    'attention_mask': torch.tensor([[1, 1, 1, 0], [1, 1, 1, 1]])}

        def model(**tokens):
            hidden = torch.zeros(2, tokens['input_ids'].shape[1], bge_model.DIMENSIONS)
            hidden[:, 0, 0] = 2.0
            return SimpleNamespace(last_hidden_state=hidden)

        state = {'tokenizer': tokenizer, 'model': model, 'precision': precision}
        with patch.dict(server.state, state, clear=True):
            return server.embeddings(server.EmbeddingRequest(model=bge_model.MODEL, input=['첫째', '둘째문장']))

    def test_reports_configured_precision_and_padding_free_token_counts(self):
        for precision in ('float32', 'float16'):
            with self.subTest(precision=precision):
                result = self.respond(precision)
                self.assertEqual(result['precision'], precision)
                self.assertIn(precision, bge_model.INDEX_PROTOCOLS)
                self.assertEqual([row['token_count'] for row in result['data']], [3, 4])
                self.assertTrue(all(type(row['token_count']) is int for row in result['data']))
                self.assertAlmostEqual(result['data'][0]['embedding'][0], 1.0)


if __name__ == '__main__':
    unittest.main()
