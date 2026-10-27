"""직원 프로필·권한 (설계서 v1.7 API-04~08 · 5.1 접근 범위).

부서장 범위(2026-10-21 사용자 결정): 부서장은 자기 부서의 직원 + 바로 아래 부서의 부서장을 본다(4차 감독 그룹과 같은 결과).
내 계획을 보는 부서장 = 자기 부서의 부서장, 내가 부서장이면 바로 위 부서의 부서장. 부서장 권한은 팀 DB employees.is_department_head.
화면에는 4차와 같은 모양(view)으로 주고, 설계서 API 모양(hr·permission·self·evaluations)도 함께 준다.
"""
from __future__ import annotations

from datetime import datetime

from .. import db
from ..errors import ApiError

LISTS = ('tech', 'certs', 'learning', 'projects')


def _grade(name: str | None) -> str:
    # 팀 DB 직급 이름은 '일반직 4급'. 화면은 4차처럼 '4급'
    return (name or '').replace('일반직 ', '', 1) or ''


def _rows() -> list[dict]:
    return db.all_("""SELECT e.employee_id, e.employee_number, e.name, e.is_department_head, e.department_id, e.source_type,
            coalesce(d.name, e.department) AS dept, pd.name AS parent_dept, d.parent_department_id,
            coalesce(g.name, e.grade) AS grade, coalesce(j.title, e.job_title) AS job,
            h.employee_group, h.hire_date, h.position, h.job_family, h.task, h.employment_status, h.account_status, h.grade_since, h.valid_from, h.change_reason
        FROM public.employees e
        LEFT JOIN public.departments d ON d.department_id = e.department_id
        LEFT JOIN public.departments pd ON pd.department_id = d.parent_department_id
        LEFT JOIN public.job_grades g ON g.job_grade_id = e.job_grade_id
        LEFT JOIN public.jobs j ON j.job_id = e.job_id
        LEFT JOIN app_ext.employee_hr h ON h.employee_id = e.employee_id
        ORDER BY e.employee_id""")


def _ref(r: dict) -> dict:
    return {'id': str(r['employee_id']), 'name': r['name'], 'code': r['employee_number'] or ''}


def supervisor_of(r: dict, rows: list[dict]) -> dict | None:
    if not r['department_id']:
        return None
    if not r['is_department_head']:
        h = next((x for x in rows if x['department_id'] == r['department_id'] and x['is_department_head'] and x['employee_id'] != r['employee_id']), None)
    else:
        h = next((x for x in rows if r['parent_department_id'] and x['department_id'] == r['parent_department_id'] and x['is_department_head']), None)
    return h


def members_of(r: dict, rows: list[dict]) -> list[dict]:
    if not r['is_department_head'] or not r['department_id']:
        return []
    child_depts = {x['department_id'] for x in rows if x['parent_department_id'] == r['department_id']}
    return [x for x in rows if x['employee_id'] != r['employee_id'] and (
        (x['department_id'] == r['department_id'] and not x['is_department_head']) or (x['department_id'] in child_depts and x['is_department_head']))]


def member_ids(employee_id: int) -> set[int]:
    rows = _rows()
    me = next((x for x in rows if x['employee_id'] == employee_id), None)
    return {x['employee_id'] for x in members_of(me, rows)} if me else set()


def _self_of(employee_id: int) -> tuple[dict | None, dict | None, datetime | None]:
    s = db.one('SELECT baseline, edited, edited_at FROM app_ext.employee_self_inputs WHERE employee_id = :e', e=employee_id) or {}
    return s.get('baseline'), s.get('edited'), s.get('edited_at')


def _evals(employee_id: int) -> list[dict]:
    return [{'period': v['period'], 'title': v['title'] or '', 'grade': v['grade'] or '', 'score': v['score'] or '',
             'consent': v['consent'] if v['consent'] is not None else v['consent_default'], 'consentDefault': v['consent_default']}
            for v in db.all_('SELECT * FROM app_ext.employee_evaluations WHERE employee_id = :e ORDER BY period DESC', e=employee_id)]


def view(employee_id: int, rows: list[dict] | None = None) -> dict | None:
    """4차 화면 모양의 계정 정보(GP.me)"""
    rows = rows or _rows()
    r = next((x for x in rows if x['employee_id'] == employee_id), None)
    if not r:
        return None
    base, edited, at = _self_of(employee_id)
    src = edited or base or {}
    has_profile = bool(src.get('present', bool(src.get('workDesc')))) if src else False
    sup = supervisor_of(r, rows)
    ms = members_of(r, rows)
    edu = db.all_('SELECT school_name, education_level, department_name FROM public.employee_education_records WHERE employee_id = :e', e=employee_id)
    return {
        'id': str(r['employee_id']), 'code': r['employee_number'] or '', 'name': r['name'], 'role': 'employee', 'source': r['source_type'],
        'hireDate': str(r['hire_date']) if r['hire_date'] else None, 'dept': r['dept'], 'parentDept': r['parent_dept'], 'deptId': r['department_id'],
        'grade': _grade(r['grade']), 'jobFamily': r['job_family'], 'position': r['position'], 'job': r['job'], 'task': r['task'],
        'supervisor': bool(r['is_department_head']), 'empGroup': r['employee_group'], 'status': r['employment_status'] or '재직',
        'accountStatus': r['account_status'] or 'active', 'validFrom': str(r['valid_from']) if r['valid_from'] else None, 'changeReason': r['change_reason'],
        'gradeSince': str(r['grade_since']) if r['grade_since'] else None,
        'supGroup': {'name': r['dept'], 'id': str(r['department_id'])} if r['is_department_head'] and r['department_id'] else None,
        'members': [_ref(x) for x in ms], 'planGroup': {'name': sup['dept'] if sup and r['is_department_head'] else r['dept'], 'id': str(sup['department_id'])} if sup else None,
        'mySupervisor': _ref(sup) if sup else None,
        'profile': {k: src.get(k) for k in ('workDesc', 'expStatus', 'expSummary', 'devYears', 'inputStatus')} if has_profile else None,
        **{k: list(src.get(k) or []) for k in LISTS},
        'evals': _evals(employee_id), 'edited': bool(edited), 'editedAt': at.strftime('%Y-%m-%d') if at else None,
        'education': [f"{x['school_name']} {x['department_name'] or ''} ({x['education_level']})".replace('  ', ' ') for x in edu],
    }


def accounts() -> list[dict]:
    """로그인 화면의 '직원 고르기'(시연 전용 · 설계서 부록 A): 부서별, 부서장 표시. 사번이 없는 계정은 로그인할 수 없어 뺀다"""
    rows = _rows()
    out = []
    for r in rows:
        if not r['employee_number'] or (r['employment_status'] or '재직') != '재직' or (r['account_status'] or 'active') != 'active':
            continue
        out.append({'id': str(r['employee_id']), 'code': r['employee_number'], 'name': r['name'], 'dept': r['dept'] or '부서 없음',
                    'supervisor': bool(r['is_department_head'] and members_of(r, rows)), 'team': r['source_type'] != 'TEST_MANUAL' or r['employee_group'] is None})
    return out


def spec(v: dict) -> dict:
    """설계서 API-05 모양"""
    return {'hr': {k: v[k] for k in ('code', 'name', 'empGroup', 'status', 'hireDate', 'parentDept', 'dept', 'grade', 'gradeSince', 'jobFamily', 'position', 'job', 'task', 'validFrom', 'changeReason')},
            'permission': {'role': v['role'], 'supervisor': {'group': v['supGroup'], 'memberCount': len(v['members'])} if v['supGroup'] else None,
                           'mySupervisor': v['mySupervisor']},
            'self': {'profile': v['profile'], **{k: v[k] for k in LISTS}, 'edited': v['edited'], 'editedAt': v['editedAt']},
            'evaluations': v['evals']}


def save_self(employee_id: int, body: dict) -> None:
    """본인 입력 저장(API-06). 하나라도 적으면 업무 설명 필수(사내 DB 규칙). 사내 DB 값과 같으면 '직접 고침'으로 두지 않는다"""
    wd, ex = str(body.get('workDesc') or '').strip(), str(body.get('expSummary') or '').strip()
    yrs = body.get('devYears')
    yrs = None if yrs in ('', None) else float(yrs)
    if yrs is not None and not 0 <= yrs <= 50:
        raise ApiError(422, 'DEV_YEARS_RANGE', '개발 경험은 0~50년 사이로 적거나 비워 주세요.')
    lists = {k: [str(x).strip() for x in body.get(k) or [] if str(x).strip()][:20] for k in LISTS}
    none = body.get('noneConfirmed') or {}
    anything = wd or ex or yrs is not None or any(lists[k] or none.get(k) for k in LISTS)
    if anything and not wd:
        raise ApiError(422, 'WORK_DESC_REQUIRED', '업무 설명을 적어 주세요. 본인 입력 정보를 저장할 때 업무 설명은 꼭 있어야 해요.')
    st = lambda k: 'reported' if lists[k] else 'none_confirmed' if none.get(k) else 'unprovided'  # noqa: E731
    new = {'workDesc': wd or None, 'expStatus': 'reported' if ex else 'unprovided', 'expSummary': ex or None, 'devYears': yrs,
           'inputStatus': {k2: st(k) for k, k2 in (('certs', 'certs'), ('learning', 'learning'), ('projects', 'projects'), ('tech', 'tech'))},
           **lists, 'present': bool(anything)}
    base, _, _ = _self_of(employee_id)
    same = base is not None and all((base.get(k) or None) == (new.get(k) or None) for k in ('workDesc', 'expSummary', 'devYears', *LISTS))
    with db.tx() as t:
        t.run("""INSERT INTO app_ext.employee_self_inputs(employee_id, baseline, edited, edited_at) VALUES(:e, NULL, :v, now())
                 ON CONFLICT (employee_id) DO UPDATE SET edited = :v, edited_at = now()""", e=employee_id, v=None if same else db.J(new))


def revert_self(employee_id: int) -> None:
    with db.tx() as t:
        t.run('UPDATE app_ext.employee_self_inputs SET edited = NULL, edited_at = NULL WHERE employee_id = :e', e=employee_id)


def set_consent(employee_id: int, period: str, consent: bool) -> None:
    with db.tx() as t:
        row = t.one('SELECT consent_default FROM app_ext.employee_evaluations WHERE employee_id = :e AND period = :p', e=employee_id, p=period)
        if not row:
            raise ApiError(404, 'NOT_FOUND', '그 평정을 찾을 수 없어요')
        t.run('UPDATE app_ext.employee_evaluations SET consent = :c, consent_changed_at = now() WHERE employee_id = :e AND period = :p',
              c=None if consent == row['consent_default'] else consent, e=employee_id, p=period)
