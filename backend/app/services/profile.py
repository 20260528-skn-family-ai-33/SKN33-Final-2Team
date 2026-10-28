"""직원 프로필·권한 (설계서 v1.7 API-04~08 · 5.1 접근 범위).

부서장 범위(2026-10-27 팀 합의 · 팀 DB employee_can_read_employee 와 같음): 부서장은 자기 부서의 직원만 본다.
내 계획을 보는 부서장 = 자기 부서의 부서장, 부서장의 계획은 본인만 본다. 상위 부서는 표시·목표 후보 입력에만 쓰고 권한에는 쓰지 않는다.
부서장 권한은 팀 DB employees.is_department_head.
화면에는 4차와 같은 모양(view)으로 주고, 설계서 API 모양(hr·permission·self·evaluations)도 함께 준다.
"""
from __future__ import annotations

from datetime import datetime

from .. import db
from ..errors import ApiError

LISTS = ('tech', 'certs', 'learning', 'projects')
# 팀 DB 학력 단계 코드(employee_form.EDUCATION_LEVELS) → 화면 글자
EDU_LEVEL = {'middle_school_or_lower': '중학교 이하', 'high_school': '고등학교', 'associate': '전문학사', 'bachelor': '학사',
             'master': '석사', 'doctorate': '박사', 'other': '기타'}
# 직원 구분(일반직·실무직 등 · 규정 묶음 선택에 씀): 관리자가 정한 값이 없으면 팀 DB 직급 이름('일반직 4급')의 앞부분
EMP_GROUP_SQL = "coalesce(h.employee_group, substring(coalesce(g.name, e.grade) from '^([^ ]+직) '))"


def _grade(name: str | None) -> str:
    # 팀 DB 직급 이름은 '일반직 4급'. 화면은 4차처럼 '4급'
    return (name or '').replace('일반직 ', '', 1) or ''


def _rows() -> list[dict]:
    # 입사일·현재 근무 시작일은 팀 DB employees(#22 최신 DB 의 hire_date·department_start_date)를 먼저 쓴다
    return db.all_(f"""SELECT e.employee_id, e.employee_number, e.name, e.is_department_head, e.department_id, e.source_type,
            coalesce(d.name, e.department) AS dept, pd.name AS parent_dept,
            coalesce(g.name, e.grade) AS grade, coalesce(j.title, e.job_title) AS job,
            {EMP_GROUP_SQL} AS employee_group, coalesce(e.hire_date, h.hire_date) AS hire_date, h.position, h.job_family, h.task,
            h.employment_status, h.account_status, h.grade_since, coalesce(e.department_start_date, h.valid_from) AS valid_from, h.change_reason
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
    if not r['department_id'] or r['is_department_head']:
        return None
    return next((x for x in rows if x['department_id'] == r['department_id'] and x['is_department_head']), None)


def members_of(r: dict, rows: list[dict]) -> list[dict]:
    if not r['is_department_head'] or not r['department_id']:
        return []
    return [x for x in rows if x['department_id'] == r['department_id'] and not x['is_department_head']]


def member_ids(employee_id: int) -> set[int]:
    rows = _rows()
    me = next((x for x in rows if x['employee_id'] == employee_id), None)
    return {x['employee_id'] for x in members_of(me, rows)} if me else set()


# ── 본인 입력 (2026-10-27 사용자 결정: 팀 최신 DB 기준) ──
# 값은 팀 직원 입력 표에 둔다(팀 database/src/database/employee_form.py 와 같은 표·열): 경험 요약·개발 경력·기술·프로젝트·교육은
# public.employee_input_profiles, 자격은 public.employee_certifications(팀 자격표에 있는 것) + employees.unlisted_certifications(없는 것).
# 팀 표에 자리가 없는 업무 설명·'없음 확인' 표시와, 되돌리기용 처음 팀 표 값(baseline)만 app_ext.employee_self_inputs 에 둔다.
def _split(v: str | None) -> list[str]:
    return [x.strip() for x in (v or '').split('\n') if x.strip()]


def _join(xs: list[str]) -> str | None:
    return '\n'.join(xs) or None


def _team_state(t: db.Tx, employee_id: int) -> dict:
    """팀 표의 지금 값. 되돌리기용으로 그대로 저장해 두었다가 다시 쓸 수 있는 모양"""
    p = t.one("""SELECT experience_summary, development_years, technology_experience, project_experience, learning_history
                 FROM public.employee_input_profiles WHERE employee_id = :e""", e=employee_id)
    if p and p['development_years'] is not None:
        p = dict(p, development_years=float(p['development_years']))
    return {'profile': dict(p) if p else None,
            'certIds': [r['certification_id'] for r in t.all('SELECT certification_id FROM public.employee_certifications WHERE employee_id = :e ORDER BY 1', e=employee_id)],
            'unlisted': t.val('SELECT unlisted_certifications FROM public.employees WHERE employee_id = :e', e=employee_id)}


def _team_values(t: db.Tx, employee_id: int, st: dict) -> dict:
    p = st['profile'] or {}
    certs = [r['title'] for r in t.all("""SELECT c.title FROM public.employee_certifications ec JOIN public.certifications c ON c.cert_id = ec.certification_id
                                         WHERE ec.employee_id = :e ORDER BY c.title""", e=employee_id)] + _split(st['unlisted'])
    if st['profile'] is None:
        # 본인 입력 전에는 사내 DB 의 보유 스킬을 사용 기술 처음 값으로 보여 준다
        tech = [r['name'] for r in t.all("""SELECT s.name FROM public.employee_skills es JOIN public.skill_tags s USING (skill_id)
                                            WHERE es.employee_id = :e ORDER BY s.name""", e=employee_id)]
    else:
        tech = _split(p.get('technology_experience'))
    return {'expSummary': p.get('experience_summary'), 'devYears': p.get('development_years'), 'tech': tech, 'certs': certs,
            'learning': _split(p.get('learning_history')), 'projects': _split(p.get('project_experience'))}


def _write_profile(t: db.Tx, employee_id: int, p: dict) -> None:
    t.run("""INSERT INTO public.employee_input_profiles(employee_id, experience_summary, development_years, technology_experience, project_experience,
                 learning_history, updated_at) VALUES(:e, :ex, :dy, :te, :pe, :lh, now())
             ON CONFLICT (employee_id) DO UPDATE SET experience_summary = EXCLUDED.experience_summary, development_years = EXCLUDED.development_years,
                 technology_experience = EXCLUDED.technology_experience, project_experience = EXCLUDED.project_experience,
                 learning_history = EXCLUDED.learning_history, updated_at = now()""",
          e=employee_id, ex=p.get('experience_summary'), dy=p.get('development_years'), te=p.get('technology_experience'),
          pe=p.get('project_experience'), lh=p.get('learning_history'))


def _write_team(t: db.Tx, employee_id: int, v: dict) -> None:
    _write_profile(t, employee_id, {'experience_summary': v['expSummary'], 'development_years': None if v['devYears'] is None else round(v['devYears'], 2),
                                    'technology_experience': _join(v['tech']), 'project_experience': _join(v['projects']),
                                    'learning_history': _join(v['learning'])})
    # 자격: 팀 자격표 이름과 같으면 연결하고, 없는 자격은 목록 밖 자격 글자로 둔다('SQLD (2023)'처럼 괄호 앞 이름으로 찾음)
    ids = {r['title'].casefold(): r['cert_id'] for r in t.all('SELECT cert_id, title FROM public.certifications')}
    linked: list[int] = []
    unlisted: list[str] = []
    for c in v['certs']:
        cid = ids.get(c.split(' (')[0].strip().casefold())
        if cid and cid not in linked:
            linked.append(cid)
        elif not cid:
            unlisted.append(c)
    _write_certs(t, employee_id, linked, _join(unlisted))


def _write_certs(t: db.Tx, employee_id: int, cert_ids: list[int], unlisted: str | None) -> None:
    t.run('DELETE FROM public.employee_certifications WHERE employee_id = :e', e=employee_id)
    for cid in cert_ids:
        t.run('INSERT INTO public.employee_certifications(employee_id, certification_id) VALUES(:e, :c) ON CONFLICT DO NOTHING', e=employee_id, c=cid)
    t.run('UPDATE public.employees SET unlisted_certifications = :u, updated_at = now() WHERE employee_id = :e', u=unlisted, e=employee_id)


def _restore_team(t: db.Tx, employee_id: int, st: dict) -> None:
    p = st.get('profile')
    if p is None:
        t.run('DELETE FROM public.employee_input_profiles WHERE employee_id = :e', e=employee_id)
    else:
        _write_profile(t, employee_id, p)
    _write_certs(t, employee_id, list(st.get('certIds') or []), st.get('unlisted'))


def _self_of(employee_id: int) -> tuple[dict, bool, datetime | None]:
    """화면에 줄 본인 입력 값(팀 표 + 업무 설명·입력 상태), 직원이 내 정보에서 고쳤는지, 고친 때"""
    with db.tx() as t:
        vals = _team_values(t, employee_id, _team_state(t, employee_id))
        x = t.one('SELECT edited, edited_at FROM app_ext.employee_self_inputs WHERE employee_id = :e', e=employee_id) or {}
    extra = x.get('edited') or {}
    status = {k: 'reported' if vals[k] else 'unprovided' for k in LISTS}
    status.update({k: v for k, v in (extra.get('inputStatus') or {}).items() if v == 'none_confirmed' and not vals.get(k)})
    src = {**vals, 'workDesc': extra.get('workDesc'), 'expStatus': 'reported' if vals['expSummary'] else 'unprovided', 'inputStatus': status}
    src['present'] = bool(src['workDesc'] or vals['expSummary'] or vals['devYears'] is not None or any(vals[k] for k in LISTS))
    return src, x.get('edited_at') is not None, x.get('edited_at')


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
    src, edited, at = _self_of(employee_id)
    has_profile = src['present']
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
        'members': [_ref(x) for x in ms], 'planGroup': {'name': r['dept'], 'id': str(sup['department_id'])} if sup else None,
        'mySupervisor': _ref(sup) if sup else None,
        'profile': {k: src.get(k) for k in ('workDesc', 'expStatus', 'expSummary', 'devYears', 'inputStatus')} if has_profile else None,
        **{k: list(src.get(k) or []) for k in LISTS},
        'evals': _evals(employee_id), 'edited': bool(edited), 'editedAt': at.strftime('%Y-%m-%d') if at else None,
        'education': [f"{x['school_name']} {x['department_name'] or ''} ({EDU_LEVEL.get(x['education_level'], x['education_level'])})".replace('  ', ' ') for x in edu],
    }


# 부서장 화면에 주는 직원 정보: 소속·직급·직위와 부서장 여부만(설계서 공개 범위 · PR #23 리뷰 2026-10-27).
# 평정·본인 입력·학력·입사일·계정 상태 등은 화면에서 숨겨도 응답으로 받을 수 있으므로 보내지 않는다
TEAM_FIELDS = ('id', 'code', 'name', 'role', 'dept', 'parentDept', 'grade', 'position')


def team_view(v: dict) -> dict:
    return {**{k: v.get(k) for k in TEAM_FIELDS}, 'supervisor': bool(v.get('supervisor') and v.get('members'))}


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
    try:
        yrs = None if yrs in ('', None) else float(yrs)
    except (TypeError, ValueError, OverflowError):
        raise ApiError(422, 'DEV_YEARS_RANGE', '개발 경험은 0~50년 사이의 숫자로 적거나 비워 주세요.') from None
    if yrs is not None and not 0 <= yrs <= 50:
        raise ApiError(422, 'DEV_YEARS_RANGE', '개발 경험은 0~50년 사이로 적거나 비워 주세요.')
    lists = {k: [str(x).strip() for x in body.get(k) or [] if str(x).strip()][:20] for k in LISTS}
    none = body.get('noneConfirmed') or {}
    anything = wd or ex or yrs is not None or any(lists[k] or none.get(k) for k in LISTS)
    if anything and not wd:
        raise ApiError(422, 'WORK_DESC_REQUIRED', '업무 설명을 적어 주세요. 본인 입력 정보를 저장할 때 업무 설명은 꼭 있어야 해요.')
    st = lambda k: 'reported' if lists[k] else 'none_confirmed' if none.get(k) else 'unprovided'  # noqa: E731
    new = {'expSummary': ex or None, 'devYears': yrs, **lists}
    extra = {'workDesc': wd or None, 'inputStatus': {k: st(k) for k in LISTS}}
    with db.tx() as t:
        row = t.one('SELECT baseline FROM app_ext.employee_self_inputs WHERE employee_id = :e', e=employee_id)
        # 처음 고칠 때의 팀 표 값을 되돌리기용으로 남긴다(사내 DB 값으로 되돌리기)
        base = row['baseline'] if row and row['baseline'] else _team_state(t, employee_id)
        _write_team(t, employee_id, new)
        if _team_state(t, employee_id) == base and not wd and not any(none.get(k) for k in LISTS):
            # 처음 값과 같아졌고 팀 표 밖 값도 없으면 '직접 고침'이 아니다
            _restore_team(t, employee_id, base)
            t.run('DELETE FROM app_ext.employee_self_inputs WHERE employee_id = :e', e=employee_id)
            return
        t.run("""INSERT INTO app_ext.employee_self_inputs(employee_id, baseline, edited, edited_at) VALUES(:e, :b, :v, now())
                 ON CONFLICT (employee_id) DO UPDATE SET baseline = EXCLUDED.baseline, edited = EXCLUDED.edited, edited_at = now()""",
              e=employee_id, b=db.J(base), v=db.J(extra))


def revert_self(employee_id: int) -> None:
    """사내 DB 값으로 되돌리기: 처음 고치기 전의 팀 표 값으로 되돌리고 팀 표 밖 값(업무 설명 등)도 지운다"""
    with db.tx() as t:
        row = t.one('SELECT baseline FROM app_ext.employee_self_inputs WHERE employee_id = :e', e=employee_id)
        if row and row['baseline']:
            _restore_team(t, employee_id, row['baseline'])
        t.run('DELETE FROM app_ext.employee_self_inputs WHERE employee_id = :e', e=employee_id)


def set_consent(employee_id: int, period: str, consent: bool) -> None:
    with db.tx() as t:
        row = t.one('SELECT consent_default FROM app_ext.employee_evaluations WHERE employee_id = :e AND period = :p', e=employee_id, p=period)
        if not row:
            raise ApiError(404, 'NOT_FOUND', '그 평정을 찾을 수 없어요')
        t.run('UPDATE app_ext.employee_evaluations SET consent = :c, consent_changed_at = now() WHERE employee_id = :e AND period = :p',
              c=None if consent == row['consent_default'] else consent, e=employee_id, p=period)
