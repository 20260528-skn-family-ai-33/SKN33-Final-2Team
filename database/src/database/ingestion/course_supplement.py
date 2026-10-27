"""Validate and add only reviewed new courses; never reset/finalize other catalogs."""
from datetime import datetime, timezone
import hashlib
from urllib.parse import urlsplit, parse_qs, urlencode

from psycopg.types.json import Jsonb

from src.shared.catalog_eligibility import eligible_keys, exclusion_reason
from src.shared.catalog_scope import scoped_matches
from src.shared.skill_matching import SkillMatcher
from src.database.ingestion.ai_catalog_filter import AICatalogFilter
from src.shared.course_sources import step_identity, kmooc_identity
from src.database.vectors import resource_vectors

FIELDS = {'course_id', 'title', 'org_name', 'platform', 'url', 'source_url', 'content_status',
          'record_source', 'source_verified_at', 'syllabus_summary', 'cost', 'difficulty',
          'image_url', 'duration_weeks', 'category_name', 'enrollment_start', 'enrollment_end',
          'enrollment_period_type', 'recruitment_status'}


def canonical_url(value: str) -> tuple:
    parsed = urlsplit(value)
    host, query = parsed.hostname, ''
    if host in ('kocw.net', 'www.kocw.net'):
        host = 'kocw.net'
        query = urlencode(sorted((k, v) for k, values in parse_qs(parsed.query).items()
                                 if k == 'kemId' for v in values))
    elif host in ('step.or.kr', 'www.step.or.kr'):
        host = 'step.or.kr'
        query = urlencode(sorted((k, v) for k, values in parse_qs(parsed.query).items()
                                 if k in ('crscd', 'crsseqId') for v in values))
    return host, parsed.path.rstrip('/'), query


def validate_rows(rows: list, skills: list, existing: list, *, now=None) -> list:
    """Validate the complete batch before any write or paid request."""
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError('보충 강좌는 1~50개로 제한합니다.')
    matcher = SkillMatcher(skills)
    ids = {r['course_id'] for r in existing}
    urls = {canonical_url(r['url']) for r in existing}
    result = []
    for item in rows:
        fields = dict(item['fields'])
        if set(fields) - FIELDS or fields.get('record_source') != item['source']:
            raise ValueError('보충 강좌 필드/출처가 올바르지 않습니다.')
        if item['source'] not in ('WEB_KOCW', 'API_MS_LEARN', 'WEB_INFLEARN', 'WEB_OPENTUTORIALS', 'WEB_STEP', 'API_KMOOC'):
            raise ValueError('지원하지 않는 강좌 출처입니다.')
        rid = fields['course_id']
        url = canonical_url(fields['url'])
        if rid in ids or url in urls:
            raise ValueError('기존 강좌 또는 배치 안의 중복 강좌가 있습니다.')
        ids.add(rid)
        urls.add(url)
        if item['source'] == 'API_MS_LEARN':
            uid = item['raw'].get('uid')
            if (not isinstance(uid, str) or item['external_key'] != uid
                    or rid != 'MS_' + hashlib.md5(uid.encode()).hexdigest()[:12]
                    or item['raw'].get('url') != fields['url']):
                raise ValueError('Microsoft 공식 원본 ID/URL이 일치하지 않습니다.')
        elif item['source'] in ('WEB_KOCW', 'WEB_INFLEARN', 'WEB_OPENTUTORIALS') and str(item['raw'].get('source_id')) != str(item['external_key']):
            raise ValueError('교육 사이트 공식 원본 ID가 일치하지 않습니다.')
        elif item['source'] in ('WEB_STEP', 'API_KMOOC'):
            raw = item['raw']
            expected_key = (str(raw.get('crscd')) + '_' + str(raw.get('crsseqId'))
                            if item['source'] == 'WEB_STEP' else str(raw.get('id')))
            check_identity = step_identity if item['source'] == 'WEB_STEP' else kmooc_identity
            if item['external_key'] != expected_key or not check_identity(fields, raw) or not raw.get('public_detail'):
                raise ValueError('교육 사이트 공식 원본 ID/상세 근거가 일치하지 않습니다.')
        reason = exclusion_reason('courses', fields, item['source'], item['raw'], item['fetched_at'], now=now)
        if reason:
            raise ValueError('강좌 보충 검사 실패: ' + reason)
        matches = scoped_matches(matcher, fields)
        reviewed = item.get('reviewed_skill_ids')
        if (not isinstance(reviewed, list) or not reviewed
                or any(type(sid) is not int or sid not in matches for sid in reviewed)):
            raise ValueError('커리큘럼 검토 스킬과 본문 스킬 근거가 일치하지 않습니다.')
        # Prerequisite skills and merely mentioned technologies are not added.
        result.append({**item, 'fields': fields, 'matches': {sid: matches[sid] for sid in reviewed}})
    return result


def validate_catalog(rows: list, skills: list, existing: list, *, max_courses=50, now=None) -> list:
    """Preflight a finite catalog in bounded blocks, retaining cross-block duplicate checks."""
    if type(max_courses) is not int or not 1 <= max_courses <= 2500:
        raise ValueError('강좌 심사 범위는 1~2500개로 지정하세요.')
    if not isinstance(rows, list) or not 1 <= len(rows) <= max_courses:
        raise ValueError('강좌 수가 이번 심사 범위를 벗어났습니다.')
    checked, seen = [], list(existing)
    for start in range(0, len(rows), 50):
        block = validate_rows(rows[start:start + 50], skills, seen, now=now)
        checked.extend(block)
        seen.extend(row['fields'] for row in block)
    return checked


def _insert_approved(conn, rows: list, skills: list, validator, *, embedding_client=None) -> dict:
    """Caller provides an outer transaction; any failure rolls back the entire catalog."""
    conn.execute('SELECT pg_advisory_xact_lock(763250131)')
    conn.execute('LOCK TABLE public.courses IN SHARE ROW EXCLUSIVE MODE')
    current = conn.execute('SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id').fetchall()
    if current != skills:
        raise ValueError('검토 중 스킬이 변경되었습니다. 다시 준비하세요.')
    existing = conn.execute('SELECT course_id,title,url FROM public.courses').fetchall()
    checked = validator(rows, skills, existing)
    ids = {r['fields']['course_id'] for r in checked}
    original_rows = {r['fields']['course_id']: r for r in rows}
    for row in checked:
        if not row.get('matches') or not set(row['matches']) <= set(row['reviewed_skill_ids']):
            raise ValueError('심사 결과의 스킬 범위가 올바르지 않습니다.')
        # Keep the AI-approved subset; validation must not restore removed skills.
        original = original_rows[row['fields']['course_id']]
        approved = original['matches']
        if not approved or not set(approved) <= set(row['matches']):
            raise ValueError('심사 결과의 스킬이 본문에 입증되지 않습니다.')
        fields = {**row['fields'], 'last_batch_updated': datetime.now(timezone.utc)}
        fields.setdefault('duration_weeks', None)
        fields.setdefault('enrollment_period_type', 'unrestricted')
        columns = list(fields)
        conn.execute('INSERT INTO public.courses (' + ','.join(columns) + ') VALUES (' + ','.join(['%s'] * len(columns)) + ')',
                     [fields[k] for k in columns])
        rid = fields['course_id']
        for sid in approved:
            conn.execute('INSERT INTO public.course_skills (course_id,skill_id) VALUES (%s,%s)', (rid, sid))
        conn.execute('''INSERT INTO growpath_meta.catalog_api_sources
            (resource_type,source,external_key,entity_key,payload,mapping_evidence,fetched_at)
            VALUES ('courses',%s,%s,%s,%s,%s,%s)''',
                     (row['source'], row['external_key'], rid, Jsonb(row['raw']), Jsonb(approved), row['fetched_at']))
    previous = resource_vectors.stored(conn)
    pending = {key for key, source in resource_vectors.sources(conn).items()
               if not resource_vectors.is_current(source, previous.get(key))}
    if pending != {('courses', rid) for rid in ids}:
        raise ValueError('기존 자료에도 벡터 갱신이 필요합니다. 보충 적재는 기존 자료를 갱신하지 않습니다.')
    vectors = resource_vectors.embed(conn, client=embedding_client)
    allowed, _ = eligible_keys(conn)
    if not {('courses', rid) for rid in ids} <= allowed or vectors['embedded_count'] != len(ids):
        raise ValueError('추가 강좌의 추천/벡터 검증에 실패했습니다.')
    return {'inserted_courses': len(ids), 'course_ids': sorted(ids), 'vectors': vectors}


def insert_approved(conn, rows: list, skills: list, *, embedding_client=None) -> dict:
    return _insert_approved(conn, rows, skills, validate_rows, embedding_client=embedding_client)


def insert_catalog_approved(conn, rows: list, skills: list, *, max_courses=50, embedding_client=None) -> dict:
    def validator(items, current_skills, existing):
        return validate_catalog(items, current_skills, existing, max_courses=max_courses)
    return _insert_approved(conn, rows, skills, validator, embedding_client=embedding_client)


def prepare(conn, rows: list, *, max_courses=50) -> tuple:
    skills = conn.execute('SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id').fetchall()
    existing = conn.execute('SELECT course_id,title,url FROM public.courses').fetchall()
    checked = validate_catalog(rows, skills, existing, max_courses=max_courses)
    return skills, checked


def review(rows: list, skills: list, *, ai_client=None) -> list:
    return AICatalogFilter(skills, client=ai_client).filter('courses', rows)
