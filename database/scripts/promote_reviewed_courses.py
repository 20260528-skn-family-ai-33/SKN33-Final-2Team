"""검토 명단의 강좌 난이도와 BGE 색인을 함께 적용하거나 원래 값으로 복원한다."""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.deployment import digest
from src.database.vectors import resource_vectors as vectors

UPPER = 'UPPER_INTERMEDIATE'
MIGRATION = ROOT / 'src/database/migrations/027_upper_intermediate_courses.sql'


def install_schema(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('upper-course-level-147'))")
        registered = conn.execute(
            'SELECT sha256 FROM growpath_meta.schema_migrations WHERE version=%s', (MIGRATION.name,)
        ).fetchone()
        checksum = digest(MIGRATION)
        if registered:
            if registered['sha256'] != checksum:
                raise ValueError('적용된 난이도 마이그레이션 해시가 다릅니다.')
            return
        conn.execute("SET LOCAL lock_timeout TO '5s'")
        conn.execute(MIGRATION.read_text(encoding='utf-8'))
        conn.execute('INSERT INTO growpath_meta.schema_migrations(version, sha256) VALUES (%s,%s)',
                     (MIGRATION.name, checksum))


def update_levels(conn, *, apply=False, restore=False):
    original = json.loads((ROOT / 'config/reviewed_course_difficulties_147.json').read_text(encoding='utf-8'))
    if len(original) != 85 or set(original.values()) != {None, 'INTERMEDIATE'}:
        raise ValueError('검토 명단 또는 원본 난이도가 올바르지 않습니다.')
    ids = list(original)
    if apply:
        install_schema(conn)
    with conn.transaction():
        if apply:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('upper-course-level-147'))")
        sql = 'SELECT course_id, difficulty FROM public.courses WHERE course_id=ANY(%s) ORDER BY course_id'
        rows = conn.execute(sql + (' FOR UPDATE' if apply else ''), (ids,)).fetchall()
        if len(rows) != len(ids):
            raise ValueError('DB에 없는 검토 강좌가 있습니다.')
        changes = []
        for row in rows:
            rid, current = row['course_id'], row['difficulty']
            if current not in (original[rid], UPPER):
                raise ValueError(f'검토 이후 다른 난이도로 수정된 강좌: {rid}')
            target = original[rid] if restore else UPPER
            if current != target:
                changes.append((target, rid))
        result = dict(selected=len(ids), changed=len(changes), applied=apply, restore=restore)
        if apply:
            with conn.cursor() as cursor:
                cursor.executemany('UPDATE public.courses SET difficulty=%s WHERE course_id=%s', changes)
            selection = dict(resource_types=['courses'], resource_ids=ids, max_records=len(ids))
            result['embedded'] = vectors.embed(conn, **selection)['embedded_count']
            if vectors.plan(conn, **selection)['pending_count']:
                raise ValueError('갱신 후 강좌 벡터와 난이도가 일치하지 않습니다.')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restore', action='store_true', help='검토 전 난이도로 복구')
    args = parser.parse_args()
    with psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg:', 'postgresql:'),
                         autocommit=True, row_factory=dict_row) as conn:
        if conn.info.dbname != args.database:
            raise ValueError('대상 DB 이름 불일치')
        print(json.dumps(update_levels(conn, apply=args.apply, restore=args.restore)))
