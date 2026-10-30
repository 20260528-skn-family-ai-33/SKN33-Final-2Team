"""Coherent fictional employee scenarios. No real identities or model/API calls.

The reviewed plan is external data, not a seed bundled into application startup.
Only TEST_MANUAL records can be planned/applied, using a compare-before-write guard.
"""
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Any

from psycopg import sql

from .employee_form import get_employee_input_form, save_employee_input_form, validate_form_payload

VERSION = 'synthetic-work-profile/v1'
TABLES = ('employees', 'employee_input_profiles', 'employee_skills', 'employee_certifications', 'employee_education_records')
SKILL_NAMES = {
    1: 'SQL 기본 문법 & 조인', 2: 'SQL 쿼리 튜닝 & 인덱스 최적화', 3: 'RDBMS 데이터 모델링',
    5: 'ETL & 데이터 파이프라인', 6: '데이터 웨어하우스 & OLAP', 7: '탐색적 데이터 분석(EDA) & 전처리',
    8: '머신러닝 지도/비지도 학습', 9: 'MLOps & 모델 서빙', 10: '딥러닝 신경망 아키텍처',
    11: 'PyTorch/TensorFlow 딥러닝 구현', 15: '리눅스 환경 및 Bash 스크립팅', 16: 'TCP/IP 네트워크 프로토콜',
    17: '클라우드 컴퓨팅 아키텍처 (AWS/Azure)', 18: '클라우드 IAM & 네트워크 보안',
    19: 'Docker 컨테이너 가상화', 21: 'CI/CD 배포 자동화 파이프라인', 22: 'Python 프로그래밍 & 비동기 I/O',
    24: '운영체제(OS) & 동시성 제어', 25: '컴퓨터 구조 & 메모리 관리', 31: '시스템 프로그래밍 & POSIX API',
    32: '멀티스레딩 & 비동기 동시성', 33: '시스템 & OS 보안 강화', 34: '웹 애플리케이션 취약점 진단',
    35: '네트워크 보안 & 침입 탐지', 36: '데이터 거버넌스 & 보안 규정 준수',
}
# Department codes, never local IDs. An HR department's IT roles refer explicitly
# to HR systems and training operations, not to general HR policy ownership.
DEPARTMENTS = {
    'AIDATA': ('AI데이터센터', ('ai', 'data', 'gis', 'system'),
               ('수질 측정 자료', '시설 점검 기록', '급수 사용량 자료', '민원 분류 자료', '관측소 위치 자료')),
    'HR': ('인재경영실', ('data', 'cloud', 'system', 'security'),
           ('교육 신청 자료', '교육 이수 집계', '학습 포털 운영', '교육 수요 설문', '직원 역량 설문')),
    'BIZ': ('업무시스템팀', ('system', 'data', 'security', 'cloud'),
            ('업무 포털 연계', '전자결재 처리 로그', '시설 신청 서비스', '문서 조회 서비스', '사용자 지원 기록')),
    'INFRA': ('인프라운영팀', ('cloud', 'system', 'security', 'data'),
              ('운영 서버 점검', '서비스 배포 기록', '백업 작업 결과', '접속 장애 기록', '가상망 구성')),
    'DATA': ('데이터운영팀', ('data', 'gis', 'ai', 'system'),
             ('시설 데이터 연계', '관측 자료 적재', '측정값 품질 점검', '데이터 제공 이력', '공간 속성 자료')),
}
ROLES = {
    'data': dict(job='데이터베이스관리자', major='컴퓨터공학과',
                 task='SQL 조회와 테이블 키·중복·누락을 점검하고 적재 및 복구 절차를 관리한다',
                 tools='PostgreSQL·SQL·DBeaver', basic=(1, 3), working=(1, 2, 3, 5), advanced=(1, 2, 3, 5, 6),
                 gap='실행계획을 근거로 병목을 설명하고 데이터 품질 검사를 자동화하는 작업',
                 artifact='조회·적재 검증 보고서', cert='SQL 전문가', dev=(0.25, 1.5, 4)),
    'ai': dict(job='인공지능 엔지니어', major='컴퓨터과학과',
               task='데이터를 정제하고 학습·검증 분리를 확인하며 분류 모델의 오류 사례를 정리한다',
               tools='Python·pandas·scikit-learn', basic=(7, 22), working=(7, 8, 22), advanced=(7, 8, 9, 10, 11, 22),
               gap='운영 데이터 변화에 따른 성능 저하를 감지하고 재학습 기준을 세우는 작업',
               artifact='분류 오류 분석 노트', cert='데이터 분석 전문가', dev=(0.25, 2, 5)),
    'cloud': dict(job='클라우드 시스템 엔지니어', major='정보통신과',
                  task='서버 자원·네트워크 연결·서비스 계정의 접근 범위를 점검하고 운영 기록을 관리한다',
                  tools='Linux·Azure·운영 대시보드', basic=(15, 16), working=(15, 16, 17, 18), advanced=(15, 16, 17, 18, 19, 21),
                  gap='장애 징후와 변경 이력을 연결하여 재발 방지 절차를 수립하는 작업',
                  artifact='구성 변경·복구 점검표', cert='Microsoft 인증: Azure 관리자 보조', dev=(0, 0.5, 2)),
    'system': dict(job='시스템소프트웨어개발자', major='컴퓨터공학과',
                   task='Linux 서비스의 로그 수집·프로세스 상태 점검 도구와 연계 배치 프로그램을 유지보수한다',
                   tools='Python·Bash·Linux 서비스', basic=(15, 22), working=(15, 22, 24, 31), advanced=(15, 22, 24, 25, 31, 32),
                   gap='동시 실행과 실패 재시도에서 중복 처리·자원 누수가 생기지 않도록 검증하는 작업',
                   artifact='실패 복구 재현 기록', cert=None, dev=(0.5, 2.5, 6)),
    'security': dict(job='정보보호전문가', major='정보보호학과',
                     task='계정 권한과 접근 로그를 검토하고 시스템 설정의 보안 점검 및 조치 이력을 관리한다',
                     tools='접근 로그·Linux 점검 도구·네트워크 분석 도구', basic=(16, 36), working=(16, 18, 33, 36), advanced=(16, 18, 33, 34, 35, 36),
                     gap='이상 접근 경보의 오탐 원인을 분석하고 점검 근거를 재현하는 작업',
                     artifact='권한·로그 점검 근거표', cert='Microsoft 인증: 클라우드 및 AI 보안 엔지니어 어소시에이트', dev=(0, 0.5, 2)),
    'gis': dict(job='지리정보시스템기사', major='정보통신과',
                task='시설 좌표·공간 속성 자료를 대조하고 좌표계·중복 위치·누락 속성을 점검한다',
                tools='QGIS·PostgreSQL·Python', basic=(1, 7), working=(1, 3, 5, 7, 22), advanced=(1, 2, 3, 5, 7, 22),
                gap='공간 데이터 정합성 검사를 자동화하고 오류 위치의 원인을 설명하는 작업',
                artifact='좌표·속성 정합성 점검 지도', cert=None, dev=(0.25, 1, 3)),
}
LEVELS = ('기초 실무', '독립 수행', '운영 개선')
FOUNDATIONS = {
    'data': '조인·집계 결과를 설명하고 키·누락 검사를 재현하는 작업',
    'ai': '훈련·검증 데이터를 분리하고 단순 분류 결과를 비교하는 작업',
    'cloud': '접속 실패와 권한 거절을 구분하고 기본 구성도를 읽는 작업',
    'system': '파일·프로세스 오류를 재현하고 로그로 원인을 좁히는 작업',
    'security': '최소 권한 점검표를 적용하고 접근 로그의 정상·거절을 구분하는 작업',
    'gis': '좌표계를 확인하고 공간 자료와 속성 표를 연결하는 작업',
}
SKILL_EVIDENCE = {
    1: '조건·집계·조인 쿼리의 행 수를 원자료와 대조', 2: 'EXPLAIN과 인덱스 전후 조회 비용 비교',
    3: '키·참조 관계와 중복 저장 여부 점검', 5: '파일 적재 배치의 누락·중복·재시도 점검',
    6: '사실·차원 표를 나눠 기간별 집계 쿼리 작성', 7: '결측·중복·이상치와 분포 점검',
    8: '훈련·검증 분리 후 기준 분류 모델의 오류 비교', 9: '모델 버전별 시험 배포와 되돌리기 절차 실행',
    10: '작은 신경망의 층·손실·과적합 양상 비교', 11: 'PyTorch 예제의 학습·검증 루프와 텐서 차원 점검',
    15: 'Bash로 로그·파일 상태를 수집하고 종료 코드 확인', 16: '주소·포트·이름 해석을 나눠 접속 실패 재현',
    17: 'Azure 자원 그룹·가상망·인스턴스 구성 점검', 18: '서비스 계정의 허용·거절 권한 대조',
    19: 'Docker 이미지 버전을 고정해 실행 환경 재현', 21: '배포 전 검사와 실패 시 되돌리기 작업 연결',
    22: 'Python으로 입력 파일을 읽고 오류를 분류하는 스크립트 수정',
    24: '프로세스·파일 잠금과 작업 동시 실행 결과 비교', 25: '메모리·CPU 사용량을 측정해 자원 병목 구분',
    31: 'Linux 파일·프로세스 API 사용 프로그램의 종료·권한 오류 재현',
    32: '복수 작업자의 동시 처리와 공유 자원 충돌 점검', 33: '서비스 계정·파일 권한·설정 점검표 적용',
    34: '시험 환경에서 웹 입력·접근 제어 취약점 사례 재현', 35: '시험 네트워크의 탐지 경보와 실제 접근 로그 대조',
    36: '데이터 접근 목적·보관·공유 범위를 점검표와 대조',
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':')).encode('utf-8')).hexdigest()


def state(conn: Any, employee_id: int) -> dict:
    """Complete preimage hash input; only hashes, never password values, enter plans."""
    result = {}
    for table in TABLES:
        rows = conn.execute(sql.SQL('SELECT to_jsonb(t) row FROM public.{} t WHERE employee_id=%s ORDER BY to_jsonb(t)::text').format(sql.Identifier(table)), (employee_id,)).fetchall()
        result[table] = [r['row'] for r in rows]
    return result


def _duration(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'))


def scenario(employee: dict, ordinal: int, skills: dict[int, str], jobs: dict[str, int], certifications: dict[str, int], *, as_of: date) -> dict:
    """Produce an explicit fictional narrative consistent with tenure and owned skills."""
    if employee['source_type'] != 'TEST_MANUAL':
        raise ValueError('Only TEST_MANUAL fictional employees may be enriched')
    code = employee['department_code']
    if code not in DEPARTMENTS or not employee.get('hire_date'):
        raise ValueError('Known department code and hire date required')
    dept, pool, assets = DEPARTMENTS[code]
    hire = employee['hire_date']
    if isinstance(hire, str):
        hire = date.fromisoformat(hire)
    if hire >= as_of:
        raise ValueError('Scenario requires an employee hired before as_of')
    tenure_days = (as_of - hire).days
    level = min(ordinal % 3, 0 if tenure_days < 365 else 1 if tenure_days < 3 * 365 else 2)
    role_key = pool[ordinal % len(pool)]
    role = ROLES[role_key]
    asset = assets[(ordinal // len(pool)) % len(assets)]
    dev_years = min(_duration(role['dev'][level]), _duration(tenure_days / 365.25))
    by_name = {name: sid for sid, name in skills.items()}
    canonical_skills = role[('basic', 'working', 'advanced')[level]]
    names = [SKILL_NAMES[s] for s in canonical_skills]
    if any(name not in by_name for name in names) or role['job'] not in jobs:
        raise ValueError('Scenario references unavailable job or skill masters')
    skill_ids = [by_name[name] for name in names]
    start = max(hire, as_of - timedelta(days=(45, 180, 365)[level]))
    training_date = start + timedelta(days=min(7, max(0, (as_of - start).days // 4)))
    project_end = as_of - timedelta(days=1)
    phase = ('정해진 절차를 따라 점검하고 결과를 선임에게 확인받는다',
             '반복 작업을 독립 수행하고 예외 사례를 담당자와 조정한다',
             '운영 원인을 분석하고 개선안·회귀 점검을 동료와 검토한다')[level]
    head = employee['is_department_head']
    responsibility = '같은 부서 구성원의 업무 배분·결과 검토를 맡으며, 직접 수행한 기술 범위는 아래 경험으로 제한한다. ' if head else ''
    gap = FOUNDATIONS[role_key] if level == 0 else role['gap']
    tools = role['tools'] + ('·PyTorch·모델 시험 배포 환경' if role_key == 'ai' and level == 2 else '')
    work = f'{dept}에서 {asset} 관련 업무를 담당한다. {role["task"]}. {responsibility}{phase}. 다음 학습 목표는 {gap}이다.'
    exp = f'{hire.isoformat()} 입사 후 현재 {asset} 업무를 수행하고 있다. 개발 경험은 {dev_years}년이며 전체 근속 기간과 구분한다. {phase}. 사용 도구는 {tools}이다. {gap}은 추가 학습이 필요하다.'
    if level == 0 and tenure_days >= 365:
        exp += ' 현재 기술 분야로 전환한 초기 단계이며 이전 근속을 해당 기술의 숙련 경력으로 계산하지 않는다.'
    usage = ('기존 예제를 수정하고 결과를 설명하는 기초 작업', '정해진 범위의 운영·검증 작업을 독립 수행', '실패 원인 분석과 회귀 확인을 포함한 운영 개선')[level]
    tech = '\n'.join(f'{skills[s]} / {start.isoformat()}~{as_of.isoformat()} / {SKILL_EVIDENCE[k]}. 수행 범위: {usage}. 태그 전체의 숙련도 인증을 뜻하지 않는다.' for k,s in zip(canonical_skills,skill_ids))
    if level == 0:
        project = f'업무 프로젝트 독립 수행 이력 없음. {start.isoformat()}~{project_end.isoformat()}에는 {asset} 점검 예제를 따라 실행하고 {role["artifact"]}의 일부를 작성했다. 설계·배포 책임은 맡지 않았다.'
    else:
        project = f'{start.isoformat()}~{project_end.isoformat()} / {asset} 개선 / 역할: {usage}. 산출물: {role["artifact"]}. 정상·누락·실패 입력을 재현했다. 실제 서비스 성과 수치는 가정하지 않는다.'
    learning = f'{training_date.isoformat()} / {asset} {LEVELS[level]} 실습 / 사내 실습교육(가상) / {4 + level * 4}시간 / 수료 / {role["artifact"]} 예제를 제출했다.'
    cert_name = role['cert'] if level == 2 and ordinal % 2 == 0 and tenure_days >= 3 * 365 else None
    if cert_name and cert_name not in certifications:
        raise ValueError('Scenario certification master missing')
    cert_ids = [] if cert_name is None else [certifications[cert_name]]
    note = f'{VERSION}; synthetic=true; as_of={as_of.isoformat()}; persona={code}/{role_key}/{ordinal:02d}; source=Codex authored fictional scenario, not submitted human history; '
    note += '자격 없음 확인.' if not cert_ids else f'가상 보유 자격: {cert_name}; 취득 설정일={training_date.isoformat()}; 실제 취득 증빙 아님.'
    payload = {'employee': {'job_id': jobs[role['job']], 'planned_project_description': work, 'unlisted_certifications': None},
               'skill_ids': skill_ids, 'certification_ids': cert_ids,
               'profile': {'experience_summary': exp, 'development_years': str(dev_years), 'technology_experience': tech,
                           'project_experience': project, 'learning_history': learning, 'submission_note': note}}
    validate_form_payload(payload)
    return {'role': role_key, 'level': LEVELS[level], 'asset': asset, 'synthetic': True, 'payload': payload}


def plan(conn: Any, *, as_of: date, expected_count: int = 100) -> dict:
    employees = conn.execute("""SELECT e.employee_id,e.source_type,e.hire_date,e.department_start_date,e.is_department_head,
        d.department_code FROM public.employees e JOIN public.departments d USING(department_id)
        WHERE e.source_type='TEST_MANUAL' ORDER BY d.department_code,e.employee_id""").fetchall()
    if len(employees) != expected_count:
        raise ValueError('Unexpected synthetic employee count; review the target set')
    skills = {r['skill_id']: r['name'] for r in conn.execute('SELECT skill_id,name FROM public.skill_tags').fetchall()}
    jobs = {r['title']: r['job_id'] for r in conn.execute('SELECT job_id,title FROM public.jobs').fetchall()}
    certs = {r['title']: r['cert_id'] for r in conn.execute('SELECT cert_id,title FROM public.certifications').fetchall()}
    majors = {r['title']: r['major_id'] for r in conn.execute('SELECT major_id,title FROM public.majors').fetchall()}
    entries = []
    counts = {}
    for e in employees:
        ordinal = counts.get(e['department_code'], 0)
        counts[e['department_code']] = ordinal + 1
        item = scenario(e, ordinal, skills, jobs, certs, as_of=as_of)
        edu = conn.execute('SELECT education_record_id,department_name,major_id FROM public.employee_education_records WHERE employee_id=%s', (e['employee_id'],)).fetchall()
        matching = [r for r in edu if r['major_id'] is None and r['department_name'] in majors]
        if len(matching) == 1:
            item['payload']['education'] = {'education_record_id': str(matching[0]['education_record_id']), 'major_id': majors[matching[0]['department_name']]}
        entries.append({'employee_id': e['employee_id'], 'before_sha256': digest(state(conn, e['employee_id'])), **item})
    return {'version': VERSION, 'synthetic': True, 'as_of': as_of.isoformat(), 'expected_count': expected_count, 'entries': entries}


def _validate_entry(entry: dict) -> dict:
    if set(entry) != {'employee_id', 'before_sha256', 'role', 'level', 'asset', 'synthetic', 'payload'} or entry['synthetic'] is not True:
        raise ValueError('Unexpected synthetic plan entry')
    raw = entry['payload']
    if set(raw) - {'employee', 'profile', 'skill_ids', 'certification_ids', 'education'}:
        raise ValueError('Unexpected payload fields')
    if set(raw.get('employee', {})) != {'job_id', 'planned_project_description', 'unlisted_certifications'}:
        raise ValueError('Identity, organization, dates and permissions are immutable')
    if set(raw.get('profile', {})) != {'experience_summary', 'development_years', 'technology_experience', 'project_experience', 'learning_history', 'submission_note'}:
        raise ValueError('Complete fictional profile fields required; preferences are preserved')
    if 'education' in raw and set(raw['education']) != {'education_record_id', 'major_id'}:
        raise ValueError('Only an existing education major link may change')
    if not raw['profile']['submission_note'].startswith(VERSION + '; synthetic=true;'):
        raise ValueError('Fictional provenance is required')
    result = validate_form_payload(raw)
    if not result['skill_ids'] or any(not result['profile'].get(k) for k in ('experience_summary', 'technology_experience', 'project_experience', 'learning_history')):
        raise ValueError('Fictional scenario evidence must not be blank')
    return result


def _matches(current: dict, payload: dict) -> bool:
    for section in ('employee', 'profile'):
        for key, value in payload[section].items():
            if current[section].get(key) != value:
                return False
    if sorted(current['skill_ids']) != sorted(payload['skill_ids']) or sorted(current['certification_ids']) != sorted(payload['certification_ids']):
        return False
    if 'education' in payload:
        edu = payload['education']
        row = next((r for r in current['education_records'] if str(r['education_record_id']) == str(edu['education_record_id'])), None)
        if not row or row['major_id'] != edu['major_id']:
            return False
    return True


def apply_plan(conn: Any, reviewed: dict, *, apply: bool = False, expected_count: int = 100) -> dict:
    """Validate every target before any writes, then save atomically or roll back preview."""
    if set(reviewed) != {'version', 'synthetic', 'as_of', 'expected_count', 'entries'} or reviewed['version'] != VERSION or reviewed['synthetic'] is not True:
        raise ValueError('Unsupported synthetic plan')
    entries = reviewed['entries']
    ids = [r['employee_id'] for r in entries]
    if reviewed['expected_count'] != expected_count or len(ids) != expected_count or len(set(ids)) != len(ids) or any(type(x) is not int or x <= 0 for x in ids):
        raise ValueError('Unexpected or duplicate target IDs')
    changed = []
    with conn.transaction(force_rollback=not apply):
        if apply:
            for table in TABLES:
                conn.execute(sql.SQL('LOCK TABLE public.{} IN SHARE ROW EXCLUSIVE MODE').format(sql.Identifier(table)))
        actual = conn.execute("SELECT employee_id FROM public.employees WHERE source_type='TEST_MANUAL' ORDER BY employee_id").fetchall()
        if {r['employee_id'] for r in actual} != set(ids):
            raise ValueError('Target set changed or contains a protected human employee')
        validated = []
        for entry in entries:
            payload = _validate_entry(entry)
            current = get_employee_input_form(conn, entry['employee_id'])
            if current['employee']['source_type'] != 'TEST_MANUAL':
                raise ValueError('Protected non-synthetic employee')
            job = conn.execute('SELECT title FROM public.jobs WHERE job_id=%s', (payload['employee']['job_id'],)).fetchone()
            if not job:
                raise ValueError('Unknown job')
            if _matches(current, payload) and conn.execute('SELECT job_title FROM public.employees WHERE employee_id=%s', (entry['employee_id'],)).fetchone()['job_title'] == job['title']:
                continue
            if digest(state(conn, entry['employee_id'])) != entry['before_sha256']:
                raise ValueError('Employee data changed after plan; re-review before applying')
            if 'education' in payload:
                edu = payload['education']
                valid = conn.execute('''SELECT 1 FROM public.employee_education_records e JOIN public.majors m ON m.title=e.department_name
                    WHERE e.employee_id=%s AND e.education_record_id=%s AND m.major_id=%s''',
                    (entry['employee_id'], edu['education_record_id'], edu['major_id'])).fetchone()
                if not valid:
                    raise ValueError('Education link must match its existing department name exactly')
            validated.append((entry['employee_id'], payload, job['title']))
        # Preview never writes. SQL constraints are exercised by applying to a clone.
        if apply:
            for eid, payload, job_title in validated:
                save_employee_input_form(conn, eid, payload)
                conn.execute('UPDATE public.employees SET job_title=%s WHERE employee_id=%s', (job_title, eid))
                changed.append(eid)
        else:
            changed = [eid for eid, _, _ in validated]
    return {'version': VERSION, 'employees': len(ids), 'changed_count': len(changed), 'applied': apply, 'paid_api_calls': 0}
