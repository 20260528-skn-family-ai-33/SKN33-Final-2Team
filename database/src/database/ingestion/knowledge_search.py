"""Read-only Korean lexical/vector fusion; no chunk or embedding changes."""
from collections import Counter, defaultdict
from functools import lru_cache
import json
import math
import re
import unicodedata

from src.database.vectors.regulation_vectors import MODEL, DIMENSIONS, vector_values

VERSION = 'knowledge-bm25-rrf-site/v1'
POOL_SIZE = 20
RRF_K = 60


def tokens(text: str) -> list[str]:
    """Hangul 2/3-grams handle particles without a morphological dependency."""
    text = unicodedata.normalize('NFKC', text).lower()
    result = []
    for word in re.findall(r'[가-힣]+|[a-z]+[0-9]*|\d+(?:\.\d+)?', text):
        if re.fullmatch('[가-힣]+', word):
            if len(word) >= 2:
                result.append('w:' + word)
            for size in (2, 3):
                result.extend(f'g{size}:' + word[i:i+size] for i in range(len(word) - size + 1))
        else:
            result.append('w:' + word)
    return result


def inferred_site(query: str, category: str) -> str | None:
    if category != '사내 생활안내':
        return None
    headquarters = '본사' in query or '사옥' in query
    training_center = '인재개발원' in query or '교육원' in query
    if headquarters == training_center:
        return None
    return '본사' if headquarters else '인재개발원'


@lru_cache(maxsize=4)
def _index(records: tuple) -> tuple:
    """Cache is keyed by complete current content, not a mutable DB timestamp."""
    counts, frequencies = {}, Counter()
    for rid, body, section in records:
        terms = Counter(tokens(body + '\n' + section))
        counts[rid] = terms
        frequencies.update(terms.keys())
    lengths = {rid: sum(terms.values()) for rid, terms in counts.items()}
    average = sum(lengths.values()) / max(1, len(lengths)) or 1
    return counts, frequencies, lengths, average


def lexical_scores(rows: list[dict], query: str) -> dict[str, float]:
    signature = tuple((r['chunk_id'], r['chunk_text'], r['metadata'].get('section_title') or '') for r in rows)
    counts, df, lengths, average = _index(signature)
    scores = defaultdict(float)
    # Standard BM25 constants; unique query terms prevent repeated query words dominating.
    n, k1, b = len(rows), 1.2, 0.75
    for term in set(tokens(query)):
        frequency = df.get(term, 0)
        if not frequency:
            continue
        inverse = math.log(1 + (n - frequency + 0.5) / (frequency + 0.5))
        for rid, terms in counts.items():
            tf = terms.get(term, 0)
            if tf:
                norm = k1 * (1 - b + b * lengths[rid] / average)
                scores[rid] += inverse * tf * (k1 + 1) / (tf + norm)
    return dict(scores)


def rank_records(rows: list[dict], query: str, *, category: str, limit: int = 5,
                 threshold: float = 0.25, mode: str = 'hybrid_site') -> list[dict]:
    """Modes are fixed experiment controls; production uses hybrid_site only."""
    if mode not in ('vector', 'lexical', 'hybrid', 'hybrid_site'):
        raise ValueError('Unknown search mode')
    site = inferred_site(query, category) if mode == 'hybrid_site' else None
    selected = [r for r in rows if r['category'] == category
                and (site is None or site in (r['metadata'].get('site') or ''))]
    lexical = lexical_scores(selected, query) if mode != 'vector' else {}
    # Keep the existing cosine threshold contract, including for lexical candidates.
    eligible = [r for r in selected if r['similarity'] >= threshold]
    vector = sorted(eligible, key=lambda r: (-r['similarity'], r['chunk_id']))
    lexical_rank = sorted((r for r in eligible if lexical.get(r['chunk_id'], 0) > 0),
                          key=lambda r: (-lexical[r['chunk_id']], r['chunk_id']))
    if mode == 'vector':
        return vector[:limit]
    if mode == 'lexical':
        return [{**r, 'lexical_score': lexical[r['chunk_id']]} for r in lexical_rank[:limit]]
    vector_ranks = {r['chunk_id']: i for i, r in enumerate(vector[:POOL_SIZE], 1)}
    lexical_ranks = {r['chunk_id']: i for i, r in enumerate(lexical_rank[:POOL_SIZE], 1)}
    fused = []
    for row in eligible:
        rid = row['chunk_id']
        if rid not in vector_ranks and rid not in lexical_ranks:
            continue
        score = sum(1 / (RRF_K + ranks[rid]) for ranks in (vector_ranks, lexical_ranks) if rid in ranks)
        fused.append({**row, 'lexical_score': lexical.get(rid, 0.0), 'hybrid_score': score,
                      'vector_rank': vector_ranks.get(rid), 'lexical_rank': lexical_ranks.get(rid),
                      'site_filter': site, 'search_version': VERSION})
    return sorted(fused, key=lambda r: (-r['hybrid_score'], -r['similarity'], r['chunk_id']))[:limit]


def hybrid_search_vector(conn, query_vector: list[float], *, query: str, category: str,
                         limit: int = 5, threshold: float = 0.25) -> list[dict]:
    if (not isinstance(query, str) or not query.strip() or category not in ('수자원공사 정보','사내 생활안내')
            or type(limit) is not int or not 1 <= limit <= 50
            or not math.isfinite(threshold) or not -1 <= threshold <= 1):
        raise ValueError('검색 질문·범주·결과 수·유사도를 확인하세요.')
    vector = json.dumps(vector_values(query_vector), allow_nan=False)
    conn.execute('SET LOCAL search_path TO public, extensions')
    rows = conn.execute('''SELECT c.chunk_id,c.chunk_text,c.is_virtual,c.metadata,c.display_order,
        d.document_id,d.category,d.title AS document_title,1-(c.embedding <=> %s::vector) AS similarity
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        WHERE d.category=%s AND c.embedding_model=%s AND c.dimensions=%s
            AND c.input_sha256=c.chunk_text_sha256 AND c.embedding IS NOT NULL
        ORDER BY c.chunk_id''', (vector, category, MODEL, DIMENSIONS)).fetchall()
    return rank_records(rows, query, category=category, limit=limit, threshold=threshold)
