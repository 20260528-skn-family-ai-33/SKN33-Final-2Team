"""미기재 강좌의 난이도·추정 근거를 저장하고 대상 BGE 벡터를 갱신한다."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'backend')]
from app.course_levels import classify
from src.database.deployment import digest
from src.database.vectors import resource_vectors as vectors

MIGRATION = ROOT / 'src/database/migrations/028_course_difficulty_provenance.sql'
REVIEWED = ROOT / 'config/reviewed_course_difficulties_147.json'


def install_schema(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('course-difficulty-147'))")
        checksum = digest(MIGRATION)
        existing = conn.execute('SELECT sha256 FROM growpath_meta.schema_migrations WHERE version=%s',
                                (MIGRATION.name,)).fetchone()
        if existing:
            if existing['sha256'] != checksum:
                raise ValueError('기존 마이그레이션과 028의 해시가 다릅니다.')
            return
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute(MIGRATION.read_text(encoding='utf8'))
        conn.execute('INSERT INTO growpath_meta.schema_migrations(version, sha256) VALUES (%s,%s)',
                     (MIGRATION.name, checksum))


def backfill(conn, *, apply=False, client=None):
    if apply:
        install_schema(conn)
    with conn.transaction():
        if apply:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('course-difficulty-147'))")
        query = 'SELECT course_id,title,curriculum FROM public.courses WHERE difficulty IS NULL ORDER BY course_id'
        rows = conn.execute(query + (' FOR UPDATE' if apply else '')).fetchall()
        updates = [(*classify(None, r['title'], r['curriculum']), r['course_id']) for r in rows]
        result = dict(applied=apply, courses=len(rows), levels=dict(Counter(r[0] for r in updates)),
                      reasons=dict(Counter(r[1] for r in updates)), embedded=0)
        if not apply:
            return result
        reviewed = list(json.loads(REVIEWED.read_text(encoding='utf8')))
        conn.execute("""UPDATE public.courses SET difficulty_basis='목차 검토로 중상 확정'
                        WHERE course_id=ANY(%s) AND difficulty='UPPER_INTERMEDIATE'
                          AND NOT difficulty_estimated AND difficulty_basis IS NULL""", (reviewed,))
        if updates:
            with conn.cursor() as cursor:
                cursor.executemany("""UPDATE public.courses SET difficulty=%s, difficulty_basis=%s,
                                      difficulty_estimated=true WHERE course_id=%s AND difficulty IS NULL""", updates)
        estimated = [r['course_id'] for r in conn.execute(
            'SELECT course_id FROM public.courses WHERE difficulty_estimated ORDER BY course_id')]
        records = vectors.sources(conn, retained_course_ids=estimated)
        ids = [rid for rid in estimated if ('courses', rid) in records]
        if ids:
            selection = dict(resource_types=['courses'], resource_ids=ids, max_records=len(ids))
            result['embedded'] = vectors.embed(conn, client=client, include_stored_courses=True, **selection)['embedded_count']
            current = vectors.sources(conn, retained_course_ids=ids)
            _, pending = vectors.pending_sources(current, vectors.stored(conn), **selection)
            if pending:
                raise ValueError('강좌 난이도와 갱신된 BGE 입력이 일치하지 않습니다.')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg:', 'postgresql:'),
                         autocommit=True, row_factory=dict_row) as conn:
        if conn.info.dbname != args.database:
            raise ValueError('대상 DB 이름 불일치')
        print(json.dumps(backfill(conn, apply=args.apply), ensure_ascii=False))
