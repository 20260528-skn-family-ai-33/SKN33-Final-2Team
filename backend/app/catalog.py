"""학습 자료 목록 (팀 DB 강좌·도서·자격증 + 보조 스키마 resource_meta).

화면·에이전트는 자료를 '자료 키'로 부른다: 강좌 = course_id(예: MS_c5522b7d6d49), 도서 = book_<ISBN>, 자격 = cert_<cert_id>, 공식 문서 = doc_<id>.
팀 DB에 없는 학습 시간·형식·단계·비용은 resource_meta 에 규칙으로 채운 '추정' 값이 있고(estimated_fields), 관리자 엑셀로 고칠 수 있다.
자료가 수천 건이라 화면에는 쓰는 자료만 보내고(resources_for), 목록은 검색·쪽 나누기로 준다(search).
"""
from __future__ import annotations

import re
import threading
import time

from . import db, course_time, catalog_evidence

KIND = {'course': '강좌', 'book': '도서', 'cert': '자격', 'doc': '공식 문서'}
_lock = threading.Lock()
_cache: dict = {'at': 0.0, 'items': {}, 'skills': {}}
TTL_S = 120


def _date(v) -> str:
    return v.strftime('%Y-%m-%d') if v else ''


def _load() -> dict:
    items: dict[str, dict] = {}
    skills = {r['skill_id']: r['name'] for r in db.all_('SELECT skill_id, name FROM public.skill_tags')}
    links: dict[tuple, list] = {}
    for r in db.all_("""SELECT 'course' AS t, course_id AS k, skill_id FROM public.course_skills
                       UNION ALL SELECT 'book', isbn, skill_id FROM public.book_skills
                       UNION ALL SELECT 'cert', cert_id::text, skill_id FROM public.certification_skills"""):
        links.setdefault((r['t'], r['k']), []).append(skills.get(r['skill_id'], ''))
    meta = {r['resource_key']: r for r in db.all_('SELECT * FROM app_ext.resource_meta')}
    rows = db.all_("""SELECT m.resource_key, m.resource_type, c.course_id, c.title AS c_title, c.org_name, c.platform, c.url AS c_url, c.cost AS c_cost,
            c.duration_weeks, c.duration_seconds,c.duration_kind,c.estimated_duration_seconds,c.duration_provenance,
            c.difficulty, c.syllabus_summary, c.curriculum, c.content_status AS c_status, c.source_url AS c_src, c.source_verified_at AS c_ver, c.last_batch_updated AS c_upd,
            c.image_url AS c_img,
            b.isbn, b.title AS b_title, b.author, b.publisher, b.description AS b_desc, b.content_status AS b_status, b.source_url AS b_src, b.loan_count,
            b.source_verified_at AS b_ver, b.last_batch_updated AS b_upd, b.image_url AS b_img,
            x.cert_id, x.title AS x_title, x.provider AS x_provider, x.test_subjects, x.exam_type, x.pass_score, x.content_status AS x_status, x.source_url AS x_src,
            x.source_verified_at AS x_ver, x.last_batch_updated AS x_upd, x.image_url AS x_img,
            d.doc_id, d.title AS d_title, d.provider AS d_provider, d.url AS d_url, d.description AS d_desc, d.source_verified_at AS d_ver
        FROM app_ext.resource_meta m
        LEFT JOIN public.courses c ON c.course_id = m.course_id
        LEFT JOIN public.books b ON b.isbn = m.isbn
        LEFT JOIN public.certifications x ON x.cert_id = m.cert_id
        LEFT JOIN app_ext.learning_docs d ON d.doc_id = m.doc_id""")
    for r in rows:
        m = meta[r['resource_key']]
        t = r['resource_type']
        if t == 'course':
            title, provider, url, status = r['c_title'], r['org_name'] or r['platform'], r['c_url'] or r['c_src'], r['c_status']
            content = r['syllabus_summary'] or ''
            source = f"{r['platform']} 공개 강좌" if r['platform'] else '강좌'
            checked = _date(r['c_ver'] or r['c_upd'])
            sk = links.get(('course', r['course_id']), [])
            extra = {'platform': r['platform'], 'difficulty': r['difficulty'], 'weeks': r['duration_weeks'],
                     'curriculum': {key: (r['curriculum'] or {}).get(key) for key in ('coverage', 'items', 'item_count', 'source_url')}}
        elif t == 'book':
            title, provider, url, status = r['b_title'], r['publisher'], r['b_src'], r['b_status']
            content = r['b_desc'] or (f"저자 {r['author']}" if r['author'] else '')
            source, checked = '도서관 정보나루 도서', _date(r['b_ver'] or r['b_upd'])
            sk = links.get(('book', r['isbn']), [])
            extra = {'author': r['author'], 'loans': r['loan_count']}
        elif t == 'cert':
            title, provider, url, status = r['x_title'], r['x_provider'], r['x_src'], r['x_status']
            content = r['test_subjects'] or ''
            source, checked = '자격 공식 정보', _date(r['x_ver'] or r['x_upd'])
            sk = links.get(('cert', str(r['cert_id'])), [])
            extra = {'examType': r['exam_type'], 'passScore': r['pass_score']}
        else:
            title, provider, url, status = r['d_title'], r['d_provider'], r['d_url'], 'ready'
            content, source, checked = r['d_desc'] or '', '공식 문서', _date(r['d_ver'])
            sk = list(m['skill_keys'] or [])
            extra = {}
        if not title:
            continue  # 원본 행이 지워졌으면 목록에서 뺀다
        image = _image(r.get({'course': 'c_img', 'book': 'b_img', 'cert': 'x_img'}.get(t, '')))
        est = list(m['estimated_fields'] or [])
        timing = course_time.effective(r, m) if t == 'course' else {}
        if timing:est = timing['estimated']
        items[r['resource_key']] = dict({
            'id': r['resource_key'], 'type': t, 'title': title, 'provider': provider or '', 'kind': KIND[t],
            'format': m['format'] or '', 'hours': float(m['hours']) if m['hours'] is not None else None,
            'cost': m['cost_won'], 'stage': m['stage'], 'real': bool(m['is_real']), 'skills': [s for s in sk if s],
            'audience': m['audience'] or '', 'prereq': m['prereq'] or '', 'content': catalog_evidence.content_text(m['content'] or content),
            'note': m['note'] or ('단계·형식 등은 규칙으로 정한 계획값이에요' if {'format', 'stage'} & set(est) else ''),
            'url': url or '', 'image': image, 'source': m['source_label'] or source, 'checked': _date(m['checked_on']) or checked,
            'estimated': est, 'status': status or '', 'usable': _usable(t, status, sk),
            'certCode': m['cert_code'], 'certGroup': m['cert_group'], 'certShort': m['cert_short'], 'certSub': m['cert_sub'],
            'certVendor': m['cert_vendor'], 'order': m['display_order'],
        }, **extra, **timing)
    return {'items': items, 'skills': skills}


def _image(v: str | None) -> str:
    """표지·썸네일·배지 주소(팀 DB image_url). 화면에서 <img src>로 바로 쓰므로 http(s) 주소만 내보낸다(2026-10-22 사용자 결정: 원본 주소에서 바로 불러옴)"""
    v = (v or '').strip()
    return v if re.match(r'https?://', v, re.I) else ''


def _usable(t: str, status: str | None, skills: list) -> bool:
    """추천에 쓰는 자료: 강좌 ready·상태 없음, 도서 IT 스킬 연결, 자격 진행 중(폐지·폐지 예정·상태 미확인 제외 · 사용자 결정)"""
    if t == 'course':
        return status in (None, '', 'ready')
    if t == 'book':
        return status in (None, '', 'ready') and bool(skills)
    if t == 'cert':
        return status == 'ready'
    return True


def items(refresh: bool = False) -> dict[str, dict]:
    with _lock:
        if refresh or time.time() - _cache['at'] > TTL_S:
            _cache.update(_load(), at=time.time())
        return _cache['items']


def skill_names() -> list[str]:
    """팀 DB 스킬 태그 이름(skill_tags · 번호 순). 로드맵 에이전트가 직접 수행 과제의 스킬을 이 목록에서 고른다(10/23)"""
    items()
    return [n for _, n in sorted(_cache['skills'].items())]


def invalidate() -> None:
    with _lock:
        _cache['at'] = 0.0


def get(key: str | None) -> dict | None:
    return items().get(key or '') if key else None


def resources_for(keys, *, detail: bool = False) -> dict[str, dict]:
    """화면에 보낼 자료(쓰인 키만)"""
    all_ = items()
    return {k: _public(all_[k], detail=detail) for k in set(k for k in keys if k) if k in all_}


def _public(r: dict, *, detail: bool = False) -> dict:
    out = {k: r.get(k) for k in ('id', 'title', 'provider', 'kind', 'format', 'hours', 'cost', 'stage', 'real', 'skills', 'audience', 'prereq',
                                  'content', 'note', 'url', 'image', 'type', 'source', 'checked', 'estimated', 'certCode', 'platform', 'difficulty', 'weeks', 'author',
                                  'timeStatus','durationKind','durationSeconds','timeNote','curriculum')}
    out['detailsLoaded'] = detail
    if not detail:
        out['content'] = str(r.get('content') or '')[:400]
        if r.get('curriculum'):
            out['curriculum'] = {k: r['curriculum'].get(k) for k in ('coverage', 'item_count')}
    return out


def _word_re(w: str) -> re.Pattern:
    # 영문·숫자 검색어는 단어 앞머리에서만 찾는다('rag'가 'storage'에 걸리지 않게). 한글은 그대로 포함 여부
    return re.compile(rf'(?<![a-z0-9]){re.escape(w)}' if re.fullmatch(r'[a-z0-9.+#-]+', w) else re.escape(w))


def search(kind: str = '', q: str = '', stage_min: int = 0, exclude: list | None = None, limit: int = 30, offset: int = 0,
           include_certs: bool = True) -> dict:
    """학습 자료 목록·고르기 창 (API-53). 추천에 쓰는 자료만, 검색어는 제목·제공처·스킬에서 찾는다.
    검색어가 있으면 제목에 맞는 자료를 먼저 보여 주고, 제목·제공처·종류가 같은 중복 행(팀 DB에 언어별로 따로 있는 모듈 등)은 하나만 보여 준다"""
    ex = set(exclude or [])
    words = [_word_re(w) for w in re.split(r'\s+', (q or '').strip().lower()) if w]
    out = []
    for r in items().values():
        if not r['usable'] or r['id'] in ex or (kind and r['kind'] != kind) or (not include_certs and r['type'] == 'cert'):
            continue
        if stage_min and (r['stage'] or 2) < stage_min:
            continue
        score = 0
        if words:
            title, other = r['title'].lower(), f"{r['provider']} {' '.join(r['skills'])}".lower()
            hits = [(3 if w.search(title) else 1 if w.search(other) else 0) for w in words]
            if not all(hits):
                continue
            score = sum(hits)
        out.append((score, r))
    # 검색 점수 → 강좌·공식 문서 → 도서 → 자격, 같은 종류 안에서는 쉬운 단계·대출 많은 도서·제목 순
    order = {'course': 0, 'doc': 0, 'book': 1, 'cert': 2}
    out.sort(key=lambda x: (-x[0], order[x[1]['type']], x[1]['stage'] or 2, -(x[1].get('loans') or 0), x[1]['title']))
    seen, uniq = set(), []
    for _, r in out:
        k = (r['title'].strip().lower(), r['provider'], r['kind'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return {'total': len(uniq), 'items': [_public(r) for r in uniq[offset:offset + limit]]}


# ── 에이전트에게 넘길 자료 목록 ──
# 자료가 수천 건이라 목표·진단 내용과 관련된 스킬로 먼저 고른다(팀 DB 스킬 태그·연결표 사용). 임베딩 검색은 OpenAI 모드에서만
# 가능해(팀 DB 자료 벡터가 text-embedding-3-small) 5차는 스킬 규칙으로 고른다.
SKILL_RULES = [
    (r'RAG|검색|질의응답|챗봇|문서|지식|근거|규정', ['RAG & 생성형 AI 에이전트', '자연어 처리(NLP) & LLM 기초']),
    (r'LLM|생성형|GPT|프롬프트|언어 ?모델|에이전트|AI 활용|인공지능|AI', ['자연어 처리(NLP) & LLM 기초', 'RAG & 생성형 AI 에이전트']),
    (r'Python|파이썬|스크립트|자동화|코드', ['Python 프로그래밍 & 비동기 I/O']),
    (r'데이터|분석|지표|이상값|통계|시각화|pandas|예측', ['탐색적 데이터 분석(EDA) & 전처리', '머신러닝 지도/비지도 학습']),
    (r'SQL|DB|데이터베이스|쿼리', ['SQL 기본 문법 & 조인', 'RDBMS 데이터 모델링']),
    (r'API|백엔드|서비스|서버|FastAPI|Django|웹', ['RESTful API 서버 아키텍처', '웹 프레임워크 (FastAPI/Django)']),
    (r'운영|배포|로그|장애|모니터링|Docker|컨테이너', ['Docker 컨테이너 가상화', 'CI/CD 배포 자동화 파이프라인', '리눅스 환경 및 Bash 스크립팅']),
    (r'클라우드|AWS|Azure', ['클라우드 컴퓨팅 아키텍처 (AWS/Azure)']),
    (r'보안|개인정보|인젝션|취약', ['데이터 거버넌스 & 보안 규정 준수', '웹 애플리케이션 취약점 진단']),
    (r'MLOps|모델 서빙|파인튜닝|학습', ['MLOps & 모델 서빙', '딥러닝 신경망 아키텍처']),
]
BASE_SKILLS = ['자연어 처리(NLP) & LLM 기초', 'RAG & 생성형 AI 에이전트', 'Python 프로그래밍 & 비동기 I/O']


def skills_for(texts: list[str]) -> list[str]:
    hay = ' '.join(t for t in texts if t)
    out: list[str] = []
    for pat, names in SKILL_RULES:
        if re.search(pat, hay, re.I):
            out += [n for n in names if n not in out]
    return out or list(BASE_SKILLS)


def for_agent(texts: list[str], cert_key: str | None = None, limit: int = 28, start_stage: int = 1, *, free_only: bool = False) -> list[dict]:
    """관련 스킬 자료를 단계·종류가 고르게 섞이도록 고른다. 자격은 사용자가 고른 것만"""
    want = skills_for(texts)
    pool = [r for r in items().values() if r['usable'] and r['type'] != 'cert' and set(r['skills']) & set(want) and (not free_only or r.get('type') == 'book' or r.get('cost') == 0)]
    hay = ' '.join(t for t in texts if t).lower()
    words = {w for w in re.findall(r'[A-Za-z]{3,}|[가-힣]{2,}', hay)}

    def score(r: dict) -> float:
        s = len(set(r['skills']) & set(want)) * 2
        title = r['title'].lower()
        s += sum(1 for w in words if w.lower() in title)
        outline = ' '.join(f"{row.get('section', '')} {row.get('title', '')} {row.get('description', '')}" for row in (r.get('curriculum') or {}).get('items') or []).lower()
        s += min(3, sum(0.5 for w in words if w.lower() in outline))
        s -= 0.5 * max(0, (r['stage'] or 2) - 3)
        if r['type'] == 'book':
            s -= 1  # 도서는 강좌보다 뒤에(시간 추정이 거칠어서)
        return s

    pool.sort(key=lambda r: (-score(r), r['stage'] or 2, r['title']))
    picked, books = [], 0
    for r in pool:
        if r['type'] == 'book':
            if books >= 4:
                continue
            books += 1
        picked.append(r)
        if len(picked) >= limit:
            break
    cert = get(cert_key) if cert_key else None
    if cert and (not free_only or cert.get('cost') == 0):
        picked.append(cert)
    return picked


def agent_view(r: dict, skill_names: bool = True, texts: list[str] | None = None) -> dict:
    """Keep original keys and add bounded, goal-relevant source evidence."""
    return {**catalog_evidence.entry(r, skill_names=skill_names),
            **catalog_evidence.evidence(r, texts)}


def agent_views(records: list[dict], texts: list[str] | None = None) -> list[dict]:
    return catalog_evidence.pack(records, texts)


def cert_groups() -> list[dict]:
    """세부 사항의 자격증 고르기(API-22): 분야 → 자격. 폐지·폐지 예정·상태 미확인은 뺀다(사용자 결정)"""
    groups = db.all_('SELECT group_key, label, issuer, url FROM app_ext.cert_groups ORDER BY display_order, label')
    certs = [r for r in items().values() if r['type'] == 'cert' and r['usable'] and r['certGroup']]
    out = []
    for g in groups:
        list_ = sorted((c for c in certs if c['certGroup'] == g['group_key']), key=lambda c: (c['order'], c['title']))
        if list_:
            out.append({'key': g['group_key'], 'label': g['label'], 'issuer': g['issuer'], 'url': g['url'],
                        'certs': [{'id': c['certCode'], 'res': c['id'], 'short': c['certShort'] or c['title'], 'sub': c['certSub'] or '',
                                   'name': c['title'], 'issuer': c['provider'], 'vendor': c['certVendor'], 'hours': c['hours'], 'url': c['url'],
                                   'image': c['image']} for c in list_]})
    return out


def cert_by_code(code: str | None) -> dict | None:
    if not code:
        return None
    for r in items().values():
        if r['type'] == 'cert' and r['certCode'] == str(code):
            return r
    return None
