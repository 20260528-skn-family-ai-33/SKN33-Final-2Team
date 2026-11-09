"""#147 야간 부족분만 적재한다. 기본은 SELECT 전용, --apply만 신규 강좌 2개와 그 색인을 쓴다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def package() -> dict:
    data = json.loads((ROOT / 'config/night_course_supply_147.json').read_text(encoding='utf-8'))
    if (data['record_source'] != 'INTERNAL_TRAINING_PILOT' or data['platform'] != '사내교육'
            or data['image_url'] != '/images/resource-course.svg'):
        raise ValueError('승인된 사내교육 출처·플랫폼·일반 표지를 유지해야 합니다.')
    ids = [row['id'] for row in data['courses']]
    if len(ids) != len(set(ids)) or set(ids) != {'INTERNAL_NIGHT_147_DROPOUT', 'INTERNAL_NIGHT_147_IDS_TLS'}:
        raise ValueError('승인한 두 신규 과정 이외의 ID는 적재하지 않습니다.')
    for row in data['courses']:
        if row['difficulty'] != 'INTERMEDIATE' or not row['distinct_from'] or not row['outcome']:
            raise ValueError('과정의 수준·차별화 근거·산출물이 필요합니다.')
        if any(type(unit['minutes']) is not int or unit['minutes'] <= 0 or not unit['description']
               for unit in row['units']):
            raise ValueError('각 차시의 학습시간과 실습 내용이 필요합니다.')
    return data


def protected_fingerprints(conn, ids: list[str]) -> dict:
    """기존 자료·615개 변경·그 벡터가 이번 두 ID 이외에서 바뀌지 않았는지 대조한다."""
    guards = {
        'public.courses': 'course_id<>ALL(%s)',
        'public.course_skills': 'course_id<>ALL(%s)',
        'app_ext.resource_meta': 'resource_key<>ALL(%s)',
        'public.learning_resource_embeddings': "NOT(resource_type='courses' AND resource_id=ANY(%s))",
        'growpath_bge_meta.inputs': "NOT(kind='courses' AND source_id=ANY(%s))",
    }
    return {table: conn.execute(f'''SELECT count(*) AS n,
        md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS sha
        FROM (SELECT md5(to_jsonb(r)::text) h FROM {table} r WHERE {condition}) q''', (ids,)).fetchone()
        for table, condition in guards.items()}


def install(conn, *, apply: bool) -> dict:
    data = package()
    ids = [row['id'] for row in data['courses']]
    with conn.transaction():
        if not apply:
            conn.execute('SET TRANSACTION READ ONLY')
        if apply and not conn.execute("SELECT pg_try_advisory_xact_lock(hashtext('course-supply-147')) AS ok").fetchone()['ok']:
            raise ValueError('다른 강좌 공급 트랜잭션이 진행 중입니다.')
        tags = {}
        already = []
        for row in data['courses']:
            tag = conn.execute('SELECT skill_id FROM public.skill_tags WHERE name=%s', (row['skill'],)).fetchone()
            if not tag:
                raise ValueError('등록되지 않은 스킬: ' + row['skill'])
            tags[row['id']] = tag['skill_id']
            existing = conn.execute('SELECT title,record_source,platform FROM public.courses WHERE course_id=%s', (row['id'],)).fetchone()
            if existing and existing != dict(title=row['title'], record_source=data['record_source'], platform=data['platform']):
                raise ValueError('이미 존재하는 다른 과정과 ID가 충돌합니다: ' + row['id'])
            if existing:
                already.append(row['id'])
        if not apply:
            return dict(applied=False, database=conn.info.dbname, ids=ids, existing_ids=already,
                        new_courses=len(ids)-len(already), database_writes=0, external_model_calls=0)
        before = protected_fingerprints(conn, ids)
        for row in data['courses']:
            rid = row['id']
            minutes = sum(unit['minutes'] for unit in row['units'])
            units = [dict(section=f"{unit['minutes']}분", title=unit['title'], description=unit['description']) for unit in row['units']]
            summary = row['outcome'] + '\n' + '\n'.join(unit['description'] for unit in units)
            outline = Jsonb(dict(source='internal_training_pilot_v1', coverage='full_outline',
                                 outcome=row['outcome'], description=summary, item_count=len(units), items=units))
            url = f'/resources/{rid}?view=curriculum'
            conn.execute('''INSERT INTO public.courses(course_id,title,platform,org_name,cost,url,image_url,
                syllabus_summary,difficulty,record_source,content_status,duration_seconds,duration_kind,
                duration_provenance,curriculum,enrollment_period_type,recruitment_status)
                VALUES(%s,%s,%s,%s,0,%s,%s,%s,%s,%s,'ready',%s,'learning',%s,%s,'unrestricted','OPEN')
                ON CONFLICT(course_id) DO NOTHING''',
                (rid,row['title'],data['platform'],data['platform'],url,data['image_url'],summary,row['difficulty'],
                 data['record_source'],minutes*60,Jsonb(dict(source='internal_lesson_plan',
                     lesson_minutes=[unit['minutes'] for unit in row['units']], package_version=data['version'])),outline))
            same = conn.execute('''SELECT 1 FROM public.courses WHERE course_id=%s AND title=%s
                AND record_source=%s AND platform=%s AND cost=0 AND image_url=%s AND url=%s
                AND difficulty=%s AND duration_seconds=%s AND duration_kind='learning' AND curriculum=%s''',
                (rid,row['title'],data['record_source'],data['platform'],data['image_url'],url,row['difficulty'],minutes*60,outline)).fetchone()
            if not same:
                raise ValueError('기존 과정이 승인한 패키지와 다릅니다: ' + rid)
            conn.execute('INSERT INTO public.course_skills(course_id,skill_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',
                         (rid,tags[rid]))
            conn.execute('''INSERT INTO app_ext.resource_meta(resource_key,course_id,resource_type,format,hours,
                hours_origin,cost_won,audience,content,note,is_real,source_label,stage)
                VALUES(%s,%s,'course','실습',%s,'catalog',0,%s,%s,%s,false,%s,2)
                ON CONFLICT(resource_key) DO NOTHING''',
                (rid,rid,minutes/60,row['skill']+' 실습 직원',summary,row['outcome'],data['platform']))
            if not conn.execute('''SELECT 1 FROM app_ext.resource_meta WHERE resource_key=%s AND course_id=%s
                AND resource_type='course' AND cost_won=0 AND hours=round(%s::numeric/60,6)
                AND source_label=%s AND NOT is_real''', (rid,rid,minutes,data['platform'])).fetchone():
                raise ValueError('과정 앱 메타데이터 불일치: ' + rid)
        from src.database.vectors import resource_vectors as vectors
        from src.shared.bge_embeddings import embed_texts
        selected, pending = vectors.pending_sources(vectors.sources(conn), vectors.stored(conn), ['courses'], ids, len(ids))
        if len(selected) != len(ids):
            raise ValueError('신규 과정의 수집·색인 적격성을 확인할 수 없습니다.')
        # 기존 표·권한·전체 색인을 변경하는 DDL 없이 승인된 두 ID의 벡터만 기록한다.
        embedded = embed_texts([row['text'] for _, row in pending]) if pending else []
        for ((kind,rid),row), vector in zip(pending, embedded, strict=True):
            conn.execute('''INSERT INTO public.learning_resource_embeddings(resource_type,resource_id,embedding_model,
                dimensions,input_version,input_sha256,embedding,course_id) VALUES('courses',%s,%s,1024,%s,%s,%s::vector,%s)
                ON CONFLICT(resource_type,resource_id,embedding_model) DO UPDATE SET
                dimensions=EXCLUDED.dimensions,input_version=EXCLUDED.input_version,input_sha256=EXCLUDED.input_sha256,
                embedding=EXCLUDED.embedding,updated_at=now()''',
                (rid,vectors.MODEL,vectors.INPUT_VERSION,row['hash'],json.dumps(vector),rid))
            conn.execute('''INSERT INTO growpath_bge_meta.inputs(kind,source_id,source_sha256,actual_input_sha256,
                protocol,model_revision,token_count,created_at) VALUES('courses',%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT(kind,source_id) DO UPDATE SET source_sha256=EXCLUDED.source_sha256,
                actual_input_sha256=EXCLUDED.actual_input_sha256,protocol=EXCLUDED.protocol,
                model_revision=EXCLUDED.model_revision,token_count=EXCLUDED.token_count,created_at=EXCLUDED.created_at''',
                (rid,row['hash'],hashlib.sha256(row['text'].encode('utf-8')).hexdigest(),vectors.PROTOCOL,
                 vectors.PROVENANCE['model_revision'],max(1,min(len(row['text'].split()),8192))))
        final_sources = vectors.sources(conn)
        _, remaining = vectors.pending_sources(final_sources, vectors.stored(conn), ['courses'], ids, len(ids))
        if remaining:
            raise ValueError('신규 강좌의 BGE 입력 해시·revision이 일치하지 않습니다.')
        after = protected_fingerprints(conn, ids)
        if before != after:
            raise ValueError('승인된 두 ID 이외의 자료 또는 벡터가 바뀌어 적재를 롤백합니다.')
        from scripts import apply_internal_training as training
        training.verify(conn, training.read_packages([training.NIGHT_PACKAGE]), sources=final_sources)
        return dict(applied=True, database=conn.info.dbname, ids=ids, inserted_ids=sorted(set(ids)-set(already)),
                    embedded_count=len(pending), outside_scope_unchanged=True, before=before, after=after,
                    record_source=data['record_source'],platform=data['platform'],external_model_calls=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--verify-only', action='store_true', help='야간 보강 2개의 원본·메타·벡터를 읽기 전용 대조')
    args = parser.parse_args()
    if args.verify_only and args.apply:
        parser.error('--verify-only와 --apply는 분리해서 실행하세요.')
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        if args.database != 'growpath_bge_m3_20261107':
            raise ValueError('격리 재현에는 DATABASE_URL을 명시하세요.')
        from app import db
        dsn = db.engine.url.render_as_string(hide_password=False)
    dsn = dsn.replace('postgresql+psycopg:', 'postgresql:')
    os.environ.setdefault('BGE_M3_TIMEOUT', '300')
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        if connection.info.dbname != args.database:
            raise ValueError('DB 이름 확인 실패')
        if args.verify_only:
            from scripts import apply_internal_training as training
            with connection.transaction():
                connection.execute('SET TRANSACTION READ ONLY')
                result = training.verify(connection, training.read_packages([training.NIGHT_PACKAGE]))
        else:
            result = install(connection, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False))
