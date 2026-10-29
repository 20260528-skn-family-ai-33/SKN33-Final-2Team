"""Portable public course outlines; never rewrite raw payloads or vector input text."""
from collections import Counter
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin

from psycopg.types.json import Jsonb

VERSION = 'public-course-outline/v2'


class _Markup(HTMLParser):
    """Read text, links and table cells without scripts, style or executing HTML."""
    def __init__(self):
        super().__init__()
        self.text, self.links, self.tables = [], [], []
        self.hidden = 0
        self.anchor = None
        self.table = self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.hidden += 1
        if self.hidden:
            return
        if tag in ('p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'section'):
            self.text.append('\n')
        if tag == 'a':
            self.anchor = [attrs, []]
        if tag == 'table' and self.table is None:
            self.table = []
        if tag == 'tr' and self.table is not None:
            self.row = []
        if tag in ('th', 'td') and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
            return
        if self.hidden:
            return
        if tag == 'a' and self.anchor:
            attrs, text = self.anchor
            self.links.append((attrs, ' '.join(''.join(text).split())))
            self.anchor = None
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.table.append(self.row)
            self.row = None
        if tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None
        if tag in ('p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'section'):
            self.text.append('\n')

    def handle_data(self, data):
        if self.hidden:
            return
        self.text.append(data)
        if self.anchor:
            self.anchor[1].append(data)
        if self.cell is not None:
            self.cell.append(data + ' ')


def plain(value):
    text = str(value or '')
    if re.search(r'</?(?:div|p|br|section|article|table|h[1-6]|span|script|style)\b', text, re.I):
        parser = _Markup()
        parser.feed(text)
        text = ''.join(parser.text)
    text = re.sub(r'^\s*id="course"\s+class="[^"]*">\s*', '', text)
    return '\n'.join(line for raw in unescape(text).splitlines() if (line := ' '.join(raw.split())))


def cached_markup(payload, root):
    relative, expected = payload.get('html_path'), payload.get('html_sha256')
    if not relative or not expected:
        return None
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Curriculum cache checksum mismatch')
    parser = _Markup()
    parser.feed(raw.decode('utf-8'))
    return parser


def repair_numbered_titles(value):
    """주차/차시만 제목인 항목은 같은 원문 행의 설명으로 표시하고 원래 값도 보존한다.

    복원본의 원문 해시와 목차를 이용하므로 수집 PC의 HTML 캐시가 필요하지 않다.
    내용을 추정하지 않으며 새 제목이 될 설명이 없으면 제목 미제공으로 구분한다.
    """
    if value.get('source') not in ('API_KMOOC', 'WEB_KOCW'):
        return value
    ordinal = re.compile(r'(?:WEEK\s*\d+|\d+\s*[-.]\s*\d+|\d+\s*(?:주차?|차시|강|회)?)', re.I)
    items, changed = [], False
    for item in value.get('items', []):
        title = str(item.get('title') or '').strip()
        parts = [part.strip() for part in str(item.get('description') or '').split(' / ')]
        index = next((i for i, part in enumerate(parts) if part and not ordinal.fullmatch(part)), None)
        if ordinal.fullmatch(title):
            item = dict(item, title=parts[index] if index is not None else '제목 미제공',
                        section=' / '.join(part for part in (item.get('section'), title) if part),
                        description=' / '.join(parts[:index] + parts[index + 1:]) if index is not None else item.get('description', ''),
                        original_title=item['title'], original_description=item.get('description', ''))
            if index is None:
                item['title_missing'] = True
            changed = True
        items.append(item)
    if not changed:
        return value
    coverage = value.get('coverage')
    if coverage == 'public_outline' and any(item.get('title_missing') for item in items):
        coverage = 'partial_outline'
    return dict(value, items=items, coverage=coverage, title_normalization_version='numbered-outline-title/v1')


def normalize(source, payload, description='', *, url=None, previous=None, source_root=None, supplement=None):
    payload = payload or {}
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    previous = previous or {}
    supplement_hash = hashlib.sha256(json.dumps(supplement, ensure_ascii=False, sort_keys=True).encode()).hexdigest() if supplement else None
    # A restored DB carries the outline, not a dependency on the collector PC's cache.
    if previous.get('version') == VERSION and previous.get('payload_sha256') == fingerprint and (not supplement or previous.get('supplement_input_sha256') == supplement_hash):
        return repair_numbered_titles(dict(previous, description=plain(description), description_sha256=hashlib.sha256(str(description or '').encode()).hexdigest()))
    root = source_root or Path(__file__).resolve().parents[2]
    items, coverage = [], 'description_only'

    def add(title, section='', description='', **extra):
        title = plain(title)
        if title:
            items.append(dict(title=title, section=plain(section), description=plain(description), **extra))

    if source in ('WEB_INFLEARN', 'WEB_KOCW'):
        for lesson in payload.get('lessons') or []:
            title = lesson.get('title') or '제목 미제공'
            if source == 'WEB_INFLEARN':
                add(title, lesson.get('section'), seconds=lesson.get('runtime') or None,
                    video=lesson.get('hasVideo') is True, title_missing=not bool(lesson.get('title')))
            else:
                add(title, lesson.get('chapter'), lesson.get('description'), title_missing=not bool(lesson.get('title')),
                    video=bool(lesson.get('video_listed')), suspended=bool(lesson.get('suspended_marker')))
        coverage = 'partial_outline' if any(item.get('title_missing') for item in items) else 'public_outline' if items else coverage
    elif source == 'WEB_OPENTUTORIALS':
        markup = cached_markup(payload, root)
        pattern = re.compile(r'/course/' + re.escape(str(payload.get('source_id'))) + r'/\d+(?:[/?#]|$)')
        seen = set()
        for attrs, title in markup.links if markup else []:
            href = attrs.get('href', '')
            if pattern.search(href) and 'depth_' in attrs.get('class', '') and href not in seen:
                seen.add(href)
                add(title, url=urljoin(payload.get('url') or '', href))
        coverage = 'public_outline' if items else coverage
        if not items:
            for lesson in payload.get('lessons') or []:
                add(lesson.get('title'), url=lesson.get('url'))
            coverage = 'sample' if items else coverage
    elif source == 'API_MS_LEARN':
        markup = cached_markup(supplement or payload, root)
        for attrs, title in markup.links if markup else []:
            if 'unit-title' in attrs.get('class', '').split():
                add(title, url=urljoin((url or payload.get('url') or '').rstrip('/') + '/', attrs.get('href', '')))
        # Collector summaries also retain all public unit titles. Never invent a title from a UID.
        if not items and '공개 단원' in str(description):
            for line in plain(description).split('공개 단원', 1)[1].splitlines():
                if line and not re.fullmatch(r'(?:\d+\s*)?(?:min|분)', line, re.I):
                    add(line)
        coverage = 'public_outline' if items and len(items) == len(payload.get('units') or []) else 'partial_outline' if items else coverage
    elif source == 'WEB_STEP':
        for title in (payload.get('public_detail') or {}).get('curriculum_titles') or []:
            add(title)
        coverage = 'public_outline' if items else coverage
    elif source == 'API_KMOOC':
        markup = cached_markup(supplement, root) if supplement else None
        if markup is None:
            markup = _Markup()
            markup.feed(str(payload.get('summary') or ''))
        for table in markup.tables:
            header = next((index for index, row in enumerate(table) if len(row) >= 2 and any(
                re.fullmatch(r'주차|차시|차시목차|목차|세부목차|강의주제|학습주제', re.sub(r'\s+', '', cell)) for cell in row)), None)
            if header is None:
                continue
            for row in table[header + 1:]:
                cells = [cell for cell in row if cell and not re.fullmatch(r'\d+(?:주|차시)?', cell)]
                if not cells or any(re.fullmatch(r'주차|차시목차|차시|목차|세부목차|학습활동', cell.replace(' ', '')) for cell in cells):
                    continue
                if re.fullmatch(r'교재및참고자료|평가기준|수강대상|교수자|이수기준', re.sub(r'\s+', '', cells[0])):
                    break
                add(cells[0], description=' / '.join(cells[1:]))
        if not items:
            for title in (payload.get('public_detail') or {}).get('curriculum_titles') or []:
                add(title)
        transcription = (supplement or {}).get('visual_transcription') or {}
        if not items and transcription:
            image = transcription['image']
            root_path = Path(root).resolve()
            path = (root_path / image['path']).resolve()
            if not path.is_relative_to(root_path) or hashlib.sha256(path.read_bytes()).hexdigest() != image['sha256']:
                raise ValueError('Curriculum image checksum mismatch')
            for row in transcription['items']:
                add(row['title'], row.get('section'), row.get('description'))
        coverage = 'public_outline' if items else coverage
    return repair_numbered_titles({'version': VERSION, 'source': source, 'source_url': url or payload.get('url'),
            'payload_sha256': fingerprint, 'html_sha256': payload.get('html_sha256') or (payload.get('public_detail') or {}).get('html_sha256'),
            'description': plain(description), 'description_sha256': hashlib.sha256(str(description or '').encode()).hexdigest(),
            'supplement_sha256': (supplement or {}).get('html_sha256'),
            'supplement_input_sha256': supplement_hash,
            'supplement_url': (supplement or {}).get('url'), 'supplement_fetched_at': (supplement or {}).get('fetched_at'),
            'visual_transcription': (supplement or {}).get('visual_transcription', {}).get('image'),
            'visual_transcription_method': (supplement or {}).get('visual_transcription', {}).get('method'),
            'visual_transcription_human_review': (supplement or {}).get('visual_transcription', {}).get('human_review'),
            'coverage': coverage, 'items': items,
            'item_count': len(items), 'expected_unit_count': len(payload.get('units') or []) or None})


def backfill(conn, *, apply=False, source_root=None, supplements=None):
    rows = conn.execute('''SELECT c.course_id,c.url,c.syllabus_summary,c.curriculum,s.source,s.payload
        FROM public.courses c LEFT JOIN LATERAL
        (SELECT source,payload FROM growpath_meta.catalog_api_sources WHERE resource_type='courses'
         AND entity_key=c.course_id ORDER BY fetched_at DESC,source,external_key LIMIT 1) s ON true
        ORDER BY c.course_id''').fetchall()
    counts, changed = Counter(), 0
    for row in rows:
        supplement = (supplements or {}).get(row['course_id'])
        if supplement and (supplement.get('error') or supplement.get('url') != row['url']):
            supplement = None
        value = normalize(row['source'], row['payload'], row['syllabus_summary'], url=row['url'],
                          previous=row['curriculum'], source_root=source_root, supplement=supplement)
        counts[value['coverage']] += 1
        if value != row['curriculum']:
            changed += 1
            if apply:
                conn.execute('UPDATE public.courses SET curriculum=%s WHERE course_id=%s', (Jsonb(value), row['course_id']))
    return {'courses': len(rows), 'changed_count': changed, 'coverage': dict(counts), 'applied': apply,
            'embedding_api_called': False, 'vector_inputs_changed': False}
