"""사내교육 패키지만 원자적으로 재적재한다. 기존 강좌의 난이도·스킬별 정책은 변경하지 않는다."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.vectors import resource_vectors as vectors
from src.shared.bge_embeddings import PROVENANCE, embed_texts, vector_values

SOURCE = 'INTERNAL_TRAINING_PILOT'
PACKAGE_INDEX = ROOT / 'config/internal_training_packages.json'


def default_packages() -> tuple[Path, ...]:
    index = json.loads(PACKAGE_INDEX.read_text(encoding='utf-8'))
    names = index.get('packages')
    if (index.get('schema_version') != 'internal-training-index/v1' or not isinstance(names, list)
            or not names or len(names) != len(set(names))
            or any(not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_]+\.json', name) for name in names)):
        raise ValueError('교육 패키지 기본 목록 오류')
    return tuple(PACKAGE_INDEX.parent / name for name in names)


DEFAULT_PACKAGES = default_packages()
NIGHT_PACKAGE = ROOT / 'config/night_course_supply_147.json'


def _free_courses(package: dict) -> dict:
    """기존 무료 보충 명령과 같은 원본을 읽는다. 교육 밖 reviewed_links는 이 적재기에서 실행하지 않는다."""
    if set(package) != {'reviewed_links', 'skill', 'courses'}:
        raise ValueError('무료 교육 원본 형식 오류')
    courses = []
    for original in package['courses']:
        course = dict(original)
        defaults = dict(track='crash', fee_won=0, url=f"/resources/{course['id']}?view=curriculum",
                        image_url='/images/resource-course.svg', skills=[package['skill']],
                        audience='Django로 웹 API를 개발하는 직원', duration_weeks=4,
                        syllabus_summary=course['outcome'] + '\n' + '\n'.join(u['description'] for u in course['units']),
                        meta_note=course['outcome'])
        for name, value in defaults.items():
            course.setdefault(name, value)
        if course['fee_won'] != 0:
            raise ValueError('무료 교육 패키지의 가격은 0원이어야 합니다.')
        courses.append(course)
    return dict(schema_version='internal-training/v1', courses=courses)


def _night_courses(package: dict) -> dict:
    """야간 보강 2개의 단일 원본을 공통 검증 형식으로 읽는다. 기본 412개 목록에는 넣지 않는다."""
    if (package.get('version') != 'course-search-147/night-20261110-v1'
            or package.get('record_source') != SOURCE or package.get('platform') != '사내교육'
            or package.get('image_url') != '/images/resource-course.svg'):
        raise ValueError('야간 교육 패키지의 버전·출처·플랫폼·표지가 다릅니다.')
    raw_courses = package.get('courses', [])
    expected = {'INTERNAL_NIGHT_147_DROPOUT', 'INTERNAL_NIGHT_147_IDS_TLS'}
    if len(raw_courses) != 2 or {c.get('id') for c in raw_courses} != expected:
        raise ValueError('승인한 야간 보강 2개 ID가 필요합니다.')
    courses = []
    for original in raw_courses:
        if original.get('difficulty') != 'INTERMEDIATE' or not original.get('distinct_from') or not original.get('skill'):
            raise ValueError('야간 교육의 수준·차별화 근거·스킬이 필요합니다.')
        course = dict(original, track='crash', fee_won=0, url=f"/resources/{original['id']}?view=curriculum",
                      image_url=package['image_url'], skills=[original['skill']], audience=original['skill'] + ' 실습 직원',
                      duration_weeks=4, meta_note=original['outcome'],
                      syllabus_summary=original['outcome'] + '\n' + '\n'.join(u['description'] for u in original['units']),
                      duration_provenance=dict(source='internal_lesson_plan',
                          lesson_minutes=[u['minutes'] for u in original['units']], package_version=package['version']))
        courses.append(course)
    return dict(schema_version='internal-training/v1', courses=courses)


def read_packages(paths: list[Path] | tuple[Path, ...] | None = None) -> list[dict]:
    courses, seen = [], set()
    for path in default_packages() if paths is None else paths:
        package = json.loads(path.read_text(encoding='utf-8'))
        if 'reviewed_links' in package and 'skill' in package and 'schema_version' not in package:
            package = _free_courses(package)
        elif 'version' in package and 'record_source' in package and 'schema_version' not in package:
            package = _night_courses(package)
        if package.get('schema_version') != 'internal-training/v1' or set(package) - {'schema_version', 'origin', 'courses'}:
            raise ValueError('교육 데이터 전용 패키지가 필요합니다. 승격·외부 연결 항목은 허용하지 않습니다.')
        for course in package['courses']:
            rid = course.get('id', '')
            if not re.fullmatch(r'INTERNAL_(?:(?:CRASH|CHALLENGE)_[0-9]+|NIGHT_147_(?:DROPOUT|IDS_TLS))', rid) or rid in seen:
                raise ValueError(f'사내교육 ID 오류 또는 중복: {rid}')
            if (type(course.get('fee_won')) is not int or course['fee_won'] < 0
                    or course.get('url') != f'/resources/{rid}?view=curriculum'
                    or not re.fullmatch(r'/images/(?:[a-z0-9_-]+/)*[a-z0-9_.-]+\.(?:svg|webp|png|jpg)', course.get('image_url', ''))
                    or course.get('difficulty') not in ('BEGINNER', 'INTERMEDIATE', 'UPPER_INTERMEDIATE', 'ADVANCED')
                    or course.get('track') not in ('crash', 'challenge')):
                raise ValueError(f'가격·URL·표지·난이도·종류 오류: {rid}')
            for key in ('title', 'audience', 'outcome', 'syllabus_summary', 'meta_note'):
                if not isinstance(course.get(key), str) or not course[key].strip():
                    raise ValueError(f'필수 설명 누락: {rid}/{key}')
            if not course.get('skills') or len(set(course['skills'])) != len(course['skills']):
                raise ValueError(f'스킬 목록 오류: {rid}')
            if not course.get('units') or any(type(u.get('minutes')) is not int or u['minutes'] <= 0
                    or not u.get('title', '').strip() or not u.get('description', '').strip() for u in course['units']):
                raise ValueError(f'차시·기간 오류: {rid}')
            weeks = course.get('duration_weeks')
            if weeks is not None and (type(weeks) is not int or weeks <= 0):
                raise ValueError(f'기간 오류: {rid}')
            seen.add(rid)
            courses.append(course)
    if not courses:
        raise ValueError('빈 교육 패키지는 적용할 수 없습니다.')
    return courses


def course_fields(course: dict) -> dict:
    minutes = sum(unit['minutes'] for unit in course['units'])
    units = [dict(title=u['title'], description=u['description'], section=f"{u['minutes']}분") for u in course['units']]
    return dict(title=course['title'], platform='사내교육', org_name='사내교육', cost=course['fee_won'],
                url=course['url'], image_url=course['image_url'], syllabus_summary=course['syllabus_summary'],
                record_source=SOURCE, content_status='ready', duration_seconds=minutes * 60,
                duration_kind='learning', duration_weeks=course.get('duration_weeks'),
                duration_provenance=course.get('duration_provenance', dict(source='internal_lesson_plan',
                    lesson_minutes=[u['minutes'] for u in course['units']])),
                curriculum=dict(source='internal_training_pilot_v1', coverage='full_outline',
                    description=course['syllabus_summary'], outcome=course['outcome'], item_count=len(units), items=units),
                enrollment_period_type='unrestricted', recruitment_status='OPEN', enrollment_start=None, enrollment_end=None)


def meta_fields(course: dict) -> dict:
    minutes = sum(unit['minutes'] for unit in course['units'])
    return dict(resource_type='course', course_id=course['id'], format='실습',
                hours=(Decimal(minutes) / 60).quantize(Decimal('.000001')), hours_origin='catalog',
                cost_won=course['fee_won'], audience=course['audience'], content=course['syllabus_summary'],
                note=course['meta_note'], is_real=False, source_label='사내교육', stage=2 if course['track'] == 'crash' else 3)


def _values(fields: dict) -> list:
    return [Jsonb(value) if isinstance(value, (dict, list)) else value for value in fields.values()]


def _upsert(conn, table: str, key: str, rid: str, fields: dict, *, refresh: bool) -> bool:
    # table/key/columns는 위 두 필드 함수와 호출부의 상수에서만 받는다.
    previous = conn.execute(f'SELECT * FROM {table} WHERE {key}=%s FOR UPDATE', (rid,)).fetchone()
    if previous is None:
        columns = [key, *fields]
        conn.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join(["%s"] * len(columns))})',
                     [rid, *_values(fields)])
        return True
    different = [name for name, value in fields.items() if previous[name] != value]
    if different:
        if not refresh:
            raise ValueError(f'기존 교육과 패키지 불일치: {rid}/{",".join(different)}; 검토 후 --refresh 사용')
        update = {name: fields[name] for name in different}
        conn.execute(f'UPDATE {table} SET {",".join(name + "=%s" for name in update)} WHERE {key}=%s',
                     [*_values(update), rid])
    return bool(different)


def _current_rows(conn, sources: dict, ids: list[str]) -> dict:
    previous = vectors.stored(conn)
    rows = conn.execute('''SELECT e.resource_id,e.embedding::text AS vector,e.dimensions,e.input_version,e.input_sha256,
        p.actual_input_sha256,p.model_revision,p.protocol,p.token_count
        FROM public.learning_resource_embeddings e JOIN growpath_bge_meta.inputs p
        ON p.kind=e.resource_type AND p.source_id=e.resource_id
        WHERE e.resource_type='courses' AND e.embedding_model=%s AND e.resource_id=ANY(%s)''',
        (vectors.MODEL, ids)).fetchall()
    result = {}
    for row in rows:
        rid = row['resource_id']
        source = sources.get(('courses', rid))
        if source and vectors.is_current(source, previous.get(('courses', rid))):
            _validate_vector(row, source)
            result[rid] = dict(row)
    return result


def _validate_vector(row: dict, source: dict) -> list[float]:
    if (row['dimensions'] != vectors.DIMENSIONS or row['input_version'] != vectors.INPUT_VERSION
            or row['input_sha256'] != source['hash']
            or row['actual_input_sha256'] != hashlib.sha256(source['text'].encode('utf-8')).hexdigest()
            or row['model_revision'] != PROVENANCE['model_revision'] or row['protocol'] != vectors.PROTOCOL
            or type(row['token_count']) is not int or not 1 <= row['token_count'] <= 8192):
        raise ValueError('벡터 원문 해시·버전·모델 이력이 일치하지 않습니다.')
    vector = vector_values(row['vector'])
    if abs(math.hypot(*vector) - 1) >= .001:
        raise ValueError('BGE 벡터는 L2 정규화되어야 합니다.')
    return vector


def export_vectors(conn, courses: list[dict], output: Path) -> dict:
    ids = [c['id'] for c in courses]
    rows = _current_rows(conn, vectors.sources(conn), ids)
    if len(rows) != len(ids):
        raise ValueError('패키지 전체의 current 벡터를 검증하지 못했습니다.')
    document = dict(schema_version='internal-training-vectors/v1', model=vectors.MODEL,
                    provenance=PROVENANCE, records=rows)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return dict(exported=len(rows), sha256=hashlib.sha256(output.read_bytes()).hexdigest())


def verify(conn, courses: list[dict], *, sources: dict | None = None) -> dict:
    """원본·차시·기간·가격·안내 URL·메타·연결·current 벡터를 읽기만 하여 대조한다."""
    for course in courses:
        rid = course['id']
        for table, key, fields in (('public.courses', 'course_id', course_fields(course)),
                                   ('app_ext.resource_meta', 'resource_key', meta_fields(course))):
            row = conn.execute(f'SELECT * FROM {table} WHERE {key}=%s', (rid,)).fetchone()
            if row is None or any(row[name] != value for name, value in fields.items()):
                raise ValueError(f'교육 원본·메타 불일치: {rid}/{table}')
        skills = conn.execute('''SELECT s.name FROM public.course_skills c
            JOIN public.skill_tags s USING(skill_id) WHERE c.course_id=%s''', (rid,)).fetchall()
        if {row['name'] for row in skills} != set(course['skills']):
            raise ValueError(f'교육 스킬 연결 불일치: {rid}')
    ids = [c['id'] for c in courses]
    current = _current_rows(conn, vectors.sources(conn) if sources is None else sources, ids)
    if len(current) != len(ids):
        raise ValueError('최종 current 벡터 검증 실패')
    return dict(verified_courses=len(ids), verified_vectors=len(current),
                free_courses=sum(c['fee_won'] == 0 for c in courses))


def _read_cache(path: Path | None) -> dict:
    if path is None:
        return {}
    cache = json.loads(path.read_text(encoding='utf-8'))
    if (cache.get('schema_version') != 'internal-training-vectors/v1' or cache.get('model') != vectors.MODEL
            or cache.get('provenance') != PROVENANCE):
        raise ValueError('벡터 캐시의 BGE 계약이 다릅니다.')
    return cache['records']


def install(conn, courses: list[dict], *, apply: bool = False, refresh: bool = False,
            vector_cache: Path | None = None, cache_only: bool = False, client=None) -> dict:
    cache = _read_cache(vector_cache)
    with conn.transaction(force_rollback=not apply):
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('internal-training-package-147'))")
        conn.execute('SET LOCAL search_path TO public,extensions')
        inserted, changed = 0, 0
        for course in courses:
            rid = course['id']
            prior = conn.execute('SELECT record_source FROM public.courses WHERE course_id=%s FOR UPDATE', (rid,)).fetchone()
            if prior and prior['record_source'] != SOURCE:
                raise ValueError(f'다른 출처의 강좌와 ID 충돌: {rid}')
            fields = course_fields(course)
            # 기존 난이도는 담당자가 승인한 원본을 보존한다. 새 교육에만 패키지 값을 넣는다.
            if prior is None:
                fields['difficulty'] = course['difficulty']
            inserted += int(prior is None)
            changed += int(_upsert(conn, 'public.courses', 'course_id', rid, fields, refresh=refresh))
            actual = conn.execute('SELECT skill_id FROM public.course_skills WHERE course_id=%s', (rid,)).fetchall()
            expected = conn.execute('SELECT skill_id FROM public.skill_tags WHERE name=ANY(%s)', (course['skills'],)).fetchall()
            if len(expected) != len(course['skills']):
                raise ValueError(f'등록되지 않은 스킬: {rid}')
            desired = {row['skill_id'] for row in expected}
            extra = {row['skill_id'] for row in actual} - desired
            if extra and not refresh:
                raise ValueError(f'패키지 밖 스킬 연결: {rid}')
            if extra:
                conn.execute('DELETE FROM public.course_skills WHERE course_id=%s AND skill_id=ANY(%s)', (rid, sorted(extra)))
            for skill in desired:
                conn.execute('INSERT INTO public.course_skills(course_id,skill_id) VALUES(%s,%s) ON CONFLICT DO NOTHING', (rid, skill))
            meta = conn.execute('SELECT course_id,resource_type FROM app_ext.resource_meta WHERE resource_key=%s FOR UPDATE', (rid,)).fetchone()
            if meta and (meta['course_id'] != rid or meta['resource_type'] != 'course'):
                raise ValueError(f'다른 자료 메타데이터와 ID 충돌: {rid}')
            _upsert(conn, 'app_ext.resource_meta', 'resource_key', rid, meta_fields(course), refresh=refresh)

        ids = [c['id'] for c in courses]
        sources = vectors.sources(conn)
        selected, _ = vectors.pending_sources(sources, vectors.stored(conn), ['courses'], ids, len(ids))
        current = _current_rows(conn, sources, ids)
        pending = sorted(set(ids) - current.keys())
        reused, generated, missing_cache = 0, 0, []
        for rid in pending:
            source = selected['courses', rid]
            cached = cache.get(rid)
            if cached:
                _validate_vector(cached, source)
            elif cache_only:
                missing_cache.append(rid)
        if missing_cache:
            raise ValueError('재사용할 current 벡터 없음: ' + ','.join(missing_cache))
        if apply:
            for rid in pending:
                source = selected['courses', rid]
                cached = cache.get(rid)
                if cached:
                    vector = _validate_vector(cached, source)
                    row = cached
                    reused += 1
                else:
                    vector = embed_texts([source['text']], client=client)[0]
                    # token_count는 기존 resource_vectors와 같은 공백 기준 추정값이다.
                    # 실제 8192 토큰 한도는 canonical 서버가 자르지 않고 검사한다.
                    row = dict(actual_input_sha256=hashlib.sha256(source['text'].encode('utf-8')).hexdigest(),
                               token_count=max(1, min(len(source['text'].split()), 8192)), protocol=vectors.PROTOCOL)
                    _validate_vector(dict(row, input_sha256=source['hash'], input_version=vectors.INPUT_VERSION,
                        dimensions=vectors.DIMENSIONS, model_revision=PROVENANCE['model_revision'], vector=vector), source)
                    generated += 1
                conn.execute('''INSERT INTO public.learning_resource_embeddings(resource_type,resource_id,course_id,
                    embedding_model,dimensions,input_version,input_sha256,embedding)
                    VALUES('courses',%s,%s,%s,%s,%s,%s,%s::vector) ON CONFLICT(resource_type,resource_id,embedding_model)
                    DO UPDATE SET input_sha256=EXCLUDED.input_sha256,input_version=EXCLUDED.input_version,
                    dimensions=EXCLUDED.dimensions,embedding=EXCLUDED.embedding,updated_at=now()''',
                    (rid,rid,vectors.MODEL,vectors.DIMENSIONS,vectors.INPUT_VERSION,source['hash'],json.dumps(vector)))
                conn.execute('''INSERT INTO growpath_bge_meta.inputs(kind,source_id,source_sha256,actual_input_sha256,
                    protocol,model_revision,token_count) VALUES('courses',%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(kind,source_id) DO UPDATE SET source_sha256=EXCLUDED.source_sha256,
                    actual_input_sha256=EXCLUDED.actual_input_sha256,protocol=EXCLUDED.protocol,
                    model_revision=EXCLUDED.model_revision,token_count=EXCLUDED.token_count''',
                    (rid,source['hash'],row['actual_input_sha256'],row['protocol'],PROVENANCE['model_revision'],row['token_count']))
            final_sources = vectors.sources(conn)
            if any(final_sources[key]['hash'] != source['hash'] for key, source in selected.items()):
                raise ValueError('적재 중 원문 변경을 감지했습니다. 전체 롤백합니다.')
            verify(conn, courses, sources=final_sources)
        return dict(applied=apply, internal_courses=len(ids), inserted=inserted, changed_courses=changed,
                    current_before=len(current), pending_vectors=len(pending), reused_vectors=reused,
                    generated_vectors=generated, external_courses_changed=0, schema_changed=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--package', action='append', type=Path, help='지정하면 기본 목록 대신 사용. 추가분은 기본 3개와 함께 반복 지정')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--refresh', action='store_true', help='검토한 패키지로 소유 필드·스킬 연결 갱신. 기존 난이도는 보존')
    parser.add_argument('--vector-cache', type=Path)
    parser.add_argument('--cache-only', action='store_true', help='캐시에 없는 원문은 추론 없이 실패')
    parser.add_argument('--export-vectors', type=Path, help='current 벡터를 읽기 전용으로 검증·내보내기')
    parser.add_argument('--verify-only', action='store_true', help='원본·메타·연결·벡터를 읽기 전용으로 검사')
    args = parser.parse_args()
    if (args.export_vectors or args.verify_only) and (args.apply or args.refresh):
        parser.error('읽기 전용 검사·내보내기와 적용·갱신은 분리해서 실행하세요.')
    courses = read_packages(args.package)
    with psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg:', 'postgresql:'),
                         row_factory=dict_row, autocommit=True) as conn:
        if conn.info.dbname != args.database:
            raise ValueError('대상 DB 이름 불일치')
        if args.export_vectors or args.verify_only:
            with conn.transaction():
                conn.execute('SET TRANSACTION READ ONLY')
                result = export_vectors(conn, courses, args.export_vectors) if args.export_vectors else verify(conn, courses)
        else:
            result = install(conn, courses, apply=args.apply, refresh=args.refresh,
                             vector_cache=args.vector_cache, cache_only=args.cache_only)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
