"""복원 DB·CPU 서버의 실제 검색을 검사한다. 유료 API·생성 LLM·DB 쓰기는 사용하지 않는다."""
from copy import deepcopy
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import catalog, db, knowledge, llm, regulation_embeddings as embeddings, regstore
from app.services import resource_rag
from app.agents.resource_recommendations import recommend_resources
from tools.verify_bge_database import verify

TOPICS = [
    ('SQL 기본 문법 & 조인', 'SQL JOIN으로 매출 분석 쿼리를 작성한다'),
    ('SQL 쿼리 튜닝 & 인덱스 최적화', '실행계획과 인덱스로 SQL 조회 성능을 개선한다'),
    ('Python 프로그래밍 & 비동기 I/O', 'Python asyncio로 비동기 수집기를 구현한다'),
    ('RESTful API 서버 아키텍처', 'FastAPI로 REST API 서버를 구현한다'),
    ('Docker 컨테이너 가상화', 'Docker 이미지와 컨테이너로 개발 환경을 구성한다'),
    ('CI/CD 배포 자동화 파이프라인', 'GitHub Actions로 CI/CD 파이프라인을 구현한다'),
    ('RAG & 생성형 AI 에이전트', '문서 검색을 활용한 RAG 챗봇을 구현한다'),
    ('ETL & 데이터 파이프라인', 'Python과 SQL로 ETL 파이프라인을 구현한다'),
    ('RDBMS 데이터 모델링', '관계형 데이터베이스의 테이블과 관계를 설계한다'),
    ('웹 프레임워크 (FastAPI/Django)', 'FastAPI로 웹 API를 구현한다'),
    ('리눅스 환경 및 Bash 스크립팅', 'Bash 스크립트로 리눅스 작업을 자동화한다'),
    ('자연어 처리(NLP) & LLM 기초', '자연어 처리와 LLM의 기초를 학습한다'),
]


def fingerprint():
    return {table: db.one(f"SELECT count(*) AS count,md5(string_agg(t::text,'' ORDER BY t::text)) AS digest FROM {table} t")
            for table in ('public.learning_resource_embeddings', 'regulations.rag_chunk_embeddings', 'knowledge.chunks')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = {'contract': verify(), 'before': fingerprint(), 'generation_llm_tested': False,
              'recommendation_validator_uses_fixed_response': True, 'openai_embedding_calls': 0,
              'device': 'cpu', 'cases': [], 'rag': [], 'compatibility': []}
    started = perf_counter()
    items = catalog.items()
    result['catalog_warmup_ms'] = (perf_counter() - started) * 1000
    with patch.object(llm, 'openai', side_effect=AssertionError('OpenAI 임베딩 호출 금지')):
        for topic, query, fn in (
            ('regulation', '미사용 연차를 이월할 수 있나요?', lambda q: regstore.search(q, 5, '일반직', 'ollama')),
            ('company', '한국수자원공사는 어떤 일을 하나요?', knowledge.search_company),
            ('life', '구내식당 안내는 어디서 확인하나요?', knowledge.search_life)):
            started = perf_counter()
            hits = fn(query)
            if not hits:
                raise AssertionError(f'{topic}: 실제 검색 결과 없음')
            result['rag'].append({'topic': topic, 'query': query, 'elapsed_ms': (perf_counter() - started) * 1000,
                                  'ids': [hit.get('id', hit.get('chunk_id')) for hit in hits]})
        # 실제 DB에 저장된 짧은 원문과 같은 입력을 CPU에서 추론해 GPU 생성 벡터와 대조한다.
        probes = db.all_("""SELECT c.context_path || E'\\n\\n' || c.chunk_text AS input,e.embedding::text AS vector
            FROM regulations.rag_chunk_embeddings e JOIN regulations.rag_chunks c USING(rag_chunk_id)
            ORDER BY length(c.chunk_text),c.rag_chunk_id LIMIT 2""")
        probes += db.all_('SELECT chunk_text AS input,embedding::text AS vector FROM knowledge.chunks ORDER BY length(chunk_text),chunk_id LIMIT 2')
        fresh = embeddings.embed([row['input'] for row in probes])
        for row, vector in zip(probes, fresh, strict=True):
            stored = json.loads(row['vector'])
            cosine = math.fsum(a*b for a,b in zip(stored, vector)) / (math.hypot(*stored) * math.hypot(*vector))
            if cosine < .999:
                raise AssertionError(f'공유 GPU 벡터와 CPU 벡터 불일치: {cosine}')
            result['compatibility'].append({'cosine': cosine, 'input_characters': len(row['input'])})
        for topic, goal in TOPICS:
            if topic not in catalog.skill_names():
                raise AssertionError('등록되지 않은 스킬: ' + topic)
            project = {'goal': goal, 'projectSummary': goal, 'desiredCompetencies': topic}
            selection = {'skills': [{'name': topic, 'application': goal,
                                    'targetOutcome': goal, 'completionCriteria': [goal + ' 후 테스트한다']}]}
            for course_id in ('A1', 'A2', 'A3'):
                course = {'id': course_id, 'name': {'A1': 'Free', 'A2': 'Crash', 'A3': 'Challenge'}[course_id],
                          'scope': goal, 'reason': goal}
                resource_rag.cached_vectors.cache_clear()
                original = deepcopy((project, selection, course))
                started = perf_counter()
                pools, meta = resource_rag.retrieve(project, selection, items, course)
                elapsed = (perf_counter() - started) * 1000
                if not pools[0]['courses'] or not pools[0]['books']:
                    raise AssertionError(f'{topic}/{course_id}: 강좌 또는 도서 후보가 없음')
                for kind in ('courses', 'books'):
                    for row in pools[0][kind]:
                        source = items[row['id']]
                        if not source['usable'] or topic not in source['skills']:
                            raise AssertionError('사용 가능·스킬 범위 이탈')
                        if kind == 'courses' and course_id == 'A1' and source['cost'] != 0:
                            raise AssertionError('Free 유료 강좌 포함')
                if (project, selection, course) != original:
                    raise AssertionError('검색이 입력 프로젝트/선택을 변경함')
                fixed = {'skills': [{'name': topic, 'courses': [{'id': pools[0]['courses'][0]['id']}],
                                     'books': [{'id': pools[0]['books'][0]['id']}]}]}
                recommendation = recommend_resources(project, selection, items, lambda *_: fixed,
                    course=course, retrieved_pools=pools)
                allowed = {row['id'] for key in ('courses', 'books') for row in pools[0][key]}
                for row in recommendation['skills']:
                    if any(item['id'] not in allowed for key in ('courses','books') for item in row[key]):
                        raise AssertionError('추천 후처리에서 검색 후보 범위 이탈')
                case = {'topic': topic, 'course': course_id, 'model': meta['model'], 'elapsed_ms': elapsed,
                        'courses': len(pools[0]['courses']), 'books': len(pools[0]['books']),
                        'first_course': pools[0]['courses'][0]['id'], 'first_book': pools[0]['books'][0]['id'],
                        'validator_courses': len(recommendation['skills'][0]['courses']),
                        'validator_books': len(recommendation['skills'][0]['books'])}
                result['cases'].append(case)
                print(json.dumps(case, ensure_ascii=False), flush=True)
    result['after'] = fingerprint()
    if result['before'] != result['after']:
        raise AssertionError('검색 검증 중 벡터/원문 변경됨')
    values = sorted(row['elapsed_ms'] for row in result['cases'])
    result['timing'] = {'cases': len(values), 'min_ms': values[0], 'median_ms': statistics.median(values),
                        'max_ms': values[-1], 'p95_ms': values[math.ceil(len(values)*.95)-1]}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'timing': result['timing'], 'database_unchanged': True,
                      'compatibility': result['compatibility']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
