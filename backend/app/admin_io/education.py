"""교육 데이터: 강좌 · 도서 · 자격증 (팀 DB courses·books·certifications + 보조 표 resource_meta).

- 팀 DB에 없는 학습 형식·시간·단계·비용은 resource_meta 에 규칙으로 채운 '추정' 값이다(2026-10-21 사용자 결정). 관리자가 값을 고치면
  그 항목은 '추정'에서 빠진다. '추정 항목' 열을 직접 비워 확인한 값으로 둘 수도 있다.
- 스킬은 팀 DB 스킬 태그 이름으로 적는다(세미콜론으로 구분). 추천 자료 고르기와 검색에 쓴다.
- '삭제' Y: 로드맵이나 직원 보유 자격에서 쓰는 중이면 지우지 않고 목록에서만 뺀다(상태 deleted). 쓰지 않으면 지운다.
"""
from __future__ import annotations

import re

from .. import catalog, db
from .base import Col, Row, Sheet, merged

NAME, TITLE = 'education', '교육 데이터'
EST = {'format': '형식', 'hours': '시간', 'stage': '단계', 'cost': '비용'}
EST_IN = {v: k for k, v in EST.items()}
DIFF = {'BEGINNER': '초급', 'INTERMEDIATE': '중급', 'ADVANCED': '고급'}
DIFF_IN = {v: k for k, v in DIFF.items()}
CERT_ST = {'ready': '진행', 'retiring': '폐지 예정', 'retired': '폐지', 'needs_enrichment': '정보 보강 필요', 'availability_needs_review': '시행 여부 확인 필요',
           'excluded': '추천 제외', 'deleted': '삭제됨'}
CERT_ST_IN = {v: k for k, v in CERT_ST.items()}


def _image_col() -> Col:
    # 팀 DB image_url. 화면이 원본 주소에서 바로 불러온다(2026-10-22 사용자 결정)
    return Col('이미지 URL', 'image', help='표지·썸네일·배지 그림 주소(http:// 또는 https://). 비우면 화면에 종류 아이콘이 보여요', width=30)


def _meta_cols() -> list:
    return [
        Col('학습 형식', 'format', example='영상 · 문서 · 실습 · 시험', width=10),
        Col('학습 시간', 'hours', 'num', help='시간 단위. 로드맵 기간 계산에 써요', example='14', width=9),
        Col('단계', 'stage', 'int', help='1 기초 다지기 · 2 핵심 이해 · 3 업무 적용 · 4 성과 확인', example='2', width=6),
        Col('비용(원)', 'cost', 'int', help='무료는 0. 모르면 비워요(화면에 ‘비용 확인 필요’로 보여요)', width=10),
        Col('추정 항목', 'estimated', 'list', help='규칙으로 채운 값(형식·시간·단계·비용). 값을 고치면 그 항목은 자동으로 빠져요. 확인했으면 지워도 돼요', example='시간; 단계', width=12),
        Col('대상', 'audience', width=14),
        Col('선수지식', 'prereq', width=14),
        Col('비고', 'note', width=16),
        Col('스킬', 'skills', 'list', help='팀 DB 스킬 태그 이름(안내 시트 아래 목록)을 세미콜론(;)으로 구분해 적어요', example='RAG & 생성형 AI 에이전트', width=28),
    ]


COURSE = Sheet('강좌', ('key',), [
    Col('자료 키', 'key', required=True, help='강좌를 찾는 열쇠(팀 DB course_id). 새 강좌는 겹치지 않는 키를 적어요', example='ADM_0001', width=16),
    Col('제목', 'title', required=True, width=36),
    Col('플랫폼', 'platform', required=True, example='MS Learn · K-MOOC', width=10),
    Col('제공 기관', 'org', width=16),
    Col('URL', 'url', width=30),
    _image_col(),
    Col('난이도', 'difficulty', 'choice', choices=tuple(DIFF.values())),
    Col('기간(주)', 'weeks', 'int', width=8),
    Col('내용 요약', 'summary', width=36),
    Col('추천 사용', 'use', 'bool', help='N이면 로드맵 추천·학습 자료 목록에서 빼요. 비우면 Y', width=8, default=True),
] + _meta_cols(), help='MS Learn·K-MOOC 등 강좌')

BOOK = Sheet('도서', ('key',), [
    Col('ISBN', 'key', required=True, help='도서를 찾는 열쇠(10자리 또는 13자리)', example='9791158396220', width=15),
    Col('제목', 'title', required=True, width=36),
    Col('저자', 'author', width=16),
    Col('출판사', 'publisher', width=14),
    Col('설명', 'description', width=30),
    Col('URL', 'url', width=26),
    _image_col(),
    Col('대출 건수', 'loans', 'int', readonly=True, width=8),
    Col('추천 사용', 'use', 'bool', help='N이면 추천에서 빼요. 스킬이 하나도 없는 도서도 추천에 쓰지 않아요. 비우면 Y', width=8, default=True),
] + _meta_cols(), help='도서관 정보나루 도서')

CERT = Sheet('자격증', ('key',), [
    Col('자격 ID', 'key', 'int', help='자격증을 찾는 열쇠(팀 DB cert_id). 새 자격증은 비워 두면 번호가 정해져요', width=8),
    Col('자격 이름', 'title', required=True, width=34),
    Col('시행 기관', 'provider', width=16),
    Col('상태', 'status', 'choice', choices=tuple(CERT_ST.values())[:-1], help='진행인 자격증만 자격증 계획 목록과 추천에 나와요. 비우면 진행', width=12, default='진행'),
    Col('분야 키', 'group', help='자격증 계획 목록의 분야(안내 시트 아래 목록). 비우면 목록에 나오지 않아요', example='ms-ai', width=10),
    Col('짧은 이름', 'short', width=20),
    Col('세부', 'sub', width=12),
    Col('벤더 묶음', 'vendor', width=12),
    Col('시험 과목', 'subjects', width=24),
    Col('시험 방식', 'exam_type', width=10),
    Col('합격 점수', 'pass_score', 'int', width=8),
    Col('URL', 'url', width=26),
    _image_col(),
    Col('응시료(원)', 'cost', 'int', help='모르면 비워요(‘응시료 확인 필요’)', width=10),
    Col('학습 형식', 'format', width=8),
    Col('학습 시간', 'hours', 'num', width=8),
    Col('단계', 'stage', 'int', width=6),
    Col('추정 항목', 'estimated', 'list', width=12),
    Col('스킬', 'skills', 'list', width=28),
], help='자격증. 폐지·폐지 예정·상태 미확인 자격은 추천에 쓰지 않아요', auto_key=True)

SHEETS = [COURSE, BOOK, CERT]


def guide() -> list[str]:
    skills = [r['name'] for r in db.all_('SELECT name FROM public.skill_tags ORDER BY skill_id')]
    groups = [f"{r['group_key']}({r['label']})" for r in db.all_('SELECT group_key, label FROM app_ext.cert_groups ORDER BY display_order, group_key')]
    return [
        '교육 데이터(강좌·도서·자격증)를 엑셀로 내려받아 고친 뒤 다시 올려요. 올리면 먼저 미리보기를 보여 주고, 오류가 없을 때만 ‘반영’할 수 있어요.',
        '· 파일에 없는 행은 그대로 둬요. 지우려면 ‘삭제’ 열에 Y를 적어요(로드맵에서 쓰는 중인 자료는 목록에서만 빼요).',
        '· 파일에 없는 열은 바꾸지 않아요. 있는 열의 빈 칸은 값을 비워요. 회색 머리글 열은 참고용이에요.',
        '· 학습 형식·시간·단계·비용은 팀 DB에 없어 규칙으로 채운 추정값이 들어 있어요. 고치면 ‘추정’ 표시가 빠져요.',
        '· 도서는 4천 건 가까이 돼요. 고칠 행만 남기고 나머지 행을 지운 파일을 올려도 돼요(없는 행은 그대로).',
        '스킬 이름: ' + ' / '.join(skills),
        '자격증 분야 키: ' + ' / '.join(groups),
    ]


GUIDE: list[str] = []   # 내려받을 때 guide() 로 채운다(스킬 목록이 DB에 있음)


def _skills(kind: str) -> dict[str, list[str]]:
    sql = {'course': 'SELECT x.course_id AS k, s.name FROM public.course_skills x JOIN public.skill_tags s USING (skill_id) ORDER BY s.skill_id',
           'book': 'SELECT x.isbn AS k, s.name FROM public.book_skills x JOIN public.skill_tags s USING (skill_id) ORDER BY s.skill_id',
           'cert': 'SELECT x.cert_id::text AS k, s.name FROM public.certification_skills x JOIN public.skill_tags s USING (skill_id) ORDER BY s.skill_id'}[kind]
    out: dict[str, list[str]] = {}
    for r in db.all_(sql):
        out.setdefault(r['k'], []).append(r['name'])
    return out


def _meta(m: dict) -> dict:
    return {'format': m['format'], 'hours': float(m['hours']) if m['hours'] is not None else None, 'stage': m['stage'], 'cost': m['cost_won'],
            'estimated': [EST[f] for f in (m['estimated_fields'] or []) if f in EST], 'audience': m['audience'], 'prereq': m['prereq'], 'note': m['note'],
            '_est': list(m['estimated_fields'] or [])}


def current(sheet: str) -> dict:
    if sheet == '강좌':
        sk = _skills('course')
        rows = db.all_("""SELECT c.*, m.format, m.hours, m.stage, m.cost_won, m.estimated_fields, m.audience, m.prereq, m.note FROM app_ext.resource_meta m
                          JOIN public.courses c ON c.course_id = m.course_id ORDER BY c.platform, c.title""")
        return {(r['course_id'],): dict({'key': r['course_id'], 'title': r['title'], 'platform': r['platform'], 'org': r['org_name'], 'url': r['url'],
                                          'image': r['image_url'], 'difficulty': DIFF.get(r['difficulty'] or ''), 'weeks': r['duration_weeks'], 'summary': r['syllabus_summary'],
                                          'use': r['content_status'] in (None, '', 'ready'), 'skills': sk.get(r['course_id'], []), '_status': r['content_status']},
                                         **_meta(r)) for r in rows}
    if sheet == '도서':
        sk = _skills('book')
        rows = db.all_("""SELECT b.*, m.format, m.hours, m.stage, m.cost_won, m.estimated_fields, m.audience, m.prereq, m.note FROM app_ext.resource_meta m
                          JOIN public.books b ON b.isbn = m.isbn ORDER BY b.loan_count DESC NULLS LAST, b.title""")
        return {(r['isbn'],): dict({'key': r['isbn'], 'title': r['title'], 'author': r['author'], 'publisher': r['publisher'], 'description': r['description'],
                                     'url': r['source_url'], 'image': r['image_url'], 'loans': r['loan_count'], 'use': r['content_status'] in (None, '', 'ready'), 'skills': sk.get(r['isbn'], []),
                                     '_status': r['content_status']}, **_meta(r)) for r in rows}
    if sheet == '자격증':
        sk = _skills('cert')
        rows = db.all_("""SELECT x.*, m.format, m.hours, m.stage, m.cost_won, m.estimated_fields, m.audience, m.prereq, m.note, m.cert_group, m.cert_short, m.cert_sub, m.cert_vendor
                          FROM app_ext.resource_meta m JOIN public.certifications x ON x.cert_id = m.cert_id ORDER BY m.cert_group NULLS LAST, x.cert_id""")
        return {(r['cert_id'],): dict({'key': r['cert_id'], 'title': r['title'], 'provider': r['provider'], 'status': CERT_ST.get(r['content_status'] or '', r['content_status']),
                                        'group': r['cert_group'], 'short': r['cert_short'], 'sub': r['cert_sub'], 'vendor': r['cert_vendor'], 'subjects': r['test_subjects'],
                                        'exam_type': r['exam_type'], 'pass_score': r['pass_score'], 'url': r['source_url'], 'image': r['image_url'], 'skills': sk.get(str(r['cert_id']), []),
                                        '_status': r['content_status']}, **_meta(r)) for r in rows}
    return {}


def options(sheet: str) -> dict:
    """화면에서 고칠 때의 고르기 목록(hr.options 와 같은 모양). 목록 칸(스킬·추정 항목)은 여러 개를 고른다"""
    out = {'skills': {'strict': True, 'items': [{'value': r['name']} for r in db.all_('SELECT name FROM public.skill_tags ORDER BY skill_id')]},
           'estimated': {'strict': True, 'items': [{'value': v} for v in EST.values()]},
           'format': {'items': [{'value': r['format']} for r in db.all_('SELECT DISTINCT format FROM app_ext.resource_meta WHERE format IS NOT NULL ORDER BY 1')]}}
    if sheet == '강좌':
        out['platform'] = {'items': [{'value': r['platform']} for r in db.all_('SELECT DISTINCT platform FROM public.courses WHERE platform IS NOT NULL ORDER BY 1')]}
    if sheet == '자격증':
        out['group'] = {'strict': True, 'items': [{'value': r['group_key'], 'label': r['label']} for r in db.all_('SELECT group_key, label FROM app_ext.cert_groups ORDER BY display_order, group_key')]}
    return out


def label(sheet: str, v: dict) -> str:
    return v.get('title') or ''


def _in_use(sheet: str, key) -> bool:
    if sheet == '강좌':
        return bool(db.val('SELECT 1 FROM public.roadmap_step_resources WHERE course_id = :k LIMIT 1', k=key))
    if sheet == '도서':
        return bool(db.val('SELECT 1 FROM public.roadmap_step_resources WHERE isbn = :k LIMIT 1', k=key))
    return bool(db.val('SELECT 1 FROM public.roadmap_step_resources WHERE certification_id = :k UNION ALL SELECT 1 FROM public.employee_certifications WHERE certification_id = :k LIMIT 1', k=key))


def check(found: dict[str, list[Row]], cur: dict[str, dict]) -> None:
    skills = {r['name'] for r in db.all_('SELECT name FROM public.skill_tags')}
    groups = {r['group_key'] for r in db.all_('SELECT group_key FROM app_ext.cert_groups')}
    for name, rows in found.items():
        for r in rows:
            if r.action == 'delete':
                if _in_use(name, r.key[0]):
                    r.tags.append('목록에서만 빼기')
                    r.warn('로드맵이나 직원 보유 자격에서 쓰는 중이라 지우지 않고 목록·추천에서만 빼요')
                else:
                    r.tags.append('지우기')
                continue
            if r.action not in ('add', 'update'):
                continue
            v = r.values
            bad = [s for s in v.get('skills') or [] if s not in skills] if 'skills' in r.present else []
            if bad:
                r.err('스킬', f"스킬 태그에 없는 이름이에요: {', '.join(bad)} (안내 시트의 스킬 이름으로 적어 주세요)")
            if v.get('stage') is not None and not 1 <= v['stage'] <= 4:
                r.err('단계', '1~4 중 하나로 적어 주세요')
            if v.get('hours') is not None and not 0 < v['hours'] <= 500:
                r.err('학습 시간', '0보다 크고 500 이하로 적어 주세요')
            if v.get('cost') is not None and v['cost'] < 0:
                r.err(CERT.col('cost').header if name == '자격증' else '비용(원)', '0 이상으로 적어 주세요')
            bad_est = [x for x in v.get('estimated') or [] if x not in EST_IN] if 'estimated' in r.present else []
            if bad_est:
                r.err('추정 항목', f"형식·시간·단계·비용 중에서 적어 주세요({', '.join(bad_est)})")
            if v.get('image') and not re.match(r'https?://\S+$', str(v['image']).strip(), re.I):
                r.err('이미지 URL', 'http:// 또는 https:// 로 시작하는 그림 주소로 적어 주세요')
            if name == '도서' and r.action == 'add' and not re.fullmatch(r'\d{9}[\dXx]|\d{13}', str(r.key[0] or '')):
                r.err('ISBN', '10자리 또는 13자리 ISBN으로 적어 주세요')
            if name == '자격증' and 'group' in r.present and v.get('group') and v['group'] not in groups:
                r.err('분야 키', f"‘{v['group']}’ 분야가 없어요(안내 시트의 분야 키로 적어 주세요)")
            final = merged(r, cur[name].get(r.key))
            if name == '자격증' and not final.get('group'):
                r.warn('분야 키가 없어 자격증 계획 목록에 나오지 않아요')
            if name == '도서' and final.get('use') and not final.get('skills'):
                r.warn('스킬이 없어 추천에는 쓰지 않아요')
            changed_est = [c['field'] for c in r.changes if c.get('field') in EST]
            if changed_est and r.action == 'update':
                left = [EST[f] for f in changed_est if f in (cur[name].get(r.key) or {}).get('_est', [])]
                if left:
                    r.tags.append('추정 해제: ' + ', '.join(left))


def _est_of(r: Row, old: dict | None, v: dict) -> list[str]:
    """추정 항목: 파일 값(없으면 지금 값)에서, 이번에 값을 고친 항목은 뺀다"""
    est = [EST_IN[x] for x in v.get('estimated') or [] if x in EST_IN] if 'estimated' in r.present else list((old or {}).get('_est') or [])
    changed = {c['field'] for c in r.changes if c.get('field') in EST}
    return [f for f in est if f not in changed]


def _set_skills(t: db.Tx, table: str, col: str, key, names: list[str], ids: dict[str, int]) -> None:
    t.run(f'DELETE FROM public.{table} WHERE {col} = :k', k=key)
    for n in dict.fromkeys(names):
        t.run(f'INSERT INTO public.{table}({col}, skill_id) VALUES(:k, :s) ON CONFLICT DO NOTHING', k=key, s=ids[n])


def _img(v: dict) -> str | None:
    return str(v.get('image') or '').strip() or None


def _upsert_meta(t: db.Tx, rkey: str, rtype: str, fk_col: str, fk, v: dict, est: list[str], extra: dict | None = None) -> None:
    extra = extra or {}
    t.run(f"""INSERT INTO app_ext.resource_meta(resource_key, resource_type, {fk_col}, format, hours, stage, cost_won, estimated_fields, audience, prereq, note, is_real,
              cert_group, cert_short, cert_sub, cert_vendor, cert_code)
              VALUES(:k, :t, :fk, :f, :h, :s, :c, :e, :a, :p, :n, true, :g, :sh, :sb, :vd, :cc)
              ON CONFLICT (resource_key) DO UPDATE SET format = EXCLUDED.format, hours = EXCLUDED.hours, stage = EXCLUDED.stage, cost_won = EXCLUDED.cost_won,
                estimated_fields = EXCLUDED.estimated_fields, audience = EXCLUDED.audience, prereq = EXCLUDED.prereq, note = EXCLUDED.note,
                cert_group = EXCLUDED.cert_group, cert_short = EXCLUDED.cert_short, cert_sub = EXCLUDED.cert_sub, cert_vendor = EXCLUDED.cert_vendor""",
          k=rkey, t=rtype, fk=fk, f=v.get('format'), h=v.get('hours'), s=v.get('stage'), c=v.get('cost'), e=db.J(est), a=v.get('audience'), p=v.get('prereq'),
          n=v.get('note'), g=extra.get('group'), sh=extra.get('short'), sb=extra.get('sub'), vd=extra.get('vendor'), cc=extra.get('code'))


def apply(t: db.Tx, found: dict[str, list[Row]], cur: dict[str, dict], ctx: dict) -> dict:
    sid = {r['name']: r['skill_id'] for r in t.all('SELECT skill_id, name FROM public.skill_tags')}
    res = {n: {'add': 0, 'update': 0, 'delete': 0, 'hidden': 0} for n in ('강좌', '도서', '자격증')}
    for r in found.get('강좌', []):
        old = cur['강좌'].get(r.key)
        if r.action == 'delete':
            if _in_use('강좌', r.key[0]):
                t.run("UPDATE public.courses SET content_status = 'deleted' WHERE course_id = :k", k=r.key[0])
                res['강좌']['hidden'] += 1
            else:
                t.run('DELETE FROM public.courses WHERE course_id = :k', k=r.key[0])
                res['강좌']['delete'] += 1
            continue
        if r.action not in ('add', 'update'):
            continue
        v = merged(r, old)
        status = 'ready' if v.get('use', True) else 'excluded'
        if r.action == 'add':
            t.run("""INSERT INTO public.courses(course_id, title, platform, org_name, url, image_url, difficulty, duration_weeks, syllabus_summary, content_status, record_source, last_batch_updated)
                     VALUES(:k, :ti, :pl, :o, :u, :im, :d, :w, :s, :st, 'ADMIN_UPLOAD', now())""",
                  k=r.key[0], ti=v['title'], pl=v['platform'], o=v.get('org'), u=v.get('url'), im=_img(v), d=DIFF_IN.get(v.get('difficulty') or ''), w=v.get('weeks'), s=v.get('summary'), st=status)
        else:
            keep = old.get('_status') if v.get('use') and old.get('_status') in (None, '') else status
            t.run("""UPDATE public.courses SET title = :ti, platform = :pl, org_name = :o, url = :u, image_url = :im, difficulty = :d, duration_weeks = :w, syllabus_summary = :s,
                     content_status = :st, last_batch_updated = now() WHERE course_id = :k""",
                  k=r.key[0], ti=v['title'], pl=v['platform'], o=v.get('org'), u=v.get('url'), im=_img(v), d=DIFF_IN.get(v.get('difficulty') or ''), w=v.get('weeks'), s=v.get('summary'), st=keep)
        _upsert_meta(t, r.key[0], 'course', 'course_id', r.key[0], v, _est_of(r, old, v))
        if any(change.get('field') == 'hours' for change in r.changes) or (r.action == 'add' and v.get('hours') is not None):
            t.run("UPDATE app_ext.resource_meta SET hours_origin='manual' WHERE resource_key=:k", k=r.key[0])
        if 'skills' in r.present:
            _set_skills(t, 'course_skills', 'course_id', r.key[0], v.get('skills') or [], sid)
        res['강좌'][r.action] += 1
    for r in found.get('도서', []):
        old = cur['도서'].get(r.key)
        if r.action == 'delete':
            if _in_use('도서', r.key[0]):
                t.run("UPDATE public.books SET content_status = 'deleted' WHERE isbn = :k", k=r.key[0])
                res['도서']['hidden'] += 1
            else:
                t.run('DELETE FROM public.books WHERE isbn = :k', k=r.key[0])
                res['도서']['delete'] += 1
            continue
        if r.action not in ('add', 'update'):
            continue
        v = merged(r, old)
        status = 'ready' if v.get('use', True) else 'excluded'
        if r.action == 'add':
            t.run("""INSERT INTO public.books(isbn, title, author, publisher, description, source_url, image_url, content_status, record_source, last_batch_updated)
                     VALUES(:k, :ti, :au, :pu, :de, :u, :im, :st, 'ADMIN_UPLOAD', now())""",
                  k=r.key[0], ti=v['title'], au=v.get('author'), pu=v.get('publisher'), de=v.get('description'), u=v.get('url'), im=_img(v), st=status)
        else:
            keep = old.get('_status') if v.get('use') and old.get('_status') in (None, '') else status
            t.run("""UPDATE public.books SET title = :ti, author = :au, publisher = :pu, description = :de, source_url = :u, image_url = :im, content_status = :st,
                     last_batch_updated = now() WHERE isbn = :k""", k=r.key[0], ti=v['title'], au=v.get('author'), pu=v.get('publisher'), de=v.get('description'), u=v.get('url'),
                  im=_img(v), st=keep)
        _upsert_meta(t, f'book_{r.key[0]}', 'book', 'isbn', r.key[0], v, _est_of(r, old, v))
        if 'skills' in r.present:
            _set_skills(t, 'book_skills', 'isbn', r.key[0], v.get('skills') or [], sid)
        res['도서'][r.action] += 1
    for r in found.get('자격증', []):
        old = cur['자격증'].get(r.key) if r.key[0] is not None else None
        if r.action == 'delete':
            if _in_use('자격증', r.key[0]):
                t.run("UPDATE public.certifications SET content_status = 'deleted' WHERE cert_id = :k", k=r.key[0])
                res['자격증']['hidden'] += 1
            else:
                t.run('DELETE FROM public.certifications WHERE cert_id = :k', k=r.key[0])
                res['자격증']['delete'] += 1
            continue
        if r.action not in ('add', 'update'):
            continue
        v = merged(r, old)
        status = CERT_ST_IN.get(v.get('status') or '진행', 'ready')
        args = dict(ti=v['title'], pv=v.get('provider'), su=v.get('subjects'), ex=v.get('exam_type'), ps=v.get('pass_score'), u=v.get('url'), im=_img(v), st=status)
        if r.action == 'add' and r.key[0] is None:
            cid = t.val("""INSERT INTO public.certifications(title, provider, test_subjects, exam_type, pass_score, source_url, image_url, content_status, record_source, last_batch_updated)
                           VALUES(:ti, :pv, :su, :ex, :ps, :u, :im, :st, 'ADMIN_UPLOAD', now()) RETURNING cert_id""", **args)
        elif r.action == 'add':
            cid = t.val("""INSERT INTO public.certifications(cert_id, title, provider, test_subjects, exam_type, pass_score, source_url, image_url, content_status, record_source, last_batch_updated)
                           VALUES(:k, :ti, :pv, :su, :ex, :ps, :u, :im, :st, 'ADMIN_UPLOAD', now()) RETURNING cert_id""", k=r.key[0], **args)
            t.run("SELECT setval('certifications_cert_id_seq', greatest((SELECT max(cert_id) FROM public.certifications), 1))")
        else:
            cid = r.key[0]
            t.run("""UPDATE public.certifications SET title = :ti, provider = :pv, test_subjects = :su, exam_type = :ex, pass_score = :ps, source_url = :u, image_url = :im,
                     content_status = :st, last_batch_updated = now() WHERE cert_id = :k""", k=cid, **args)
        _upsert_meta(t, f'cert_{cid}', 'cert', 'cert_id', cid, v, _est_of(r, old, v),
                     {'group': v.get('group'), 'short': v.get('short') or v['title'], 'sub': v.get('sub'), 'vendor': v.get('vendor'), 'code': str(cid)})
        if 'skills' in r.present:
            _set_skills(t, 'certification_skills', 'cert_id', cid, v.get('skills') or [], sid)
        res['자격증'][r.action] += 1
    return res


def after(res: dict, ctx: dict) -> None:
    catalog.invalidate()
