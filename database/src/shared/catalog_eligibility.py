"""Fail closed on unknown availability. No generated evidence and no DB mutations."""
from src.shared.catalog_scope import scope_reason, scoped_matches
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo

from src.shared.catalog_quality import missing_fields, certification_availability
from src.shared.course_sources import step_reason, kmooc_reason

PRIMARY_KEYS = {'courses': 'course_id', 'books': 'isbn', 'certifications': 'cert_id',
                'jobs': 'job_id', 'majors': 'major_id'}
MAX_EVIDENCE_AGE_DAYS = 30


def timestamp(value):
    try:
        numeric = str(value).strip()
        if numeric.isascii() and numeric.isdigit() and len(numeric) in (10,13):
            seconds = int(numeric) / (1000 if len(numeric)==13 else 1)
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo('Asia/Seoul'))
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def public_url(value, hosts):
    try:
        url = urlsplit(str(value or ''))
        return url.scheme == 'https' and url.hostname in hosts and not url.username and not url.password
    except ValueError:
        return False


def exclusion_reason(kind, fields, source, raw, fetched_at, *, now=None):
    reason = scope_reason(kind, fields, source, raw)
    if reason:
        return reason
    now = now or datetime.now(timezone.utc)
    if fields.get('content_status') not in (None, 'ready'):
        return 'not_ready'
    if kind == 'books':
        return 'insufficient_catalog_metadata' if missing_fields(kind, fields) else None
    checked = timestamp(fetched_at)
    if checked is None or not 0 <= (now - checked).total_seconds() <= MAX_EVIDENCE_AGE_DAYS * 86400:
        return 'missing_or_expired_availability_evidence'
    if fields.get('content_status') not in (None, 'ready'):
        return 'not_ready'
    if missing_fields(kind, fields):
        return 'insufficient_factual_content'
    if not isinstance(raw, dict):
        return 'missing_official_detail'
    if kind == 'certifications':
        if certification_availability(fields, now.astimezone(ZoneInfo('Asia/Seoul')).date()) != 'available':
            return 'retired_or_retiring_or_uncertain'
        if source == 'API_ODCLOUD_KDATA':
            return None if raw.get('exam_records') else 'missing_official_exam_subjects'
        if source != 'API_MS_CERT':
            return 'unsupported_certification_source'
        item = raw.get('merged_certification') or {}
        if not item:
            item = raw.get('certification') or {}
        if not item:
            return 'missing_official_certification_detail'
        notices = ' '.join(str(record.get(key) or '') for record in
                          [raw.get('certification') or {}, item, *(raw.get('exam_records') or [])]
                          for key in ('title', 'summary', 'subtitle'))
        if certification_availability({'description': notices}, now.date()) != 'available':
            return 'retired_or_retiring_or_uncertain'
        return None
    if kind == 'courses':
        if source == 'WEB_INFLEARN':
            url = str(fields.get('url') or '')
            source_id = str(raw.get('source_id') or '')
            parsed = urlsplit(url)
            info = raw.get('course_info') or {}
            lessons = raw.get('lessons') or []
            if (not public_url(url, {'www.inflearn.com'}) or raw.get('url') != url
                    or not source_id.isascii() or not source_id.isdigit()
                    or fields.get('course_id') != 'INFLEARN_' + source_id
                    or str(info.get('id')) != source_id
                    or unquote(parsed.path) != '/course/' + str(info.get('slug') or '')
                    or parse_qs(parsed.query) != {'cid': [source_id]}
                    or info.get('status') != 'PUBLISH' or info.get('originalLanguage') != 'KO'
                    or raw.get('http_status') != 200
                    or raw.get('availability_basis') != 'published_sale_offer'
                    or raw.get('metadata_exposure') is not True
                    or info.get('title') != fields.get('title')
                    or not isinstance(lessons, list)):
                return 'missing_current_inflearn_curriculum_or_enrollment'
            price = (info.get('paymentInfo') or {}).get('krwPaymentPrice')
            payment = info.get('paymentInfo') or {}
            if (payment.get('type') not in {'REGULAR_PRICE_PURCHASE', 'DISCOUNTED_PURCHASE', 'FREE'}
                    or type(price) is not int or price < 0 or fields.get('cost') != price):
                return 'missing_factual_inflearn_price'
            if payment.get('type') == 'FREE' and price != 0:
                return 'missing_factual_inflearn_price'
            videos = [r for r in lessons if isinstance(r, dict) and r.get('title') and r.get('hasVideo') is True]
            return None if len(videos) >= 2 else 'missing_current_inflearn_curriculum_or_enrollment'
        if source == 'WEB_OPENTUTORIALS':
            url = str(fields.get('url') or '')
            source_id = str(raw.get('source_id') or '')
            lessons = raw.get('lessons') or []
            if (not public_url(url, {'opentutorials.org'}) or raw.get('url') != url
                    or not source_id.isascii() or not source_id.isdigit()
                    or fields.get('course_id') != 'OPENTUTORIALS_' + source_id
                    or urlsplit(url).path != '/course/' + source_id or urlsplit(url).query
                    or raw.get('http_status') != 200 or raw.get('public_marker_present') is not True
                    or fields.get('cost') != 0 or not isinstance(lessons, list)):
                return 'missing_current_opentutorials_public_curriculum'
            videos = [r for r in lessons if isinstance(r, dict) and r.get('title')
                      and r.get('http_status') == 200 and r.get('video_embed_present') is True
                      and public_url(r.get('url'), {'opentutorials.org'})
                      and urlsplit(r['url']).path.startswith('/course/' + source_id + '/')]
            return None if len(videos) >= 2 else 'missing_current_opentutorials_public_curriculum'
        if source == 'WEB_KOCW':
            url = str(fields.get('url') or '')
            source_id = str(raw.get('source_id') or '')
            until = timestamp(raw.get('available_until'))
            lessons = raw.get('lessons')
            if (not public_url(url, {'www.kocw.net', 'kocw.net'}) or raw.get('url') != url
                    or not source_id.isascii() or not source_id.isdigit()
                    or fields.get('course_id') != 'KOCW_' + source_id
                    or urlsplit(url).path != '/home/search/kemView.do'
                    or urlsplit(url).query != 'kemId=' + source_id
                    or raw.get('http_status') != 200 or until is None or now >= until
                    or not isinstance(lessons, list)):
                return 'missing_current_kocw_public_curriculum'
            videos = [row for row in lessons if isinstance(row, dict) and row.get('video_listed') is True
                      and row.get('player_action_present') is True and not row.get('suspended_marker')
                      and row.get('title')]
            return None if len(videos) >= 2 else 'missing_current_kocw_public_curriculum'
        if source == 'API_MS_LEARN':
            if (raw.get('type') == 'module' and raw.get('uid') and raw.get('units')
                    and public_url(raw.get('url'), {'learn.microsoft.com'})):
                return None
            return 'missing_published_learning_module'
        if source == 'API_KMOOC':
            return kmooc_reason(fields, raw, now)
        if source == 'WEB_STEP':
            return step_reason(fields, raw, now)
        return 'unsupported_availability_source'
    if kind == 'jobs' and source == 'API_CAREERNET':
        return None if (raw.get('detail_record') or {}).get('baseInfo', {}).get('job_cd') else 'missing_current_job_detail'
    if kind == 'majors' and source == 'API_CAREERNET_MAJOR':
        return None if (raw.get('detail_record') or {}).get('main_subject') else 'missing_current_major_detail'
    return 'unsupported_availability_source'


def eligible_keys(conn):
    """Recheck saved source evidence at retrieval time; legacy rows fail closed."""
    from src.shared.skill_matching import SkillMatcher
    matcher = SkillMatcher(conn.execute('SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id').fetchall())
    sources = {}
    for row in conn.execute('''SELECT resource_type,entity_key,source,payload,fetched_at
                               FROM growpath_meta.catalog_api_sources ORDER BY fetched_at DESC''').fetchall():
        sources.setdefault((row['resource_type'], row['entity_key']), []).append(row)
    eligible, report = set(), {}
    for kind, pk in PRIMARY_KEYS.items():
        reasons, count = Counter(), 0
        for record in conn.execute(f"SELECT to_jsonb(t)-'embedding' AS record FROM public.{kind} t").fetchall():
            fields = record['record']
            key = (kind, str(fields[pk]))
            body = '\n'.join(str(fields.get(f) or '') for f in ('title','syllabus_summary','description','test_subjects','curriculum','ncs_units'))
            count += 1
            if not scoped_matches(matcher, fields):
                reasons['no_it_skill_evidence'] += 1
                continue
            failures = [exclusion_reason(kind, fields, s['source'], s['payload'], s['fetched_at'])
                        for s in sources.get(key, [])]
            if failures and None in failures:
                eligible.add(key)
            else:
                reasons[failures[0] if failures else 'missing_api_source_record'] += 1
        report[kind] = {'total': count, 'usable': sum(k[0] == kind for k in eligible),
                        'excluded': dict(reasons)}
    return eligible, report
