"""프로젝트 기반 사전 점검·자료 추천·활동 선택 API."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from threading import Lock
from uuid import UUID

from fastapi import Depends, APIRouter
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt

from app import db
from app.auth import Account, require_employee
from app.agents import runtime
from app.errors import ApiError
from app.services import profile
from app.services.drafts import doc_summary
from app.agents.skill_selection import SelectionError, select_from_catalog
from app.agents.survey_generation import SurveyError, generate_survey, profile_input
from app.services.survey_store import StoreError, public_view, read, save_answers, save_generated, save_recommendations, save_resource_choices, save_duration_proposals
from app.agents.resource_recommendations import RecommendationError, recommend_from_catalog

# 독립 실험 서버는 단일 worker로 실행한다. 동시 유료 생성을 거절한다.
_generation_lock = Lock()


def project_input(t, employee_id: int, project_id: str) -> dict:
    row = t.one("SELECT draft_choices FROM public.projects WHERE project_id = CAST(:p AS uuid) "
                "AND employee_id = :e AND status = 'DRAFTING'", p=project_id, e=employee_id)
    if row is None:
        raise ApiError(404, 'DRAFT_NOT_FOUND', '본인의 작성 중인 로드맵을 찾을 수 없어요.')
    raw = row.get('draft_choices') or {}
    draft = raw.get('draft') if isinstance(raw, dict) else None
    if not isinstance(draft, dict):
        raise ApiError(422, 'DRAFT_INPUT_INVALID', '작성 중인 로드맵 정보를 확인해 주세요.')
    desired = str(draft.get('goal') or '').strip()
    if not desired:
        raise ApiError(422, 'SURVEY_INPUT_REQUIRED', '키우고 싶은 역량을 입력해 주세요.')
    summary = doc_summary(draft) or None
    if draft.get('project') and not summary:
        raise ApiError(422, 'PROJECT_SUMMARY_PENDING', '첨부한 기획서의 요약이 아직 완료되지 않았어요. 요약 상태를 확인해 주세요.')
    result = {'goal': desired, 'desiredCompetencies': desired, 'projectSummary': summary}
    if 'prefs' in draft:
        result['details'] = deepcopy(draft['prefs'])
    if draft.get('project'):
        result['projectFile'] = deepcopy(draft['project'])
        text = str((draft.get('doc') or {}).get('text') or '')
        result['projectSourceHash'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return result


def inputs_match(saved: dict, project: dict, personal: dict) -> bool:
    return saved.get('project') == project and saved.get('profile') == personal


def generate_for(employee_id: int, project_id: str) -> dict:
    if not _generation_lock.acquire(blocking=False):
        raise ApiError(409, 'GENERATION_BUSY', '다른 문항을 생성 중이에요. 잠시 후 확인해 주세요.')
    try:
        me = profile.view(employee_id)
        if me is None:
            raise ApiError(404, 'PROFILE_NOT_FOUND', '개인 DB 프로필을 찾을 수 없어요.')
        personal = profile_input(me)
        with db.tx() as t:
            project = project_input(t, employee_id, project_id)
            existing = read(t, employee_id, project_id)
            if existing is not None and inputs_match(existing, project, personal):
                return public_view(existing)
        previous_id = existing['generationId'] if existing is not None else None
        ctx = runtime.context(employee_id, me)
        if not ctx.live:
            raise ApiError(503, 'MODEL_REQUIRED', '사용 가능한 실제 모델을 선택해 주세요.')
        # 네트워크 호출은 DB 트랜잭션·행 잠금 밖에서 한다.
        selection = select_from_catalog(ctx, project)
        survey = generate_survey(project, selection, personal,
                                 lambda system, payload: runtime.llm_json(ctx, system, payload))
        if profile_input(profile.view(employee_id) or {}) != personal:
            raise ApiError(409, 'PROFILE_CHANGED', '생성 중 개인 정보가 변경됐어요. 다시 생성해 주세요.')
        with db.tx() as t:
            # 프로젝트 입력 변경과 최종 저장을 같은 행 잠금으로 보호한다.
            t.one("SELECT project_id FROM public.projects WHERE project_id = CAST(:p AS uuid) "
                  "AND employee_id = :e AND status = 'DRAFTING' FOR UPDATE", p=project_id, e=employee_id)
            if project_input(t, employee_id, project_id) != project:
                raise ApiError(409, 'SURVEY_INPUT_CHANGED', '생성 중 입력이 변경됐어요. 다시 생성해 주세요.')
            saved = save_generated(t, employee_id, project_id, project, selection, personal, survey, replace_generation_id=previous_id)
        return public_view(saved)
    finally:
        _generation_lock.release()


class AnswerBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    generationId: UUID
    answers: dict[str, StrictInt]
    complete: StrictBool = False


r = APIRouter()


async def validation_error(_, error: ValueError):
    from fastapi.responses import JSONResponse
    return JSONResponse({'error': {'code': 'V2_VALIDATION', 'message': str(error)}}, status_code=422)


@r.get('/api/v2/drafts')
def drafts(a: Account = Depends(require_employee)):
    rows = db.all_("SELECT project_id, project_goal, project_name FROM public.projects "
                   "WHERE employee_id = :e AND status = 'DRAFTING' ORDER BY updated_at DESC", e=a.id)
    return {'drafts': [{'id': str(r['project_id']), 'title': r['project_name'] or r['project_goal'] or '작성 중인 로드맵'} for r in rows]}


@r.get('/api/v2/drafts/{project_id}/survey')
def get_survey(project_id: UUID, a: Account = Depends(require_employee)):
    with db.tx() as t:
        saved = read(t, a.id, str(project_id))
        if saved is None:
            return {'survey': None}
        project = project_input(t, a.id, str(project_id))
        me = profile.view(a.id)
        if me is None or not inputs_match(saved, project, profile_input(me)):
            return {'survey': None, 'stale': True}
        return {'survey': public_view(saved)}


@r.post('/api/v2/drafts/{project_id}/survey')
def make_survey(project_id: UUID, a: Account = Depends(require_employee)):
    return {'survey': generate_for(a.id, str(project_id))}


@r.put('/api/v2/drafts/{project_id}/survey/answers')
def put_answers(project_id: UUID, body: AnswerBody, a: Account = Depends(require_employee)):
    personal = profile_input(profile.view(a.id) or {})
    with db.tx() as t:
        t.one("SELECT project_id FROM public.projects WHERE project_id = CAST(:p AS uuid) AND employee_id = :e AND status = 'DRAFTING' FOR UPDATE", p=str(project_id), e=a.id)
        project = project_input(t, a.id, str(project_id))
        current = read(t, a.id, str(project_id))
        if current is None or current.get('generationId') != str(body.generationId) or not inputs_match(current, project, personal):
            raise ApiError(409, 'SURVEY_INPUT_CHANGED', '앞 단계 내용이 변경됐어요. 문항을 새로 만들고 사전 점검을 다시 진행해 주세요.')
        saved = save_answers(t, a.id, str(project_id), str(body.generationId), body.answers, complete=body.complete)
        return {'survey': public_view(saved)}


def recommendation_context(t, employee_id: int, project_id: str) -> dict:
    saved = read(t, employee_id, project_id)
    if saved is None or not saved.get('completed'):
        raise ApiError(409, 'ASSESSMENT_REQUIRED', '사전 점검을 먼저 완료해 주세요.')
    project = project_input(t, employee_id, project_id)
    me = profile.view(employee_id)
    if me is None or not inputs_match(saved, project, profile_input(me)):
        raise ApiError(409, 'SURVEY_INPUT_CHANGED', '앞 단계가 변경됐어요. 사전 점검을 다시 진행해 주세요.')
    return saved


def course_context(t, employee_id: int, project_id: str, course: str | None = None) -> dict:
    saved = recommendation_context(t, employee_id, project_id)
    from app.services.resource_rag import VERSION
    if not course:
        if (saved.get('recommendations') or {}).get('retrieval', {}).get('version') != VERSION:
            saved['recommendations']=None
            saved['resourceChoices']={}
            saved['durationEstimates']={}
        return saved
    from app.services import drafts as draft_service
    from app.services.course_recommendations import scope_view, free_cache_valid
    from app import catalog
    draft = draft_service._row(t, employee_id, project_id, lock=False)['draft_choices']['draft']
    if course not in ('A1','A2','A3') or draft.get('chosen') != course or course not in (draft.get('gen') or {}).get('options', {}):
        raise ApiError(409,'COURSE_CHANGED','선택한 코스를 다시 확인해 주세요.')
    scoped=scope_view(saved,course)
    expected_names = {row['name'] for row in scoped['selection']['skills']}
    cached_names = {row['name'] for row in (scoped.get('recommendations') or {}).get('skills', [])}
    if expected_names != cached_names or (scoped.get('recommendations') or {}).get('retrieval', {}).get('version') != VERSION or (course=='A1' and scoped.get('recommendations') and not free_cache_valid(scoped['recommendations'],catalog.items())):
        scoped['recommendations']=None
        scoped['resourceChoices']={}
        scoped['durationEstimates']={}
    return scoped


def course_input(t, employee_id, project_id, course):
    if not course:return None
    from app.services import drafts as draft_service
    draft=draft_service._row(t,employee_id,project_id,lock=False)['draft_choices']['draft']
    option=draft['gen']['options'][course]
    return {'id':course,**{key:deepcopy(option.get(key)) for key in ('name','reason','scope','weeklyHours')}}


def recommendation_view(saved: dict) -> dict:
    return {'courseId': saved.get('_course'), 'skillDetails': deepcopy((saved.get('selection') or {}).get('skills') or []), 'generationId': saved['generationId'], 'recommendations': saved.get('recommendations'),
            'choices': saved.get('resourceChoices') or {},
            'durationEstimates': saved.get('durationEstimates') or {},
            'skillOrder': saved.get('skillOrder') or [row['name'] for row in (saved.get('recommendations') or {}).get('skills', [])]}


@r.get('/api/v2/drafts/{project_id}/recommendations')
def get_recommendations(project_id: UUID, a: Account = Depends(require_employee), course: str | None = None):
    with db.tx() as t:
        return recommendation_view(course_context(t, a.id, str(project_id), course))


@r.post('/api/v2/drafts/{project_id}/recommendations')
def generate_recommendations(project_id: UUID, a: Account = Depends(require_employee), course: str | None = None):
    if not _generation_lock.acquire(timeout=120):
        raise ApiError(409, 'GENERATION_BUSY', '생성 대기가 길어지고 있어요. 잠시 후 다시 확인해 주세요.')
    try:
        with db.tx() as t:
            pre = course_context(t, a.id, str(project_id), course)
            selected_course = course_input(t, a.id, str(project_id), course)
            if pre.get('recommendations'):
                return recommendation_view(pre)
        ctx = runtime.context(a.id)
        result = recommend_from_catalog(ctx, pre, selected_course)
        with db.tx() as t:
            current = course_context(t, a.id, str(project_id), course)
            if current['generationId'] != pre['generationId']:
                raise ApiError(409, 'SURVEY_INPUT_CHANGED', '점검 문항이 변경됐어요. 다시 확인해 주세요.')
            saved = save_recommendations(t, a.id, str(project_id), pre['generationId'], result, course=course, replace=True)
        return recommendation_view(saved)
    finally:
        _generation_lock.release()


class ChoicesBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    generationId: UUID
    recommendationId: UUID
    choices: dict[str, dict]
    skillOrder: list[str] | None = None


@r.put('/api/v2/drafts/{project_id}/recommendations/choices')
def put_resource_choices(project_id: UUID, body: ChoicesBody, a: Account = Depends(require_employee), course: str | None = None):
    with db.tx() as t:
        pre = course_context(t, a.id, str(project_id), course)
        if not pre.get('recommendations') or pre['recommendations']['id'] != str(body.recommendationId):
            raise ApiError(409,'RECOMMENDATIONS_CHANGED','코스 또는 추천 자료가 변경됐어요. 다시 확인해 주세요.')
        saved = save_resource_choices(t, a.id, str(project_id), str(body.generationId), str(body.recommendationId), body.choices, skill_order=body.skillOrder, course=course)
        return recommendation_view(saved)


@r.post('/api/v2/drafts/{project_id}/recommendations/durations')
def generate_durations(project_id: UUID, body: ChoicesBody, a: Account = Depends(require_employee), course: str | None = None):
    from app.services.duration_proposals import calculate_durations
    from app.agents.roadmap import AUTO_HOURS
    with db.tx() as t:
        pre=course_context(t,a.id,str(project_id),course)
        recommendations=pre.get('recommendations')
        if pre['generationId']!=str(body.generationId) or not recommendations or recommendations.get('id')!=str(body.recommendationId):
            raise ApiError(409,'RECOMMENDATIONS_CHANGED','점검 또는 추천이 변경됐어요.')
        selected_course=course_input(t,a.id,str(project_id),course)
        weekly=(selected_course or {}).get('weeklyHours') or AUTO_HOURS
        proposals=calculate_durations(pre['project'],recommendations,body.choices,
            body.skillOrder if body.skillOrder is not None else pre.get('skillOrder',[row['name'] for row in recommendations['skills']]),weekly)
        saved=save_duration_proposals(t,a.id,str(project_id),str(body.generationId),str(body.recommendationId),proposals,course=course)
        return recommendation_view(saved)


@r.get('/api/v2/drafts/{project_id}/activities')
def get_activities(project_id: UUID,a: Account=Depends(require_employee)):
    from app.services import activity_selection as activities
    with db.tx() as t:
        saved,d=activities.context(t,a.id,str(project_id))
        return {'proposal':activities.current_record(saved,d)}

@r.post('/api/v2/drafts/{project_id}/activities')
def propose_activities(project_id: UUID,a: Account=Depends(require_employee)):
    from app.services import activity_selection as activities
    if not _generation_lock.acquire(timeout=120): raise ApiError(409,'GENERATION_BUSY','생성 대기가 길어지고 있어요. 잠시 후 다시 확인해 주세요.')
    try:
        with db.tx() as t:saved,d=activities.context(t,a.id,str(project_id))
        existing=activities.current_record(saved,d)
        if existing:return {'proposal':existing}
        ctx=runtime.context(a.id)
        if not ctx.live:raise ApiError(503,'MODEL_REQUIRED','실제 모델 연결이 필요해요.')
        proposal=activities.propose(saved,d,lambda system,payload:runtime.llm_json(ctx,system,payload,role='roadmap'),ctx.mode)
        def save(t,w):
            current,draft=activities.context(t,a.id,str(project_id))
            if activities.fingerprint(current,draft)!=proposal['key']:raise ApiError(409,'ACTIVITIES_CHANGED','자료가 변경됐어요. 다시 제안받아 주세요.')
            current['activityProposal']=proposal
            from app.services.course_recommendations import merge_scope
            w['v2Survey']=merge_scope(w['v2Survey'],current)
        from app.services import drafts as draft_service
        draft_service._mutate(a.id,str(project_id),save)
        return {'proposal':proposal}
    finally:_generation_lock.release()

class ActivitySelectionBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    key:str
    selectedIds:list[str]

@r.put('/api/v2/drafts/{project_id}/activities/selection')
def select_activities(project_id:UUID,body:ActivitySelectionBody,a:Account=Depends(require_employee)):
    from app.services.activity_selection import save_selection
    return save_selection(a.id,str(project_id),body.key,body.selectedIds)
