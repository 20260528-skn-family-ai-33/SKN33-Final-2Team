"""인적 데이터: 부서 · 직원(인사이동·부서장 권한 포함) · 근무성적평정 (2026-10-21 사용자 결정).

- 인사이동 = 직원 시트의 '부서 코드'를 고치면 된다. 반영할 때 이동 이력을 app_ext.employee_transfers 에 남긴다.
- 부서장 권한 부여·회수 = 직원 시트의 '부서장' Y/N. 한 부서에 부서장은 한 명(팀 DB 고유 색인)이라 미리보기에서 막는다.
- 직원은 지우지 않는다. '삭제' Y 는 퇴직 처리(재직 상태 퇴직 · 계정 중지 · 부서장 해제 · 로그인 세션 끊기).
- 사번이 없는 직원(팀 테스트 계정 일부)은 엑셀로 다루지 않는다(열쇠가 없음).
- 새 직원의 비밀번호는 시연 초기 비밀번호(.env GP5_DEMO_PASSWORD)를 해시로 넣는다.
- 반영 뒤 바뀐 직원의 목표 후보를 다시 만든다(FR-05 · 직원 데이터가 갱신될 때 미리 생성).
- 입사일·현재 근무 시작일은 팀 DB employees.hire_date·department_start_date 에 쓴다(2026-10-27 · 팀 최신 DB 기준).
  직원 구분이 비면 직급 이름('일반직 4급')의 앞부분을 보여 준다.
"""
from __future__ import annotations

from .. import db
from ..auth import hash_password
from ..config import S
from ..errors import ApiError
from ..services.profile import EMP_GROUP_SQL
from .base import Col, Row, Sheet, merged

NAME, TITLE = 'hr', '인적 데이터'
ACCOUNT = {'active': '사용', 'locked': '잠금', 'inactive': '중지'}
ACCOUNT_IN = {v: k for k, v in ACCOUNT.items()}
STATUS = ('재직', '휴직', '퇴직')

DEPT = Sheet('부서', ('code',), [
    Col('부서 코드', 'code', required=True, help='부서를 찾는 열쇠. 새 부서는 겹치지 않는 영문·숫자 코드로 적어요', example='BIZ', width=14),
    Col('부서 이름', 'name', required=True, example='업무시스템팀', width=20),
    Col('상위 부서 코드', 'parent', help='위 부서의 코드. 맨 위 부서는 비워요. 부서장 범위(내 부서 + 바로 아래 부서의 부서장)가 이 관계로 정해져요', example='DIGITAL', width=14),
    Col('부서장', 'head_name', readonly=True, width=12),
    Col('직원 수', 'members', 'int', readonly=True, width=8),
], help='부서와 상위 부서. 지우려면 그 부서에 직원과 아래 부서가 없어야 해요')

EMP = Sheet('직원', ('code',), [
    Col('사번', 'code', required=True, help='직원을 찾는 열쇠. 바꿀 수 없어요', example='20200001', width=11),
    Col('이름', 'name', required=True, width=9),
    Col('이메일', 'email', help='겹치면 안 돼요', width=24),
    Col('직원 구분', 'emp_group', help='규정 묶음을 정해요(일반직·실무직 등)', example='일반직', width=10),
    Col('재직 상태', 'status', 'choice', choices=STATUS, help='퇴직이면 로그인할 수 없어요. 비우면 재직', width=9, default='재직'),
    Col('계정 상태', 'account', 'choice', choices=tuple(ACCOUNT.values()), help='사용이 아니면 로그인할 수 없어요. 비우면 사용', width=9, default='사용'),
    Col('입사일', 'hire_date', 'date', example='2020-03-02', width=11),
    Col('부서 코드', 'dept_code', help='인사이동은 이 칸을 고쳐요(이동 이력이 자동으로 남아요)', example='BIZ', width=11),
    Col('부서 이름', 'dept_name', readonly=True, width=16),
    Col('직급', 'grade', help='직급 표에 없는 이름이면 새 직급으로 추가돼요', example='일반직 4급', width=12),
    Col('직위·보직', 'position', width=12),
    Col('직종·직렬', 'job_family', width=12),
    Col('직무', 'job', width=16),
    Col('주요 담당 업무', 'task', width=28),
    Col('부서장', 'head', 'bool', help='Y면 그 부서의 부서장(권한 부여), N이면 해제(권한 회수). 한 부서에 한 명', width=8, default=False),
    Col('현재 근무 시작일', 'valid_from', 'date', width=12),
    Col('변경 사유', 'change_reason', example='정기 인사', width=14),
], help='직원 인사 정보·부서 배치·부서장 권한. 삭제 Y는 퇴직 처리예요(기록은 남아요)')

EVAL = Sheet('평정', ('code', 'period'), [
    Col('사번', 'code', required=True, width=11),
    Col('기간', 'period', required=True, example='2025', width=9),
    Col('이름', 'name', readonly=True, width=9),
    Col('평정명', 'title', example='2025년 근무성적평정', width=22),
    Col('등급', 'grade', example='A', width=8),
    Col('점수', 'score', width=8),
    Col('목표 추천 활용 기본 동의', 'consent', 'bool', help='직원이 내 정보에서 바꾸면 직원이 정한 값이 우선해요', width=12, default=False),
], help='근무성적평정. 목표 추천 활용에 동의한 평정만 목표 후보 제안에 참고로 넘겨요')

SHEETS = [DEPT, EMP, EVAL]
DELETE_LABEL = {'직원': '퇴직 처리'}
GUIDE = [
    '인적 데이터(부서·직원·평정)를 엑셀로 내려받아 고친 뒤 다시 올려요. 올리면 먼저 미리보기를 보여 주고, 오류가 없을 때만 ‘반영’할 수 있어요.',
    '· 파일에 없는 행은 그대로 둬요. 지우려면 ‘삭제’ 열에 Y를 적어요(직원은 지우지 않고 퇴직 처리해요).',
    '· 파일에 없는 열은 바꾸지 않아요. 있는 열의 빈 칸은 값을 비워요. 회색 머리글 열은 참고용이라 고쳐도 반영되지 않아요.',
    '· 인사이동: 직원 시트의 ‘부서 코드’를 고치면 이동 이력이 자동으로 남아요. 부서장 권한은 ‘부서장’ Y/N으로 주고 거둬요.',
    f'· 새 직원은 시연 초기 비밀번호({S.demo_password or ".env 의 GP5_DEMO_PASSWORD · 지금 비어 있음"})로 로그인해요. 사번이 없는 팀 테스트 계정은 이 파일에 나오지 않아요.',
    '· 반영하면 바뀐 직원의 목표 후보를 다시 만들어요.',
]


def _inst(t: db.Tx | None = None) -> str:
    sql = "SELECT institution_id FROM public.departments WHERE department_code NOT LIKE 'LEGACY-%' LIMIT 1"
    return (t.val(sql) if t else db.val(sql)) or db.val('SELECT institution_id FROM public.institutions LIMIT 1')


def current(sheet: str) -> dict:
    if sheet == '부서':
        rows = db.all_("""SELECT d.department_id, d.department_code, d.name, p.department_code AS parent,
                (SELECT e.name FROM public.employees e WHERE e.department_id = d.department_id AND e.is_department_head LIMIT 1) AS head_name,
                (SELECT count(*) FROM public.employees e LEFT JOIN app_ext.employee_hr h ON h.employee_id = e.employee_id
                  WHERE e.department_id = d.department_id AND coalesce(h.employment_status, '재직') <> '퇴직') AS members
            FROM public.departments d LEFT JOIN public.departments p ON p.department_id = d.parent_department_id ORDER BY d.parent_department_id NULLS FIRST, d.department_id""")
        return {(r['department_code'],): {'code': r['department_code'], 'name': r['name'], 'parent': r['parent'], 'head_name': r['head_name'], 'members': r['members'],
                                          '_id': r['department_id']} for r in rows}
    if sheet == '직원':
        rows = db.all_(f"""SELECT e.employee_id, e.employee_number, e.name, e.email, e.is_department_head, e.department_id, d.department_code, d.name AS dept_name,
                coalesce(g.name, e.grade) AS grade, coalesce(j.title, e.job_title) AS job, {EMP_GROUP_SQL} AS employee_group, h.employment_status, h.account_status,
                coalesce(e.hire_date, h.hire_date) AS hire_date, h.position, h.job_family, h.task, coalesce(e.department_start_date, h.valid_from) AS valid_from, h.change_reason
            FROM public.employees e LEFT JOIN public.departments d ON d.department_id = e.department_id
            LEFT JOIN public.job_grades g ON g.job_grade_id = e.job_grade_id LEFT JOIN public.jobs j ON j.job_id = e.job_id
            LEFT JOIN app_ext.employee_hr h ON h.employee_id = e.employee_id
            WHERE e.employee_number IS NOT NULL ORDER BY d.department_id NULLS LAST, e.is_department_head DESC, e.employee_number""")
        return {(r['employee_number'],): {
            'code': r['employee_number'], 'name': r['name'], 'email': r['email'], 'emp_group': r['employee_group'], 'status': r['employment_status'] or '재직',
            'account': ACCOUNT.get(r['account_status'] or 'active'), 'hire_date': str(r['hire_date']) if r['hire_date'] else None,
            'dept_code': r['department_code'], 'dept_name': r['dept_name'], 'grade': r['grade'], 'position': r['position'], 'job_family': r['job_family'],
            'job': r['job'], 'task': r['task'], 'head': bool(r['is_department_head']), 'valid_from': str(r['valid_from']) if r['valid_from'] else None,
            'change_reason': r['change_reason'], '_id': r['employee_id'], '_dept_id': r['department_id']} for r in rows}
    if sheet == '평정':
        rows = db.all_("""SELECT e.employee_number, e.name, v.period, v.title, v.grade, v.score, v.consent_default FROM app_ext.employee_evaluations v
            JOIN public.employees e ON e.employee_id = v.employee_id WHERE e.employee_number IS NOT NULL ORDER BY e.employee_number, v.period DESC""")
        return {(r['employee_number'], r['period']): {'code': r['employee_number'], 'period': r['period'], 'name': r['name'], 'title': r['title'], 'grade': r['grade'],
                                                       'score': r['score'], 'consent': bool(r['consent_default'])} for r in rows}
    return {}


def options(sheet: str) -> dict:
    """화면에서 고칠 때의 고르기 목록. strict 는 목록 밖 값을 쓸 수 없는 칸(고르기), 아니면 추천만(직접 적어도 됨)"""
    depts = {'strict': True, 'items': [{'value': r['department_code'], 'label': r['name']}
                                       for r in db.all_('SELECT department_code, name FROM public.departments WHERE department_code IS NOT NULL ORDER BY department_id')]}
    if sheet == '부서':
        return {'parent': depts}
    if sheet == '직원':
        return {'dept_code': depts,
                'grade': {'items': [{'value': r['name']} for r in db.all_('SELECT DISTINCT name FROM public.job_grades ORDER BY name')]},
                'emp_group': {'items': [{'value': r['g']} for r in db.all_("""SELECT DISTINCT g FROM (SELECT employee_group AS g FROM app_ext.employee_hr
                    UNION SELECT substring(name from '^([^ ]+직) ') FROM public.job_grades) x WHERE g IS NOT NULL ORDER BY 1""")]}}
    if sheet == '평정':
        return {'code': {'strict': True, 'items': [{'value': r['employee_number'], 'label': r['name']}
                                                   for r in db.all_('SELECT employee_number, name FROM public.employees WHERE employee_number IS NOT NULL ORDER BY employee_number')]}}
    return {}


def label(sheet: str, v: dict) -> str:
    if sheet == '부서':
        return v.get('name') or ''
    if sheet == '직원':
        return ' · '.join(x for x in (v.get('name'), v.get('dept_name') or v.get('dept_code')) if x)
    return ' · '.join(x for x in (v.get('name'), v.get('title')) if x)


def check(found: dict[str, list[Row]], cur: dict[str, dict]) -> None:
    """시트를 오가는 검사: 부서가 있는지·순환·부서장 한 명·이메일·평정의 직원. 태그(인사이동·부서장 지정 등)도 단다"""
    depts = dict(cur.get('부서') or current('부서'))
    emps = dict(cur.get('직원') or current('직원'))
    drows = found.get('부서', [])
    erows = found.get('직원', [])
    # 반영 뒤의 부서 상태
    final_d = {k[0]: dict(v) for k, v in depts.items()}
    for r in drows:
        if r.action in ('add', 'update'):
            final_d[r.key[0]] = merged(r, depts.get(r.key))
        elif r.action == 'delete':
            final_d.pop(r.key[0], None)
    for r in drows:
        if r.action not in ('add', 'update'):
            continue
        p = final_d[r.key[0]].get('parent')
        if p and p not in final_d:
            r.err('상위 부서 코드', f'‘{p}’ 부서가 없어요')
        elif p == r.key[0]:
            r.err('상위 부서 코드', '자기 자신을 상위 부서로 둘 수 없어요')
    # 순환 검사
    for code in final_d:
        seen, x = set(), code
        while x and x in final_d:
            if x in seen:
                bad = next((r for r in drows if r.key[0] == code and r.action in ('add', 'update')), None)
                if bad:
                    bad.err('상위 부서 코드', '상위 부서가 돌고 돌아 자기 자신이 돼요')
                break
            seen.add(x)
            x = final_d[x].get('parent')
    # 반영 뒤의 직원 상태
    final_e = {k[0]: dict(v) for k, v in emps.items()}
    for r in erows:
        if r.action in ('add', 'update'):
            final_e[r.key[0]] = merged(r, emps.get(r.key))
        elif r.action == 'delete':
            final_e[r.key[0]] = dict(emps[r.key], status='퇴직', account='중지', head=False)
    by_row = {r.key[0]: r for r in erows if r.action in ('add', 'update', 'delete')}
    grades = {g['name'] for g in db.all_('SELECT name FROM public.job_grades')}
    for r in erows:
        if r.action not in ('add', 'update'):
            continue
        v = final_e[r.key[0]]
        if v.get('dept_code') and v['dept_code'] not in final_d:
            r.err('부서 코드', f"‘{v['dept_code']}’ 부서가 없어요(부서 시트에 먼저 추가해 주세요)")
        if v.get('head') and not v.get('dept_code'):
            r.err('부서장', '부서장은 부서가 있어야 해요')
        if v.get('head') and v.get('status') == '퇴직':
            r.err('부서장', '퇴직한 직원은 부서장이 될 수 없어요')
        if v.get('grade') and v['grade'] not in grades:
            r.warn(f"‘{v['grade']}’은 직급 표에 없어 새 직급으로 추가돼요")
        old = emps.get(r.key) or {}
        if r.action == 'add':
            r.tags.append('신규 직원')
        if old and old.get('dept_code') != v.get('dept_code'):
            r.tags.append(f"인사이동 {old.get('dept_name') or old.get('dept_code') or '없음'} → {(final_d.get(v.get('dept_code')) or {}).get('name') or v.get('dept_code') or '없음'}")
        if bool(old.get('head')) != bool(v.get('head')):
            r.tags.append('부서장 지정(권한 부여)' if v.get('head') else '부서장 해제(권한 회수)')
        if old and old.get('status') != v.get('status') and v.get('status') == '퇴직':
            r.tags.append('퇴직')
    for r in erows:
        if r.action == 'delete':
            r.tags.append('퇴직 처리')
            if emps[r.key].get('head'):
                r.tags.append('부서장 해제(권한 회수)')
    # 한 부서에 부서장 한 명
    heads: dict[str, list[str]] = {}
    for code, v in final_e.items():
        if v.get('head') and v.get('dept_code'):
            heads.setdefault(v['dept_code'], []).append(code)
    for dc, codes in heads.items():
        if len(codes) > 1:
            names = ', '.join(f"{final_e[c].get('name')}({c})" for c in codes)
            for c in codes:
                if c in by_row and by_row[c].action in ('add', 'update'):
                    by_row[c].err('부서장', f"{(final_d.get(dc) or {}).get('name') or dc}에 부서장이 둘 이상이에요: {names}. 한 명만 Y로 두고, 바꾸는 사람은 N으로 적어 주세요")
    # 이메일 중복
    mails: dict[str, list[str]] = {}
    for code, v in final_e.items():
        if v.get('email'):
            mails.setdefault(v['email'].lower(), []).append(code)
    for m, codes in mails.items():
        if len(codes) > 1:
            for c in codes:
                if c in by_row and by_row[c].action in ('add', 'update'):
                    by_row[c].err('이메일', f'다른 직원과 이메일이 같아요({", ".join(x for x in codes if x != c)})')
    # 부서 지우기: 직원·아래 부서가 남으면 안 됨
    for r in drows:
        if r.action != 'delete':
            continue
        left = [v.get('name') for v in final_e.values() if v.get('dept_code') == r.key[0] and v.get('status') != '퇴직']
        kids = [c for c, v in final_d.items() if v.get('parent') == r.key[0]]
        if left:
            r.err('삭제', f"직원 {len(left)}명이 남아 있어 지울 수 없어요({', '.join(left[:4])}…). 직원 시트에서 먼저 부서를 옮겨 주세요")
        elif kids:
            r.err('삭제', f"아래 부서가 있어 지울 수 없어요({', '.join(kids[:4])})")
        elif any(v.get('dept_code') == r.key[0] for v in final_e.values()):
            r.err('삭제', '퇴직한 직원 기록이 이 부서에 남아 있어 지울 수 없어요(부서 이름만 바꿔 주세요)')
    # 평정: 직원이 있어야
    for r in found.get('평정', []):
        if r.action in ('add', 'update') and r.key[0] not in final_e:
            r.err('사번', f"‘{r.key[0]}’ 직원이 없어요")


def apply(t: db.Tx, found: dict[str, list[Row]], cur: dict[str, dict], ctx: dict) -> dict:
    inst = _inst(t)
    depts, emps = cur.get('부서') or current('부서'), cur.get('직원') or current('직원')
    res = {'부서': {'add': 0, 'update': 0, 'delete': 0}, '직원': {'add': 0, 'update': 0, 'delete': 0}, '평정': {'add': 0, 'update': 0, 'delete': 0},
           'transfers': 0, 'goal_ids': []}
    # 1) 부서 추가·이름 바꾸기(상위 부서는 다 넣은 뒤 정한다 · 새 부서끼리 서로 가리킬 수 있어서)
    ids = {k[0]: v['_id'] for k, v in depts.items()}
    drows = [r for r in found.get('부서', []) if r.action in ('add', 'update')]
    for r in drows:
        v = merged(r, depts.get(r.key))
        if r.action == 'add':
            ids[r.key[0]] = t.val('INSERT INTO public.departments(institution_id, department_code, name) VALUES(:i, :c, :n) RETURNING department_id',
                                  i=inst, c=r.key[0], n=v['name'])
        else:
            t.run('UPDATE public.departments SET name = :n WHERE department_id = :d', n=v['name'], d=ids[r.key[0]])
        res['부서'][r.action] += 1
    for r in drows:
        if 'parent' in r.present or r.action == 'add':
            v = merged(r, depts.get(r.key))
            t.run('UPDATE public.departments SET parent_department_id = :p WHERE department_id = :d', p=ids.get(v.get('parent')) if v.get('parent') else None, d=ids[r.key[0]])
    dept_names = {code: depts.get((code,), {}).get('name') for code in ids}
    dept_names.update({r.key[0]: merged(r, depts.get(r.key)).get('name') for r in drows})
    # 2) 직원: 부서장 해제를 먼저(한 부서 한 명 고유 색인 때문에 바꾸는 순서가 중요)
    erows = [r for r in found.get('직원', []) if r.action in ('add', 'update', 'delete')]
    finals = {}
    for r in erows:
        old = emps.get(r.key)
        v = dict(old, status='퇴직', account='중지', head=False) if r.action == 'delete' else merged(r, old)
        finals[r.key[0]] = v
        if old and old.get('head') and not v.get('head'):
            t.run('UPDATE public.employees SET is_department_head = false, updated_at = now() WHERE employee_id = :e', e=old['_id'])
    grade_ids = {g['name']: g['job_grade_id'] for g in t.all('SELECT job_grade_id, name FROM public.job_grades WHERE institution_id = :i', i=inst)}
    job_ids = {j['title']: j['job_id'] for j in t.all('SELECT job_id, title FROM public.jobs')}
    demo_hash = None
    for r in erows:
        old, v = emps.get(r.key), finals[r.key[0]]
        g = v.get('grade')
        if g and g not in grade_ids:
            grade_ids[g] = t.val('INSERT INTO public.job_grades(institution_id, name, sort_order) VALUES(:i, :n, 9) RETURNING job_grade_id', i=inst, n=g)
        dept_id = ids.get(v.get('dept_code')) if v.get('dept_code') else None
        cols = dict(n=v['name'], m=v.get('email'), d=dept_id, dn=dept_names.get(v.get('dept_code')) if v.get('dept_code') else None,
                    g=grade_ids.get(g) if g else None, gn=g, jt=v.get('job'), j=job_ids.get(v.get('job') or ''), h=bool(v.get('head')), i=inst,
                    hd=v.get('hire_date'), vf=v.get('valid_from'))
        if r.action == 'add':
            if not S.demo_password:
                raise ApiError(409, 'NO_DEMO_PASSWORD', '새 직원의 초기 비밀번호가 설정되지 않아 추가할 수 없어요', '.env 의 GP5_DEMO_PASSWORD 를 넣고 서버를 다시 켜 주세요')
            demo_hash = demo_hash or hash_password(S.demo_password)
            eid = t.val("""INSERT INTO public.employees(name, email, employee_number, institution_id, department_id, department, job_grade_id, grade, job_title, job_id,
                           is_department_head, hire_date, department_start_date, source_type, password_hash, created_at, updated_at)
                           VALUES(:n, :m, :c, :i, :d, :dn, :g, :gn, :jt, :j, :h, CAST(:hd AS date), CAST(:vf AS date), :src, :pw, now(), now()) RETURNING employee_id""",
                        c=r.key[0], pw=demo_hash, src='ADMIN_FORM' if ctx.get('source') == 'form' else 'ADMIN_UPLOAD', **cols)
        else:
            eid = old['_id']
            t.run("""UPDATE public.employees SET name = :n, email = :m, department_id = :d, department = :dn, job_grade_id = :g, grade = :gn, job_title = :jt,
                     job_id = :j, is_department_head = :h, hire_date = CAST(:hd AS date), department_start_date = CAST(:vf AS date), updated_at = now()
                     WHERE employee_id = :e""", e=eid, **{k: x for k, x in cols.items() if k != 'i'})
        # 입사일·현재 근무 시작일은 위에서 팀 표에 썼으므로 보조 표에는 비워 둔다(옛 값이 팀 값을 가리지 않게)
        t.run("""INSERT INTO app_ext.employee_hr(employee_id, employee_group, hire_date, position, job_family, task, employment_status, account_status, valid_from, change_reason, updated_at)
                 VALUES(:e, :eg, CAST(:hd AS date), :po, :jf, :ta, :st, :ac, CAST(:vf AS date), :cr, now())
                 ON CONFLICT (employee_id) DO UPDATE SET employee_group = EXCLUDED.employee_group, hire_date = EXCLUDED.hire_date, position = EXCLUDED.position,
                   job_family = EXCLUDED.job_family, task = EXCLUDED.task, employment_status = EXCLUDED.employment_status, account_status = EXCLUDED.account_status,
                   valid_from = EXCLUDED.valid_from, change_reason = EXCLUDED.change_reason, updated_at = now()""",
              e=eid, eg=v.get('emp_group'), hd=None, po=v.get('position'), jf=v.get('job_family'), ta=v.get('task'), st=v.get('status') or '재직',
              ac=ACCOUNT_IN.get(v.get('account') or '사용', 'active'), vf=None, cr=v.get('change_reason'))
        # 인사이동·부서장 권한 이력
        if old and (old.get('dept_code') != v.get('dept_code') or bool(old.get('head')) != bool(v.get('head'))):
            t.run("""INSERT INTO app_ext.employee_transfers(employee_id, from_department_id, to_department_id, from_department_name, to_department_name, head_before, head_after,
                     changed_by_admin, upload_id) VALUES(:e, :fd, :td, :fn, :tn, :hb, :ha, :a, CAST(:u AS uuid))""",
                  e=eid, fd=old.get('_dept_id'), td=dept_id, fn=old.get('dept_name'), tn=cols['dn'], hb=bool(old.get('head')), ha=bool(v.get('head')), a=ctx['admin_id'], u=ctx['upload_id'])
            res['transfers'] += 1
        if (v.get('status') == '퇴직') or ACCOUNT_IN.get(v.get('account') or '사용') != 'active':
            t.run("DELETE FROM app_ext.sessions WHERE account_type = 'employee' AND account_id = :e", e=eid)
        res['직원'][r.action] += 1
        if v.get('status') != '퇴직':
            res['goal_ids'].append(eid)
    # 3) 평정
    code_ids = {k[0]: v['_id'] for k, v in emps.items()}
    code_ids.update({c: t.val('SELECT employee_id FROM public.employees WHERE institution_id = :i AND employee_number = :c', i=inst, c=c)
                     for c in finals if c not in code_ids})
    evals = cur.get('평정') or current('평정')
    for r in found.get('평정', []):
        if r.action not in ('add', 'update', 'delete'):
            continue
        eid = code_ids.get(r.key[0])
        if r.action == 'delete':
            t.run('DELETE FROM app_ext.employee_evaluations WHERE employee_id = :e AND period = :p', e=eid, p=r.key[1])
        else:
            v = merged(r, evals.get(r.key))
            t.run("""INSERT INTO app_ext.employee_evaluations(employee_id, period, title, grade, score, consent_default) VALUES(:e, :p, :ti, :g, :s, :c)
                     ON CONFLICT (employee_id, period) DO UPDATE SET title = EXCLUDED.title, grade = EXCLUDED.grade, score = EXCLUDED.score, consent_default = EXCLUDED.consent_default""",
                  e=eid, p=r.key[1], ti=v.get('title'), g=v.get('grade'), s=v.get('score'), c=bool(v.get('consent')))
        res['평정'][r.action] += 1
        if eid and eid not in res['goal_ids']:
            res['goal_ids'].append(eid)
    # 4) 부서 지우기(직원을 옮긴 뒤)
    for r in found.get('부서', []):
        if r.action == 'delete':
            t.run('DELETE FROM public.departments WHERE department_id = :d', d=ids[r.key[0]])
            res['부서']['delete'] += 1
    return res


def after(res: dict, ctx: dict) -> None:
    """반영 뒤: 바뀐 직원의 목표 후보를 다시 만든다(실패해도 반영은 그대로 · 직원 화면에 실패로 보임)"""
    from ..services import goals
    for eid in res.get('goal_ids', []):
        try:
            goals.request(eid, 'admin-upload', mode=ctx.get('goal_mode'))
        except Exception as e:  # noqa: BLE001 - 한 직원 실패가 다른 직원을 막지 않게 하고 원인은 남긴다
            print(f'  목표 후보 다시 만들기 실패(직원 {eid}): {e}')
