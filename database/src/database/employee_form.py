"""Employee form persistence for the trusted DB layer. No network, AI or catalog writes.

Omitted fields keep their values; explicit null clears nullable fields. Lists replace
only the supplied employee's skill/credential links. Human experience stays verbatim.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import UUID

from psycopg import sql
from psycopg.types.json import Jsonb

EMPLOYEE_FIELDS = (
    'name', 'email', 'employee_number', 'institution_id', 'department_id',
    'job_grade_id', 'job_id', 'is_department_head', 'is_degree_seeker',
    'hire_date', 'department_start_date', 'unlisted_certifications',
    'planned_project_description',
)
PROFILE_FIELDS = (
    'experience_summary', 'development_years', 'technology_experience',
    'project_experience', 'learning_history', 'learning_preferences', 'submission_note',
)
EDUCATION_FIELDS = (
    'education_record_id', 'school_name', 'education_level', 'department_name',
    'major_id', 'enrollment_date', 'graduation_date',
)
EDUCATION_LEVELS = {
    'middle_school_or_lower', 'high_school', 'associate', 'bachelor',
    'master', 'doctorate', 'other',
}
PREFERENCE_FIELDS = {
    'goal_status', 'goal_text', 'deliverable', 'credential_plan', 'desired_credential',
    'weekly_hours', 'duration_weeks', 'budget_won', 'preferred_formats',
}
DATE_FIELDS = {'hire_date', 'department_start_date', 'enrollment_date', 'graduation_date'}
FORM_TEXT_FIELDS = {
    '경험 요약': 'experience_summary', '기술별 사용 경험': 'technology_experience',
    '프로젝트 경험': 'project_experience', '교육 이력': 'learning_history',
    '전달 메모': 'submission_note',
}
FORM_PREFERENCE_FIELDS = {
    '목표 상태': 'goal_status', '목표 내용': 'goal_text', '희망 산출물': 'deliverable',
    '자격 취득 계획': 'credential_plan', '취득 희망 자격': 'desired_credential',
    '주당 학습 시간': 'weekly_hours', '학습 기간': 'duration_weeks', '학습 예산': 'budget_won',
}


def _mapping(value: Any, allowed: set[str], section: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise ValueError(section + ': unsupported fields or object required')
    return deepcopy(value)


def _identifier(value: Any, *, bigint: bool = False) -> int:
    if bigint:
        if isinstance(value, bool) or not isinstance(value, (int, str)) or (isinstance(value, str) and not value.isdecimal()):
            raise ValueError('Use a positive BIGINT reference ID')
        number = int(value)
        if not 0 < number <= 9223372036854775807:
            raise ValueError('BIGINT reference ID is out of range')
        return number
    from .db_client import user_id_value
    return user_id_value(value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or '\x00' in value or len(value) > 20000:
        raise ValueError('Text must be a string of at most 20000 characters without NUL')
    return value if value.strip() else None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError('Use a date without a time')
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('Use an ISO YYYY-MM-DD date')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError('Use a valid ISO YYYY-MM-DD date') from None
    if parsed.isoformat() != value:
        raise ValueError('Use an ISO YYYY-MM-DD date')
    return parsed


def _number(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Use a finite non-negative number') from None
    if isinstance(value, bool) or not number.is_finite() or number < 0:
        raise ValueError('Use a finite non-negative number')
    return number


def validate_preferences(value: Any, *, complete: bool = False) -> dict[str, Any]:
    result = _mapping({} if value is None else value, PREFERENCE_FIELDS, 'learning_preferences')
    for key, item in result.items():
        if key in ('weekly_hours', 'duration_weeks', 'budget_won'):
            number = _number(item)
            if number is not None and (number > Decimal('1e15') or number.quantize(Decimal('.01')) != number):
                raise ValueError('Learning numeric values must have at most two decimal places and fit the supported range')
            result[key] = None if number is None else (int(number) if number == number.to_integral() else float(number))
        elif key == 'preferred_formats':
            choices = {'직접 실습', '공식 문서', '영상', '도서', '따라 하기 실습'}
            if item is None:
                result[key] = []
            elif not isinstance(item, list) or any(not isinstance(x, str) or x not in choices for x in item) or len(item) != len(set(item)):
                raise ValueError('Choose distinct supported learning formats')
        else:
            result[key] = _text(item)
    if result.get('goal_status') not in (None, '미정', '정함'):
        raise ValueError('Unsupported goal_status')
    if result.get('credential_plan') not in (None, '미정', '계획 없음', '종류 미정', '구체적 계획'):
        raise ValueError('Unsupported credential_plan')
    if complete and result.get('goal_status') == '정함' and not result.get('goal_text'):
        raise ValueError('goal_text is required when goal_status is 정함')
    if complete and result.get('credential_plan') == '구체적 계획' and not result.get('desired_credential'):
        raise ValueError('desired_credential is required for a specific credential plan')
    return result


def validate_form_payload(payload: Any) -> dict[str, Any]:
    result = _mapping(payload, {'employee', 'skill_ids', 'certification_ids', 'education', 'profile'}, 'form')
    if not result:
        raise ValueError('No employee form fields supplied')
    for section, allowed in (('employee', EMPLOYEE_FIELDS), ('profile', PROFILE_FIELDS), ('education', EDUCATION_FIELDS)):
        if section not in result:
            continue
        fields = _mapping(result[section], set(allowed), section)
        for key, value in fields.items():
            if key in DATE_FIELDS:
                fields[key] = _date(value)
            elif key in ('department_id', 'job_grade_id', 'job_id', 'major_id'):
                fields[key] = None if value is None else _identifier(value, bigint=key in ('department_id', 'job_grade_id'))
            elif key in ('is_department_head', 'is_degree_seeker'):
                if type(value) is not bool:
                    raise ValueError('Employee flags must be booleans')
            elif key == 'development_years':
                number = _number(value)
                if number is not None and (number > Decimal('9999.99') or number.quantize(Decimal('.01')) != number):
                    raise ValueError('development_years must fit NUMERIC(6,2) without rounding')
                fields[key] = number
            elif key == 'learning_preferences':
                fields[key] = validate_preferences(value)
            elif key == 'education_record_id':
                try:
                    fields[key] = UUID(str(value))
                except (ValueError, TypeError):
                    raise ValueError('Use a valid education_record_id') from None
            else:
                fields[key] = _text(value)
        if 'name' in fields and (fields['name'] is None or len(fields['name']) > 50):
            raise ValueError('Employee name must contain 1 to 50 characters')
        if fields.get('education_level') is not None and fields['education_level'] not in EDUCATION_LEVELS:
            raise ValueError('Unsupported education_level')
        if section == 'education' and 'education_record_id' not in fields and not (fields.get('school_name') and fields.get('education_level')):
            raise ValueError('New education requires school_name and education_level')
        result[section] = fields
    for key in ('skill_ids', 'certification_ids'):
        if key in result:
            if not isinstance(result[key], list):
                raise ValueError(key + ' must be an array; omit it to preserve existing links')
            result[key] = [_identifier(x) for x in result[key]]
            if len(result[key]) != len(set(result[key])):
                raise ValueError('Duplicate IDs in ' + key)
    return result


def _update(conn: Any, table: str, key: str, identity: Any, fields: dict[str, Any]) -> None:
    if not fields:
        return
    assignments = sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in fields)
    conn.execute(sql.SQL('UPDATE public.{} SET {} WHERE {}=%s').format(
        sql.Identifier(table), assignments, sql.Identifier(key)), [*fields.values(), identity])


def _save_education(conn: Any, employee_id: int, fields: dict[str, Any]) -> None:
    fields = dict(fields)
    record_id = fields.pop('education_record_id', None)
    if record_id is None:
        matches = conn.execute('''SELECT education_record_id FROM public.employee_education_records
            WHERE employee_id=%s AND school_name=%s AND education_level=%s
            AND department_name IS NOT DISTINCT FROM %s FOR UPDATE''',
            (employee_id, fields['school_name'], fields['education_level'], fields.get('department_name'))).fetchall()
        if len(matches) > 1:
            raise ValueError('Ambiguous education records; supply education_record_id')
        if matches:
            record_id = matches[0]['education_record_id']
    if record_id is not None:
        owner = conn.execute('SELECT employee_id FROM public.employee_education_records WHERE education_record_id=%s FOR UPDATE', (record_id,)).fetchone()
        if owner is None or owner['employee_id'] != employee_id:
            raise ValueError('Education record does not belong to this employee')
        _update(conn, 'employee_education_records', 'education_record_id', record_id, fields)
        return
    names = ['employee_id', *fields]
    conn.execute(sql.SQL('INSERT INTO public.employee_education_records ({}) VALUES ({})').format(
        sql.SQL(',').join(map(sql.Identifier, names)), sql.SQL(',').join(sql.Placeholder() for _ in names)),
        [employee_id, *fields.values()])


def get_employee_input_form(conn: Any, employee_id: int) -> dict[str, Any]:
    employee_id = _identifier(employee_id)
    names = sql.SQL(',').join(map(sql.Identifier, ('employee_id', 'source_type', *EMPLOYEE_FIELDS)))
    employee = conn.execute(sql.SQL('SELECT {} FROM public.employees WHERE employee_id=%s').format(names), (employee_id,)).fetchone()
    if employee is None:
        raise ValueError('Employee does not exist')
    profile = conn.execute('SELECT * FROM public.employee_input_profiles WHERE employee_id=%s', (employee_id,)).fetchone()
    return {
        'employee': employee,
        'skill_ids': [r['skill_id'] for r in conn.execute('SELECT skill_id FROM public.employee_skills WHERE employee_id=%s ORDER BY skill_id', (employee_id,)).fetchall()],
        'certification_ids': [r['certification_id'] for r in conn.execute('SELECT certification_id FROM public.employee_certifications WHERE employee_id=%s ORDER BY certification_id', (employee_id,)).fetchall()],
        'education_records': conn.execute('SELECT * FROM public.employee_education_records WHERE employee_id=%s ORDER BY education_record_id', (employee_id,)).fetchall(),
        'profile': profile or {},
    }


def save_employee_input_form(conn: Any, employee_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Operator-only full form import. Call with a trusted server/admin connection."""
    employee_id = _identifier(employee_id)
    data = validate_form_payload(payload)
    with conn.transaction():
        if not conn.execute('SELECT employee_id FROM public.employees WHERE employee_id=%s FOR UPDATE', (employee_id,)).fetchone():
            raise ValueError('Employee does not exist')
        profile = data.get('profile', {})
        if 'learning_preferences' in profile:
            previous = conn.execute('SELECT learning_preferences FROM public.employee_input_profiles WHERE employee_id=%s', (employee_id,)).fetchone()
            original = payload['profile']['learning_preferences']
            preferences = {} if original is None else {**(previous['learning_preferences'] if previous else {}), **profile['learning_preferences']}
            profile['learning_preferences'] = Jsonb(validate_preferences(preferences, complete=True))
        if data.get('employee'):
            current_number = conn.execute('SELECT employee_number FROM public.employees WHERE employee_id=%s', (employee_id,)).fetchone()['employee_number']
            candidate_number = data['employee'].get('employee_number', current_number)
            if candidate_number is None or not str(candidate_number).strip():
                raise ValueError('사번이 없는 기존 계정은 직원정보 저장 시 실제 사번을 함께 입력해야 합니다.')
            _update(conn, 'employees', 'employee_id', employee_id, {**data['employee'], 'updated_at': datetime.now(timezone.utc)})
        for key, table, column in (('skill_ids', 'employee_skills', 'skill_id'), ('certification_ids', 'employee_certifications', 'certification_id')):
            if key in data:
                conn.execute(sql.SQL('DELETE FROM public.{} WHERE employee_id=%s').format(sql.Identifier(table)), (employee_id,))
                for identity in data[key]:
                    conn.execute(sql.SQL('INSERT INTO public.{} (employee_id,{}) VALUES (%s,%s)').format(sql.Identifier(table), sql.Identifier(column)), (employee_id, identity))
        if 'education' in data:
            _save_education(conn, employee_id, data['education'])
        if profile:
            names = ['employee_id', *profile]
            updates = sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(k), sql.Identifier(k)) for k in profile)
            conn.execute(sql.SQL('INSERT INTO public.employee_input_profiles ({}) VALUES ({}) ON CONFLICT(employee_id) DO UPDATE SET {}, updated_at=now()').format(
                sql.SQL(',').join(map(sql.Identifier, names)), sql.SQL(',').join(sql.Placeholder() for _ in names), updates),
                [employee_id, *profile.values()])
        return get_employee_input_form(conn, employee_id)


def _provided(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def profile_from_form_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Map labels, not row numbers. Blank sheet cells preserve saved values."""
    profile = {target: fields[label] for label, target in FORM_TEXT_FIELDS.items() if _provided(fields.get(label))}
    if _provided(fields.get('개발 경험 연수')):
        profile['development_years'] = fields['개발 경험 연수']
    preferences = {target: fields[label] for label, target in FORM_PREFERENCE_FIELDS.items() if _provided(fields.get(label))}
    formats = [fields[label] for label in ('선호 학습 방식 1', '선호 학습 방식 2') if _provided(fields.get(label))]
    if formats:
        preferences['preferred_formats'] = formats
    if preferences:
        profile['learning_preferences'] = preferences
    return validate_form_payload({'profile': profile})['profile']


def record_from_form_fields(fields: Mapping[str, Any], db_values: Mapping[str, Any]) -> dict[str, Any]:
    """Join a person's form labels and DB-preview labels without hardcoded row numbers.

    Dates must be exported as ISO strings. Never parse free-text experiences or map
    unknown names to guessed IDs. This builds data only; it does not read the Sheet.
    """
    employee_id = _identifier(db_values.get('employees.employee_id'))
    employee = {}
    for key in EMPLOYEE_FIELDS:
        value = db_values.get('employees.' + key)
        if _provided(value):
            if key in ('is_department_head', 'is_degree_seeker') and isinstance(value, str):
                if value.upper() not in ('TRUE', 'FALSE'):
                    raise ValueError('Employee flags must be TRUE or FALSE')
                value = value.upper() == 'TRUE'
            employee[key] = value
    if fields.get('직무 ★') == '해당 없음':
        employee['job_id'] = None
    payload = {'employee': employee, 'profile': profile_from_form_fields(fields)}
    for label, section, field, count in (
        ('보유 기술', 'skill_ids', 'employee_skills.skill_id', 5),
        ('보유 자격', 'certification_ids', 'employee_certifications.certification_id', 3),
    ):
        identities = [db_values.get(f'{field} ({n})') for n in range(1, count + 1)
                      if _provided(db_values.get(f'{field} ({n})'))]
        first = fields.get(label + ' 1 ★')
        if first == '없음' and identities:
            raise ValueError('None cannot be combined with selected possession IDs')
        if identities or first == '없음':
            payload[section] = identities
    education = {key: db_values['employee_education_records.' + key]
                 for key in EDUCATION_FIELDS if _provided(db_values.get('employee_education_records.' + key))}
    if education:
        payload['education'] = education
    return {'employee_id': employee_id, **validate_form_payload(payload)}
