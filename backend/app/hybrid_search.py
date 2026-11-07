"""BM25 원문 검색과 pgvector 순위를 RRF로 합친다. 벡터·원문 DB에는 쓰지 않는다."""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import math
import re
import unicodedata

from .config import env
from .llm import LlmError

K1 = 1.2
B = 0.75
RRF_CONSTANT = 60
CANDIDATES = 50


def enabled() -> bool:
    mode = env('ASSISTANT_SEARCH_MODE', 'hybrid').strip().lower()
    if mode not in ('hybrid', 'vector'):
        raise LlmError('BGE-M3 설정: ASSISTANT_SEARCH_MODE는 hybrid 또는 vector여야 해요')
    return mode == 'hybrid'


def tokenize(text: str) -> list[str]:
    """단어·영문/숫자 식별자 + 한글 2음절 조각. 형태소 분석기 없이 조사 차이를 보완한다."""
    text = unicodedata.normalize('NFKC', text).casefold()
    # 같은 조 번호의 띄어쓰기 차이를 통일하고 조 번호 자체는 하나의 토큰으로 유지한다.
    text = re.sub(r'제\s*(\d+)\s*조(?:\s*의\s*(\d+))?',
                  lambda match: f'제{match[1]}조' + (f'의{match[2]}' if match[2] else ''), text)
    tokens = ['word:' + word for word in re.findall(r'[가-힣a-z0-9]+(?:[._-][a-z0-9]+)*', text)]
    tokens.extend('law:' + reference for reference in re.findall(r'제\d+(?:조(?:의\d+)?|항|호)', text))
    for word in re.findall(r'[가-힣]{2,}', text):
        tokens.extend('gram:' + word[index:index + 2] for index in range(len(word) - 1))
    return tokens


class BM25Index:
    def __init__(self, documents: tuple[tuple[str, str], ...]):
        self.postings: dict[str, list[tuple[str, int]]] = defaultdict(list)
        self.lengths = {}
        for identifier, text in documents:
            terms = Counter(tokenize(text))
            self.lengths[identifier] = sum(terms.values())
            for term, frequency in terms.items():
                self.postings[term].append((identifier, frequency))
        self.count = len(documents)
        self.average_length = sum(self.lengths.values()) / max(1, self.count)

    def search(self, question: str, limit: int) -> list[dict]:
        scores: dict[str, float] = defaultdict(float)
        for term in sorted(set(tokenize(question))):
            matches = self.postings.get(term, ())
            idf = math.log1p((self.count - len(matches) + 0.5) / (len(matches) + 0.5))
            for identifier, frequency in matches:
                length = self.lengths[identifier] / (self.average_length or 1)
                scores[identifier] += idf * frequency * (K1 + 1) / (frequency + K1 * (1 - B + B * length))
        return [{'id': identifier, 'score': score} for identifier, score in
                sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit] if score > 0]


@lru_cache(maxsize=8)
def _index(documents: tuple[tuple[str, str], ...]) -> BM25Index:
    """검색을 허용한 원문 스냅샷만 캐시한다. 본문·ID·검색 범위가 바뀌면 새 색인을 만든다."""
    return BM25Index(documents)


def bm25(question: str, documents: list[tuple[str, str]], limit: int = CANDIDATES) -> list[dict]:
    if limit < 1:
        raise ValueError('검색 개수는 1 이상이어야 해요')
    if len({identifier for identifier, _ in documents}) != len(documents):
        raise ValueError('BM25 원문 ID가 중복됐어요')
    return _index(tuple(sorted(documents))).search(question, limit)


def fuse(vector_hits: list[dict], keyword_hits: list[dict], limit: int) -> list[dict]:
    """점수 단위를 섞지 않고 1부터 시작하는 순위마다 1/(60+rank)를 합산한다."""
    if limit < 1:
        raise ValueError('검색 개수는 1 이상이어야 해요')
    combined = {}
    for name, hits in (('vector', vector_hits), ('bm25', keyword_hits)):
        unique = {hit['id']: hit for hit in reversed(hits)}
        for rank, identifier in enumerate(dict.fromkeys(hit['id'] for hit in hits), 1):
            result = combined.setdefault(identifier, {'id': identifier, 'rrfScore': 0.0,
                'vectorRank': None, 'bm25Rank': None, 'vectorScore': None, 'bm25Score': None})
            result['rrfScore'] += 1 / (RRF_CONSTANT + rank)
            result[name + 'Rank'] = rank
            result[name + 'Score'] = unique[identifier]['score']
    return sorted(combined.values(), key=lambda hit: (-hit['rrfScore'],
        min(rank for rank in (hit['vectorRank'], hit['bm25Rank']) if rank is not None), hit['id']))[:limit]
