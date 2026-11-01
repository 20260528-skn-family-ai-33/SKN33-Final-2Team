"""V_2 설문 저장 실험. 기존 문항 표와 분리해 초안 JSON의 전용 키를 사용한다."""
from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4
from typing import Any

from app.agents.survey_generation import generate_survey

KEY = 'v2Survey'


class StoreError(ValueError):
    pass


def _owned(t: Any, employee_id: int, project_id: str, lock: bool = False) -> dict:
    row = t.one('SELECT draft_choices FROM public.projects '
                "WHERE project_id = CAST(:p AS uuid) AND employee_id = :e AND status = 'DRAFTING'"
                + (' FOR UPDATE' if lock else ''), p=project_id, e=employee_id)
    if row is None:
        raise StoreError('본인의 작성 중인 로드맵을 찾을 수 없습니다.')
    raw = row.get('draft_choices')
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise StoreError('기존 초안 형식을 확인해 주세요. 기존 기록은 변경하지 않았습니다.')
    return raw


def _write(t: Any, employee_id: int, project_id: str, value: dict, *, reset_draft: dict | None = None) -> None:
    # 전용 키만 갱신해 기존 draft·진단·로드맵 기록을 보존한다.
    expression="jsonb_set(coalesce(draft_choices, '{}'::jsonb), '{v2Survey}', CAST(:value AS jsonb), true)"
    params={'value':json.dumps(value,ensure_ascii=False),'p':project_id,'e':employee_id}
    if reset_draft is not None:
        expression=f"jsonb_set(jsonb_set({expression}, '{{draft}}', CAST(:draft AS jsonb), true), '{{draftPlan}}', 'null'::jsonb, true)"
        params['draft']=json.dumps(reset_draft,ensure_ascii=False)
    count=t.run(f"UPDATE public.projects SET draft_choices = {expression}, updated_at = now() WHERE project_id = CAST(:p AS uuid) AND employee_id = :e AND status = 'DRAFTING'",**params)
    if count != 1:
        raise StoreError('저장 대상이 변경되었습니다. 다시 조회해 주세요.')


def save_generated(t: Any, employee_id: int, project_id: str, project: dict,
                   selection: dict, profile: dict, result: dict, *, replace_generation_id: str | None = None) -> dict:
    """모델 호출 후 짧은 트랜잭션에서 실행한다. 기존 V_2 설문을 덮어쓰지 않는다."""
    checked = generate_survey(project, selection, profile, lambda *_: result)
    raw = _owned(t, employee_id, project_id, lock=True)
    existing = raw.get(KEY)
    if existing is not None and (not replace_generation_id or not isinstance(existing, dict) or existing.get('generationId') != replace_generation_id):
        raise StoreError('설문이 이미 있거나 다른 창에서 변경됐습니다. 다시 조회해 주세요.')
    if existing is None and replace_generation_id is not None:
        raise StoreError('기존 설문이 변경됐습니다. 다시 조회해 주세요.')
    snapshot = {key: deepcopy(project.get(key)) for key in ('goal', 'projectSummary', 'desiredCompetencies', 'details', 'projectFile', 'projectSourceHash') if key in project}
    value = {'version': 1, 'generationId': str(uuid4()), 'project': snapshot,
             'selection': deepcopy(selection), 'profile': deepcopy(profile),
             'survey': checked, 'answers': {}, 'completed': False}
    reset=None
    if isinstance(raw.get('draft'),dict):
        from app.services.drafts import clear_from
        reset=deepcopy(raw['draft']);clear_from(reset,'quiz');reset['genPrefs']=None
    _write(t, employee_id, project_id, value, reset_draft=reset)
    return deepcopy(value)


def read(t: Any, employee_id: int, project_id: str) -> dict | None:
    """서버 전용: 정답을 포함하므로 클라이언트에는 public_view 결과만 전달한다."""
    value = _owned(t, employee_id, project_id).get(KEY)
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('version') != 1:
        raise StoreError('지원하지 않는 설문 저장 형식입니다.')
    return deepcopy(value)


def save_answers(t: Any, employee_id: int, project_id: str, generation_id: str,
                 answers: dict, *, complete: bool = False) -> dict:
    raw = _owned(t, employee_id, project_id, lock=True)
    value = deepcopy(raw.get(KEY))
    if not isinstance(value, dict) or value.get('version') != 1 or value.get('generationId') != generation_id:
        raise StoreError('문항이 변경되었거나 없습니다. 다시 조회해 주세요.')
    allowed = {}
    for group in value['survey']['groups']:
        for kind in ('surveys', 'quizzes'):
            for question in group[kind]:
                allowed[question['id']] = range(1, 6) if kind == 'surveys' else range(5)
    if not isinstance(answers, dict) or any(key not in allowed for key in answers):
        raise StoreError('현재 설문에 없는 응답입니다.')
    if any(type(answer) is not int or answer not in allowed[key] for key, answer in answers.items()):
        raise StoreError('설문은 1~5, 퀴즈는 0~4 중 하나를 선택해 주세요.')
    survey_ids = {q['id'] for group in value['survey']['groups'] for q in group['surveys']}
    if any(key not in survey_ids for key in answers) and not survey_ids.issubset(answers):
        raise StoreError('설문을 모두 완료한 뒤 퀴즈를 진행해 주세요.')
    if complete and set(answers) != set(allowed):
        raise StoreError('모든 문항 선택을 완료해 주세요.')
    changed=value.get('answers')!=answers
    reset=None
    if changed:
        for field in ('recommendations','resourceChoices','skillOrder','durationEstimates','courseRecommendations','activityProposal','activityVersions','materialsSelectionKey','learningOutcomes'):
            value.pop(field,None)
        if isinstance(raw.get('draft'),dict):
            from app.services.drafts import clear_from
            reset=deepcopy(raw['draft']);clear_from(reset,'gen');reset['genPrefs']=None
    value['answers'] = dict(answers)
    value['completed'] = complete or (bool(value.get('completed')) and not changed)
    _write(t, employee_id, project_id, value, reset_draft=reset)
    return value


def public_view(value: dict) -> dict:
    """프로필·정답·해설을 제외한 응답 전 화면용 데이터."""
    survey = deepcopy(value['survey'])
    for group in survey['groups']:
        for question in group['quizzes']:
            question.pop('answer', None)
            question.pop('explain', None)
            for key in ('concept', 'questionType', 'difficulty'):
                question.pop(key, None)
    return {'generationId': value['generationId'], **survey,
            'answers': deepcopy(value['answers']), 'completed': value['completed']}

def save_recommendations(t: Any, employee_id: int, project_id: str, generation_id: str, result: dict, *, course: str | None = None, replace: bool = False) -> dict:
    raw = _owned(t, employee_id, project_id, lock=True)
    current = deepcopy(raw.get(KEY))
    if not isinstance(current, dict) or current.get('generationId') != generation_id or not current.get('completed'):
        raise StoreError('완료한 사전 점검이 변경되었습니다. 다시 확인해 주세요.')
    from app.services.course_recommendations import scope_view, merge_scope
    base = deepcopy(current)
    current = scope_view(current, course, (((raw.get('draft') or {}).get('gen') or {}).get('options') or {}).get(course))
    if current.get('recommendations') and not replace:
        return current
    current['recommendations'] = {'id': str(uuid4()), **deepcopy(result)}
    current['resourceChoices'] = {row['name']: {'course': row['selectedCourse'], 'books': list(row['selectedBooks']), 'enabled': True if current.get('skillSelectionKey') else (base.get('resourceChoices') or {}).get(row['name'], {}).get('enabled', True)} for row in result['skills']}
    names = [row['name'] for row in result['skills']]
    current['skillOrder'] = [name for name in (current.get('skillOrder') or names) if name in names]
    current.pop('learningOutcomes', None)
    current.pop('activityProposal', None)
    current.pop('activityVersions', None)
    current.pop('materialsSelectionKey', None)
    current['durationEstimates'] = {}
    _write(t, employee_id, project_id, merge_scope(base, current), reset_draft=deepcopy(raw.get('draft')) if isinstance(raw.get('draft'),dict) else None)
    return current


def save_resource_choices(t: Any, employee_id: int, project_id: str, generation_id: str,
                          recommendation_id: str, choices: dict, *, skill_order: list[str] | None = None, course: str | None = None) -> dict:
    from app.agents.resource_recommendations import validate_choices, validate_skill_order
    raw = _owned(t, employee_id, project_id, lock=True)
    current = deepcopy(raw.get(KEY))
    if not isinstance(current, dict) or current.get('generationId') != generation_id or not current.get('completed'):
        raise StoreError('완료한 사전 점검이 변경되었습니다.')
    from app.services.course_recommendations import scope_view, merge_scope
    base = deepcopy(current)
    current = scope_view(current, course, (((raw.get('draft') or {}).get('gen') or {}).get('options') or {}).get(course))
    recommendations = current.get('recommendations')
    if not recommendations or recommendations.get('id') != recommendation_id:
        raise StoreError('추천 자료가 변경되었습니다. 다시 조회해 주세요.')
    validate_choices(recommendations, choices)
    order = skill_order if skill_order is not None else current.get('skillOrder', [row['name'] for row in recommendations['skills']])
    validate_skill_order(recommendations, order)
    if current.get('resourceChoices')!=choices or current.get('skillOrder')!=list(order):
        for field in ('activityProposal','activityVersions','learningOutcomes','materialsSelectionKey'):
            current.pop(field,None)
        current['durationEstimates']={name:estimate for name,estimate in (current.get('durationEstimates') or {}).items()
            if name in choices and estimate.get('course')==choices[name].get('course') and sorted(estimate.get('books') or [])==sorted(choices[name].get('books') or [])}
    current['skillOrder'] = list(order)
    current['resourceChoices'] = deepcopy(choices)
    from app.services.duration_proposals import calculate_durations
    selected_option=((((raw.get('draft') or {}).get('gen') or {}).get('options') or {}).get(course) or {})
    if current.get('project') and course:
        current['durationEstimates']=calculate_durations(current['project'],recommendations,choices,list(order),selected_option.get('weeklyHours') or 4)

    if course:
        from app.services.activity_selection import materials_key
        current['materialsSelectionKey'] = materials_key(current)
    _write(t, employee_id, project_id, merge_scope(base, current), reset_draft=deepcopy(raw.get('draft')) if isinstance(raw.get('draft'),dict) else None)
    return current


def save_duration_proposals(t: Any, employee_id: int, project_id: str, generation_id: str,
                            recommendation_id: str, proposals: dict, *, course: str | None = None) -> dict:
    raw = _owned(t, employee_id, project_id, lock=True)
    from app.services.course_recommendations import scope_view, merge_scope
    base = deepcopy(raw.get(KEY))
    current = scope_view(base, course, (((raw.get('draft') or {}).get('gen') or {}).get('options') or {}).get(course)) if isinstance(base, dict) else None
    if not isinstance(current, dict) or current.get('generationId') != generation_id or not current.get('completed') or (current.get('recommendations') or {}).get('id') != recommendation_id:
        raise StoreError('점검 또는 추천이 변경됐습니다. 다시 조회해 주세요.')
    current['durationEstimates'] = {**current.get('durationEstimates', {}), **deepcopy(proposals)}
    _write(t, employee_id, project_id, merge_scope(base, current))
    return current
