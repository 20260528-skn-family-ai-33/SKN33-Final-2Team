"""Factual identity and availability checks for STEP and K-MOOC additions."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import parse_qs, urlsplit


def source_time(value, *, step=False):
    try:
        if step:
            return datetime.strptime(str(value), '%Y%m%d%H%M%S').replace(
                tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)
        if isinstance(value, datetime):
            return value if value.tzinfo else None
        if re.fullmatch(r'\d{10}', str(value)):
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _detail_matches(fields, raw, now):
    detail = raw.get('public_detail') or {}
    if not isinstance(detail, dict):
        return False
    checked = source_time(detail.get('fetched_at'))
    titles = detail.get('curriculum_titles')
    return (isinstance(detail, dict) and checked is not None
            and 0 <= (now - checked).total_seconds() <= 30 * 86400
            and detail.get('course_id') == fields.get('course_id')
            and detail.get('url') == fields.get('url')
            and detail.get('title') == fields.get('title')
            and re.fullmatch(r'[a-f0-9]{64}', str(detail.get('html_sha256') or '')) is not None
            and isinstance(titles, list)
            and sum(isinstance(t, str) and bool(t.strip()) for t in titles) >= 2)


def step_identity(fields, raw):
    url = urlsplit(str(fields.get('url') or ''))
    keys = ('crscd', 'crsseqId', 'dgrId', 'dgrSeCd', 'verCd')
    expected = {key: [str(raw.get(key) or '')] for key in keys}
    ids = [str(raw.get(key) or '') for key in keys[:2]]
    return (url.scheme == 'https' and url.hostname == 'www.step.or.kr'
            and not url.username and not url.password
            and url.path == '/dtyCrsDetailForm.do' and not url.fragment
            and all(re.fullmatch(r'\d+', value) for value in ids)
            and parse_qs(url.query, keep_blank_values=True) == expected
            and fields.get('course_id') == 'STEP_' + '_'.join(ids)
            and fields.get('title') == raw.get('crsNm')
            and fields.get('org_name') == (raw.get('orgnztNm') or 'STEP'))


def _period_matches(fields, start, end):
    return (start is not None and end is not None and start <= end
            and fields.get('enrollment_period_type') == 'scheduled'
            and source_time(fields.get('enrollment_start')) == start
            and source_time(fields.get('enrollment_end')) == end)


def step_reason(fields, raw, now):
    if not step_identity(fields, raw) or not _detail_matches(fields, raw, now):
        return 'missing_current_step_detail'
    price = str(raw.get('educst') if raw.get('educst') is not None else '').replace(',', '').strip()
    try:
        valid_price = price.isascii() and price.isdigit() and Decimal(str(fields.get('cost'))) == Decimal(price)
    except InvalidOperation:
        valid_price = False
    if not valid_price:
        return 'missing_factual_step_price'
    start = source_time(raw.get('crsregStrtdt'), step=True)
    end = source_time(raw.get('crsregEnddt'), step=True)
    if (not _period_matches(fields, start, end) or not start <= now <= end
            or fields.get('recruitment_status') != 'OPEN'):
        return 'step_not_confirmed_open'
    return None


def kmooc_identity(fields, raw):
    url = urlsplit(str(fields.get('url') or ''))
    source_id = str(raw.get('id') or '')
    return (re.fullmatch(r'\d+', source_id) is not None
            and url.scheme == 'https' and url.hostname == 'www.kmooc.kr'
            and not url.username and not url.password
            and url.path == '/view/course/detail/' + source_id and not url.query and not url.fragment
            and fields.get('course_id') == 'KMOOC_' + source_id
            and fields.get('title') == raw.get('name')
            and fields.get('org_name') == raw.get('org_name'))


def kmooc_reason(fields, raw, now):
    start = source_time(raw.get('enrollment_start'))
    end = source_time(raw.get('enrollment_end'))
    study_end = source_time(raw.get('study_end'))
    detail = raw.get('public_detail')
    if detail is not None:
        if not isinstance(detail, dict):
            return 'missing_current_kmooc_detail'
        if not kmooc_identity(fields, raw) or not _detail_matches(fields, raw, now):
            return 'missing_current_kmooc_detail'
        if not _period_matches(fields, start, end):
            return 'kmooc_period_mismatch'
    # Legacy currently enrolling API records retain their original contract.
    if (start is not None and end is not None and study_end is not None
            and start <= now <= end and now <= study_end and raw.get('public_yn') == 'Y'):
        if detail is not None and (detail.get('enroll_action_present') is not True
                                   or fields.get('recruitment_status') != 'OPEN'):
            return 'course_not_confirmed_open'
        return None
    # Ended dates stay ended. Metadata alone is insufficient to admit an audit course.
    if (detail is not None and raw.get('public_yn') == 'Y' and raw.get('is_auditor') == 'Y'
            and start is not None and end is not None and start <= end < now
            and detail.get('audit_action_present') is True
            and detail.get('public_page_title_matches') is True
            and fields.get('recruitment_status') == 'CLOSED'):
        return None
    return 'course_not_confirmed_open'
