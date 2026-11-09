"""#124 공유 BGE DB의 개수·차원·입력 해시·revision을 읽기 전용으로 검사한다."""
import json
import argparse
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db
from app.bge_model import MODEL, REVISION, PROVENANCE
from app.config import env


def verify(*, check_counts: bool = True) -> dict:
    result = {}
    for table, expected in (('public.learning_resource_embeddings', 2984),
                            ('regulations.rag_chunk_embeddings', 1406), ('knowledge.chunks', 442)):
        row = db.one(f'''SELECT count(*) AS total,count(*) FILTER(WHERE embedding_model=:model
            AND dimensions=1024 AND vector_dims(embedding)=1024
            AND abs(vector_norm(embedding)-1)<0.001) AS valid FROM {table}''', model=MODEL)
        if row['valid'] != row['total']:
            raise ValueError(f'BGE DB 모델·차원·정규화 오류: {table} {row}')
        if check_counts and (row['total'] != expected or row['valid'] != expected):
            raise ValueError(f'BGE DB 시드 데이터 개수 불일치: {table} {row} (기대치: {expected})')
        result[table] = row
    bad_regulations = db.val('''SELECT count(*) FROM regulations.rag_chunk_embeddings e
        JOIN regulations.rag_chunks c USING(rag_chunk_id)
        LEFT JOIN growpath_bge_meta.inputs p ON p.kind='regulations' AND p.source_id=e.rag_chunk_id
        WHERE e.input_version<>'context_path+blank_line+chunk_text/v1'
          OR e.input_sha256<>encode(sha256(convert_to(c.context_path || E'\\n\\n' || c.chunk_text,'UTF8')),'hex')
          OR p.source_sha256 IS DISTINCT FROM e.input_sha256
          OR p.actual_input_sha256 IS DISTINCT FROM e.input_sha256''')
    bad_knowledge = db.val('''SELECT count(*) FROM knowledge.chunks c
        LEFT JOIN growpath_bge_meta.inputs p ON p.kind='knowledge' AND p.source_id=c.chunk_id
        WHERE c.input_sha256<>c.chunk_text_sha256
          OR c.chunk_text_sha256<>encode(sha256(convert_to(c.chunk_text,'UTF8')),'hex')
          OR p.source_sha256 IS DISTINCT FROM c.input_sha256
          OR p.actual_input_sha256 IS DISTINCT FROM c.input_sha256''')
    bad_resources = db.val('''SELECT count(*) FROM public.learning_resource_embeddings e
        LEFT JOIN growpath_bge_meta.inputs p ON p.kind=e.resource_type AND p.source_id=e.resource_id
        WHERE e.input_version<>'db-resource-fields-and-skill-links/v1'
          OR p.source_sha256 IS DISTINCT FROM e.input_sha256''')
    provenance = db.one('''SELECT count(*) AS total,count(*) FILTER(WHERE model_revision=:revision
        AND protocol='bge-m3/cls-l2-fp16/v1' AND token_count BETWEEN 1 AND 8192) AS valid
        FROM growpath_bge_meta.inputs''', revision=REVISION)
    if bad_regulations or bad_knowledge or bad_resources or provenance['total'] != provenance['valid']:
        raise ValueError(f'BGE DB 입력 계약 오류: bad_reg={bad_regulations}, bad_know={bad_knowledge}, bad_res={bad_resources}, prov={provenance}')
    if check_counts and provenance != {'total': 4832, 'valid': 4832}:
        raise ValueError(f'BGE DB 시드 메타 개수 불일치: {provenance} (기대치: 4832)')
    return {'database': db.engine.url.database, 'model': MODEL, 'revision': REVISION,
            'vectors': provenance['total'], 'tables': result, 'provenance': provenance, 'database_writes': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', action='store_true', help='실제 임베딩 서버의 모델 계약·CPU 정밀도도 확인')
    parser.add_argument('--skip-count-check', action='store_true', help='시드 개수(4832) 고정 검사를 건너뛰고 모델·해시 계약만 검증')
    args = parser.parse_args()
    result = verify(check_counts=not args.skip_count_check)
    if args.server:
        base = env('BGE_M3_BASE_URL', 'http://bge-m3:8080/v1').rstrip('/').removesuffix('/v1')
        with urllib.request.urlopen(base + '/health', timeout=10) as response:
            server = json.load(response)
        if server.get('model') != MODEL or any(server.get(key) != value for key, value in PROVENANCE.items()):
            raise ValueError('임베딩 서버와 공유 DB의 모델 계약이 다릅니다.')
        result['server'] = server
    print(json.dumps(result, ensure_ascii=False, indent=2))
