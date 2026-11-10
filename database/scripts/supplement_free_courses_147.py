"""기존 PostgreSQL 단원에 스킬을 연결하고 무료 Django REST 실습을 적재한다."""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.vectors import resource_vectors as vectors
from scripts import apply_internal_training as training


def link(conn, course_id, skill):
    tag = conn.execute('SELECT skill_id FROM public.skill_tags WHERE name=%s', (skill,)).fetchone()
    if not tag:
        raise ValueError(f'등록되지 않은 스킬: {skill}')
    conn.execute('INSERT INTO public.course_skills(course_id, skill_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                 (course_id, tag['skill_id']))


def install(conn, *, apply):
    package = json.loads((ROOT / 'config/free_course_supply_147.json').read_text(encoding='utf-8'))
    with conn.transaction(force_rollback=not apply):
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('course-supply-147'))")
        conn.execute('SET LOCAL search_path TO public,extensions')
        ids = []
        for item in package['reviewed_links']:
            rid = item['course']
            original = conn.execute("""SELECT c.curriculum,c.syllabus_summary,m.content
                FROM public.courses c JOIN app_ext.resource_meta m ON m.course_id=c.course_id
                WHERE c.course_id=%s AND c.title=%s AND m.cost_won=0 FOR UPDATE OF c,m""",
                (rid,item['title'])).fetchone()
            if (not original or not any(u.get('title') == item['unit'] for u in original['curriculum']['items'])
                    or item['objective'] not in (original['content'] or '') + (original['syllabus_summary'] or '')):
                raise ValueError(f'외부 강좌의 가격 또는 학습 근거가 변경됨: {rid}')
            link(conn, rid, item['skill'])
            ids.append(rid)
        # 6개 교육의 유일한 원본과 필드 변환·적재·검증을 통합 적재기와 공유한다.
        courses = training.read_packages([ROOT / 'config/free_course_supply_147.json'])
        internal = training.install(conn, courses, apply=apply)
        external_ids = list(ids)
        ids.extend(course['id'] for course in courses)
        if len(ids) != len(set(ids)):
            raise ValueError('패키지에 중복 강좌 ID가 있습니다.')
        external_vectors = 0
        if external_ids:
            kwargs = dict(resource_types=['courses'], resource_ids=external_ids, max_records=len(external_ids))
            job = vectors.embed(conn, **kwargs) if apply else vectors.plan(conn, **kwargs)
            external_vectors = job.get('embedded_count', job.get('pending_count'))
            if apply and vectors.plan(conn, **kwargs)['pending_count']:
                raise ValueError('외부 강좌 입력과 BGE 벡터가 일치하지 않습니다.')
        return dict(applied=apply, ids=ids,
                    vectors=internal['pending_vectors'] + external_vectors)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--database', required=True, help='연결할 DB 이름(연결 문자열은 DATABASE_URL)')
    args = parser.parse_args()
    with psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg:', 'postgresql:'),
                         row_factory=dict_row,autocommit=True) as conn:
        if conn.info.dbname != args.database:
            raise ValueError('대상 DB 이름 불일치')
        print(json.dumps(install(conn,apply=args.apply),ensure_ascii=False))
