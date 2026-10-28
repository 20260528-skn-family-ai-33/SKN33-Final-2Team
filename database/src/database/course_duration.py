"""Normalize stored provider durations without changing vector inputs or source text."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import re
from statistics import median

from psycopg.types.json import Jsonb

VERSION = 'provider-duration-and-curriculum/v3'
# Transparent planning assumptions, never presented as provider-confirmed time.
LESSON_MINUTES = {'WEB_KOCW': 50, 'WEB_OPENTUTORIALS': 20, 'WEB_INFLEARN': 20}


def kocw_chapters(lessons):
    """A numbered chapter can contain many short clips; blank cells inherit it."""
    chapters, current, videos, ungrouped = set(), None, 0, 0
    for index, lesson in enumerate(lessons):
        label = re.sub(r'\s+', '', str(lesson.get('chapter') or '')).rstrip('.')
        if label:
            current = label
        if not lesson.get('video_listed') or lesson.get('suspended_marker'):
            continue
        videos += 1
        if current is None:
            ungrouped += 1
        chapters.add(current if current is not None else f'ungrouped:{index}')
    return len(chapters), videos, ungrouped


def positive_seconds(value, multiplier=1):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value)) * multiplier
        if not number.is_finite() or number <= 0 or number != number.to_integral_value() or number > 2147483647:
            return None
        return int(number)
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize(source, payload, *, url=None, fetched_at=None, curriculum=None):
    payload = payload or {}
    proof = {'version': VERSION, 'source': source, 'url': url or payload.get('url'),
             'fetched_at': str(fetched_at) if fetched_at else None,
             'payload_sha256': hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()}
    seconds = kind = estimate = None
    lessons = payload.get('lessons') or []
    if source == 'API_MS_LEARN':
        seconds, kind = positive_seconds(payload.get('duration_in_minutes'), 60), 'learning'
        proof.update(field='duration_in_minutes', unit='minutes')
    elif source == 'API_KMOOC':
        seconds, kind = positive_seconds(payload.get('course_playtime')), 'learning'
        video = positive_seconds(payload.get('vod_playtime'))
        proof.update(field='course_playtime', unit='seconds', video_seconds=video)
        if seconds is None and video:
            seconds, kind = video, 'video'
            proof.update(field='vod_playtime')
    elif source == 'WEB_STEP':
        seconds, kind = positive_seconds(payload.get('edutime'), 3600), 'learning'
        proof.update(field='edutime', unit='hours')
    elif source == 'WEB_INFLEARN':
        videos = [lesson for lesson in lessons if lesson.get('hasVideo') is True]
        durations = [positive_seconds(lesson.get('runtime')) for lesson in videos]
        ids = [lesson.get('id') for lesson in videos]
        missing = sum(value is None for value in durations)
        duplicate = len(set(ids)) != len(ids) or any(value is None for value in ids)
        known = sum(value or 0 for value in durations)
        proof.update(field='lessons[hasVideo=true].runtime', unit='seconds', video_count=len(videos),
                     missing_video_durations=missing, known_video_seconds=known, duplicate_video_ids=duplicate)
        if videos and not missing and not duplicate:
            seconds, kind = known, 'video'
        elif videos and not duplicate:
            # Preserve known runtimes and estimate only the missing video entries.
            observed = [value for value in durations if value is not None]
            imputed = round(median(observed)) if observed else LESSON_MINUTES[source] * 60
            estimate = known + missing * imputed
            proof.update(estimate_basis='known video seconds + missing videos × same-course median seconds' if observed else 'missing videos × planning assumption seconds',
                         imputed_video_seconds=imputed, observed_video_count=len(observed),
                         estimate_confidence='within_course' if observed else 'low')
    if seconds is None and estimate is None:
        if source == 'WEB_KOCW':
            count, videos, ungrouped = kocw_chapters(lessons)
            proof.update(video_count=videos, ungrouped_video_count=ungrouped, estimate_unit='chapter')
        elif source == 'WEB_OPENTUTORIALS':
            count = (curriculum or {}).get('curriculum_lesson_count', 0)
            if count:proof.update(curriculum)
        else:
            count = 0
        if count:
            estimate = count * LESSON_MINUTES[source] * 60
            proof.update(estimate_basis='full curriculum lessons × assumed learning minutes' if source=='WEB_OPENTUTORIALS' else 'numbered chapters × assumed learning minutes',
                         lesson_count=count, minutes_per_lesson=LESSON_MINUTES[source], estimate_confidence='low')
        else:
            # Explicit fallback only for an uncountable curriculum, not a provider duration.
            estimate = 2 * 3600
            proof.update(estimate_basis='curriculum count unavailable; initial planning allowance', fallback_hours=2)
    proof['status'] = 'confirmed' if seconds is not None else 'partial' if proof.get('known_video_seconds') else 'estimated'
    return {'duration_seconds': seconds, 'duration_kind': kind if seconds else None,
            'estimated_duration_seconds': None if seconds else estimate, 'duration_provenance': proof}


class _OutlineLinks(HTMLParser):
    def __init__(self):super().__init__();self.links=set()
    def handle_starttag(self, tag, attrs):
        if tag=='a':
            href=dict(attrs).get('href')
            if href:self.links.add(href)


def full_curriculum(payload, previous, source_root):
    """Use hash-verified cached outline, or retain its count on a restored DB."""
    expected=payload.get('html_sha256')
    if expected and previous.get('curriculum_html_sha256')==expected and previous.get('curriculum_lesson_count',0)>0:
        return {k:previous[k] for k in ('curriculum_lesson_count','curriculum_html_sha256')}
    relative=payload.get('html_path')
    if not relative or not expected:return {}
    root=Path(source_root).resolve();path=(root/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():return {}
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Curriculum cache checksum mismatch')
    parser=_OutlineLinks();parser.feed(raw.decode('utf-8'))
    pattern=re.compile(r'/course/'+re.escape(str(payload.get('source_id')))+r'/(\d+)(?:[/?#]|$)')
    ids={m.group(1) for href in parser.links if (m:=pattern.search(href))}
    return {'curriculum_lesson_count':len(ids),'curriculum_html_sha256':expected} if ids else {}


def backfill(conn, *, apply=False, source_root=None):
    """Existing rows only; report before writing, preserve unrelated fields/embeddings."""
    rows = conn.execute('''SELECT c.course_id,c.url,c.duration_seconds,c.duration_kind,c.estimated_duration_seconds,c.duration_provenance,
        s.source,s.payload,s.fetched_at FROM public.courses c LEFT JOIN LATERAL
        (SELECT source,payload,fetched_at FROM growpath_meta.catalog_api_sources
         WHERE resource_type='courses' AND entity_key=c.course_id ORDER BY fetched_at DESC,source,external_key LIMIT 1) s ON true
        ORDER BY c.course_id''').fetchall()
    counts, changed = Counter(), []
    for row in rows:
        # A future explicit canonical manual override must not be silently replaced.
        if (row['duration_provenance'] or {}).get('source') == 'MANUAL':
            counts['manual_preserved'] += 1
            continue
        curriculum=full_curriculum(row['payload'],row['duration_provenance'] or {},source_root or Path(__file__).resolve().parents[2]) if row['source']=='WEB_OPENTUTORIALS' else None
        values = normalize(row['source'], row['payload'], url=row['url'], fetched_at=row['fetched_at'],curriculum=curriculum)
        counts['confirmed' if values['duration_seconds'] else 'estimated'] += 1
        counts[str(row['source'])] += 1
        if any(row[key] != value for key, value in values.items()):
            changed.append(row['course_id'])
            if apply:
                conn.execute('''UPDATE public.courses SET duration_seconds=%s,duration_kind=%s,
                    estimated_duration_seconds=%s,duration_provenance=%s WHERE course_id=%s''',
                    (values['duration_seconds'],values['duration_kind'],values['estimated_duration_seconds'],
                     Jsonb(values['duration_provenance']),row['course_id']))
    return {'course_count':len(rows),'counts':dict(counts),'changed_count':len(changed),'applied':apply,
            'embedding_api_called':False,'vector_inputs_changed':False}
