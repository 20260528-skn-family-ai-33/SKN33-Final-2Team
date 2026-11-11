"""프로젝트 기반 사전 점검·자료 추천·활동 선택 API."""
from __future__ import annotations

from app.services.generation_job import queued_generation

from copy import deepcopy
import hashlib
from app.services.generation_lock import generation_guard
from uuid import UUID

from fastapi import Depends, APIRouter
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt

from app import db
from app.auth import Account, require_employee
from app.agents import runtime
from app.errors import ApiError
from app.services import profile
from app.services.course_recommendations import completed_course_ids
from app.services.drafts import doc_summary
from app.agents.skill_selection import SelectionError, select_from_catalog
from app.agents.survey_generation import SurveyError, generate_survey, profile_input
from app.services.survey_store import StoreError, public_view, read, save_answers, save_generated, save_recommendations, save_resource_choices, save_duration_proposals
from app.agents.resource_recommendations import RecommendationError, recommend_from_catalog



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
    if draft.get('project') and not summary and (draft.get('doc') or {}).get('status') == 'reading':
        raise ApiError(422, 'PROJECT_SUMMARY_PENDING', '첨부한 기획서의 요약이 아직 완료되지 않았어요. 요약 상태를 확인해 주세요.')
    result = {'goal': desired, 'desiredCompetencies': desired, 'projectSummary': summary}
    if 'prefs' in draft:
        result['details'] = deepcopy(draft['prefs'])
    if draft.get('selectedSkills') is not None:
        result['selectedSkills'] = deepcopy(draft['selectedSkills'])
    if draft.get('project'):
        result['projectFile'] = deepcopy(draft['project'])
        text = str((draft.get('doc') or {}).get('text') or '')
        result['projectSourceHash'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return result


def inputs_match(saved: dict, project: dict, personal: dict) -> bool:
    return saved.get('project') == project and saved.get('profile') == personal


def generate_for(employee_id: int, project_id: str, *, staged: bool = False) -> dict:
    if staged:
        from app.services.preassessment_staged import generate_for as staged_generate
        return staged_generate(employee_id, project_id)
    with generation_guard('draft', str(project_id)):
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
        from app.learner_knowledge import from_profile,hr_context
        if 'selectedSkills' in project:
            from app.services.preassessment_flow import checked_skills
            from app import catalog
            selection = checked_skills(project['selectedSkills'], catalog.skill_names())
        else:
            selection = select_from_catalog(ctx, dict(project,learnerKnowledge=from_profile(personal),hrContext=hr_context(personal)))
        survey = generate_survey(project, selection, personal,
                                 runtime.model(ctx, '진단 에이전트', '역량 테스트 문항 생성'),
                                 require_measurement=True)
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
        view=public_view(saved)
        if saved.get('quizStatus')=='pending':
            from app.services.generation_lock import generation_running
            if not generation_running('draft',str(project_id)):view['quizStatus']='interrupted'
        return {'survey': view}


@r.post('/api/v2/drafts/{project_id}/survey')
@queued_generation(reference_prefix='survey:')
def make_survey(project_id: UUID, a: Account = Depends(require_employee)):
    return {'survey': generate_for(a.id, str(project_id), staged=True)}


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


def course_context(t, employee_id: int, project_id: str, course: str | None = None, *,
                   completed: frozenset[str] | None = None) -> dict:
    saved = recommendation_context(t, employee_id, project_id)
    from app.services.resource_rag import version_for
    from app.services.course_recommendations import compatible_recommendations, scope_view
    if completed is None:
        completed = completed_course_ids(t, employee_id)
    if not course:
        recommendations = compatible_recommendations(saved, version_for(), completed)
        if recommendations is not None:
            return dict(saved, recommendations=recommendations)
        return dict(saved, recommendations=None, resourceChoices={}, durationEstimates={})
    from app.services import drafts as draft_service
    draft = draft_service._row(t, employee_id, project_id, lock=False)['draft_choices']['draft']
    if course not in ('A1','A2','A3') or course not in (draft.get('gen') or {}).get('options', {}):
        raise ApiError(409,'COURSE_CHANGED','선택한 코스를 다시 확인해 주세요.')
    if (draft['gen'].get('regenRun') or {}).get(course):
        raise ApiError(409,'REGEN_RUNNING','해당 로드맵을 다시 만드는 중이에요. 완료 후 자료를 확인해 주세요.')
    scoped=scope_view(saved,course,draft['gen']['options'][course])
    scoped['_commonApplications'] = {s['name']: s['application'] for s in
                                     (saved.get('selection') or {}).get('skills', []) if s.get('application')}
    expected_names = {row['name'] for row in scoped['selection']['skills']}
    cached_names = {row['name'] for row in (scoped.get('recommendations') or {}).get('skills', [])}
    scoped['recommendations'] = (compatible_recommendations(scoped, version_for(course), completed)
                                 if expected_names == cached_names else None)
    if scoped['recommendations'] is None:
        scoped['resourceChoices']={}
        scoped['durationEstimates']={}
    return scoped


def course_input(t, employee_id, project_id, course):
    if not course:return None
    from app.services import drafts as draft_service
    draft=draft_service._row(t,employee_id,project_id,lock=False)['draft_choices']['draft']
    option=draft['gen']['options'][course]
    from app.services.course_skills import selected
    targets=selected(option) or []
    from app.agents.roadmap import build_plan, params_of
    planned = build_plan(option, params_of(draft['handoff'], option), draft['goal'])
    return {'id':course,'weeks':planned['weeks'],**{key:deepcopy(option.get(key)) for key in ('name','reason','scope')},'weeklyHours':planned['hours'],'learningSkills':[{k:v for k,v in row.items() if k!='enabled'} for row in targets if row['enabled']]}


def recommendation_view(saved: dict) -> dict:
    from app.services.resource_rag import version_for
    recommendations = deepcopy(saved.get('recommendations'))
    if recommendations:
        recommendations['outdated'] = (recommendations.get('retrieval') or {}).get('version') != version_for(saved.get('_course'))
    return {'courseId': saved.get('_course'), 'skillDetails': deepcopy((saved.get('selection') or {}).get('skills') or []), 'generationId': saved['generationId'], 'recommendations': recommendations,
            'choices': saved.get('resourceChoices') or {},
            'durationEstimates': saved.get('durationEstimates') or {},
            'skillOrder': saved.get('skillOrder') or [row['name'] for row in (saved.get('recommendations') or {}).get('skills', [])]}


@r.get('/api/v2/drafts/{project_id}/recommendations')
def get_recommendations(project_id: UUID, a: Account = Depends(require_employee), course: str | None = None):
    with db.tx() as t:
        saved=course_context(t, a.id, str(project_id), course)
        if (saved.get('recommendations') or {}).get('skills') and saved.get('resourceChoices'):
            from app.services.material_plan import duration_estimates
            from app.services import drafts as draft_service
            draft=draft_service._row(t,a.id,str(project_id),lock=False)['draft_choices'].get('draft') or {}
            saved['durationEstimates']=duration_estimates(saved,draft)
        result=recommendation_view(saved)
        if course:
            from app.services.material_preparation import pending
            from app.services import drafts as draft_service
            draft=draft_service._row(t,a.id,str(project_id),lock=False)['draft_choices'].get('draft') or {}
            result['preparingJobId']=pending(a.id,str(project_id),course,((draft.get('gen') or {}).get('options') or {}).get(course))
        return result


@r.post('/api/v2/drafts/{project_id}/recommendations')
@queued_generation
def generate_recommendations(project_id: UUID, a: Account = Depends(require_employee), course: str | None = None):
    with generation_guard('draft-materials', f'{project_id}:{course or "base"}'):
        with db.tx() as t:
            completed = completed_course_ids(t, a.id)
            pre = course_context(t, a.id, str(project_id), course, completed=completed)
            selected_course = course_input(t, a.id, str(project_id), course)
            if pre.get('recommendations'):
                return recommendation_view(pre)
        ctx = runtime.context(a.id)
        result = recommend_from_catalog(ctx, pre, selected_course, completed=completed)
        with db.tx() as t:
            t.one("SELECT project_id FROM public.projects WHERE project_id=CAST(:p AS uuid) AND employee_id=:e AND status='DRAFTING' FOR UPDATE",p=str(project_id),e=a.id)
            latest_completed = completed_course_ids(t, a.id)
            current = course_context(t, a.id, str(project_id), course, completed=latest_completed)
            if any(card['id'] in latest_completed for row in result.get('skills', []) for card in row['courses']):
                raise ApiError(409, 'RECOMMENDATIONS_CHANGED', '추천 중 강좌 이수 기록이 변경됐어요. 다시 추천받아 주세요.')
            from app.services.course_recommendations import dependency_key
            if dependency_key(current) != dependency_key(pre):
                raise ApiError(409, 'RECOMMENDATIONS_CHANGED', '생성 중 역량·순서 또는 선택한 계획이 변경됐어요. 최신 조건으로 다시 추천받아 주세요.')
            saved = save_recommendations(t, a.id, str(project_id), pre['generationId'], result, course=course, replace=True)
        return recommendation_view(saved)


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
        project=deepcopy(pre['project'])
        if selected_course:
            project.setdefault('details',{})['hours']=weekly
        proposals=calculate_durations(dict(project, selectedCourse=selected_course),recommendations,body.choices,
            body.skillOrder if body.skillOrder is not None else pre.get('skillOrder',[row['name'] for row in recommendations['skills']]),weekly)
        preview=dict(pre,durationEstimates=proposals,resourceChoices=deepcopy(body.choices),
                     skillOrder=body.skillOrder if body.skillOrder is not None else pre.get('skillOrder'))
        return recommendation_view(preview)


@r.get('/api/v2/drafts/{project_id}/activities')
def get_activities(project_id: UUID,a: Account=Depends(require_employee),course: str | None=None):
    from app.services import activity_selection as activities
    with db.tx() as t:
        saved,d=activities.context(t,a.id,str(project_id),**({'course':course} if course else {}))
        return activities.view(saved,d)

@r.post('/api/v2/drafts/{project_id}/activities')
@queued_generation
def propose_activities(project_id: UUID,a: Account=Depends(require_employee),regenerate: bool=False,skill: str | None=None,course: str | None=None):
    from app.services import activity_selection as activities
    with db.tx() as t:_, target=activities.context(t,a.id,str(project_id),**({'course':course} if course else {}))
    course=target['chosen']
    with generation_guard('draft-review', f'{project_id}:{target["chosen"]}'):
        with db.tx() as t:saved,d=activities.context(t,a.id,str(project_id),**({'course':course} if course else {}))
        existing=activities.current_record(saved,d)
        if existing and not regenerate and not skill:return activities.view(saved,d)
        ctx=runtime.context(a.id)
        if not ctx.live:raise ApiError(503,'MODEL_REQUIRED','실제 모델 연결이 필요해요.')
        model=runtime.model(ctx,f'로드맵 계획 · {course}','스킬 활동 다시 제안' if skill else '학습 활동 제안',role='roadmap')
        proposal=activities.repropose_skill(saved,d,skill,model,ctx.mode) if skill else activities.propose(saved,d,model,ctx.mode,previous=activities.versions(saved,d) if regenerate else None)
        def save(t,w):
            current,draft=activities.context(t,a.id,str(project_id),**({'course':course} if course else {}))
            if activities.fingerprint(current,draft)!=proposal['key']:raise ApiError(409,'ACTIVITIES_CHANGED','자료가 변경됐어요. 다시 제안받아 주세요.')
            active=activities.current_record(current,draft)
            if (activities.proposal_id(active) if active else None)!=(activities.proposal_id(existing) if existing else None):
                raise ApiError(409,'ACTIVITIES_CHANGED','선택한 제안이 변경됐어요. 다시 확인해 주세요.')
            activities.append_proposal(current,draft,proposal)
            from app.services.course_recommendations import merge_scope
            w['v2Survey']=merge_scope(w['v2Survey'],current)
        from app.services import drafts as draft_service
        current_result=draft_service._mutate(a.id,str(project_id),save)
        from app.services.course_recommendations import scope_view
        return activities.view(scope_view(current_result['v2Survey'],d['chosen'],((d.get('gen') or {}).get('options') or {}).get(d['chosen'])),d)

class ActivitySelectionBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    key:str
    selectedIds:list[str]
    proposalId:str | None=None
    skillProposalIds:dict[str,str] | None=None

@r.put('/api/v2/drafts/{project_id}/activities/selection')
def select_activities(project_id:UUID,body:ActivitySelectionBody,a:Account=Depends(require_employee)):
    from app.services.activity_selection import save_selection
    return save_selection(a.id,str(project_id),body.key,body.selectedIds,body.proposalId,**({'skill_picks':body.skillProposalIds} if body.skillProposalIds is not None else {}))


class SkillSelectionBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str
    selection: list[dict]


@r.put('/api/v2/drafts/{project_id}/options/{course}/skills')
def select_course_skills(project_id:UUID,course:str,body:SkillSelectionBody,a:Account=Depends(require_employee)):
    from app.services.course_skills import save
    return save(a.id,str(project_id),course,body.key,body.selection)


@r.post('/api/v2/drafts/{project_id}/options/{course}/skills')
@queued_generation
def initialize_course_skills(project_id:UUID,course:str,a:Account=Depends(require_employee)):
    from app.services.course_skills import initialize
    return initialize(a.id,str(project_id),course)


@r.get('/api/v2/drafts/{project_id}/learning-outcomes')
def get_learning_outcomes(project_id:UUID,a:Account=Depends(require_employee),course: str | None=None):
    from app.services import activity_selection,learning_outcomes
    with db.tx() as t:
        saved,draft=activity_selection.context(t,a.id,str(project_id),**({'course':course} if course else {}))
        return {'summaries':learning_outcomes.current(saved,draft)}


@r.post('/api/v2/drafts/{project_id}/learning-outcomes')
@queued_generation
def generate_learning_outcomes(project_id:UUID,a:Account=Depends(require_employee),course: str | None=None):
    from app.services import activity_selection,learning_outcomes,drafts
    from app.services.course_recommendations import merge_scope
    with db.tx() as t:_, target=activity_selection.context(t,a.id,str(project_id),**({'course':course} if course else {}))
    course=target['chosen']
    with generation_guard('draft-review', f'{project_id}:{target["chosen"]}'):
        with db.tx() as t:
            saved,draft=activity_selection.context(t,a.id,str(project_id),**({'course':course} if course else {}))
            existing=learning_outcomes.current(saved,draft)
            if existing is not None:return {'summaries':existing}
        ctx=runtime.context(a.id)
        if not ctx.live:raise ApiError(503,'MODEL_REQUIRED','실제 모델 연결이 필요해요.')
        result=learning_outcomes.generate(saved,draft,runtime.model(ctx,f'로드맵 계획 · {course}','학습 결과 요약',role='roadmap'))
        def save(t,w):
            latest,d=activity_selection.context(t,a.id,str(project_id),**({'course':course} if course else {}))
            if activity_selection.fingerprint(latest,d)!=result['key']:raise ApiError(409,'MATERIALS_CHANGED','선택한 자료가 변경됐어요. 다시 확인해 주세요.')
            latest['learningOutcomes']=result
            w['v2Survey']=merge_scope(w['v2Survey'],latest)
        drafts._mutate(a.id,str(project_id),save)
        return {'summaries':result['summaries']}


@r.post('/api/v2/drafts/{project_id}/skills')
@queued_generation
def preview_skills(project_id: UUID, a: Account = Depends(require_employee)):
    import json
    def snapshot():
        personal = profile_input(profile.view(a.id) or {})
        with db.tx() as t:
            project = project_input(t, a.id, str(project_id))
        project.pop('selectedSkills', None)
        project.pop('details', None)  # 학습 여건과 스킬 추천은 독립된 입력이다.
        return project, personal

    project, personal = snapshot()
    version = hashlib.sha256(json.dumps([project, personal], ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    # 문항 생성과 분리하며 동일 입력의 스킬 추천만 중복 방지한다.
    with generation_guard('draft-skills', f'{project_id}:{version}'):
        ctx = runtime.context(a.id)
        if not ctx.live:
            raise ApiError(503, 'MODEL_REQUIRED', '스킬 추천에 사용할 모델을 연결해 주세요.')
        from app.learner_knowledge import from_profile, hr_context
        result = select_from_catalog(ctx, dict(project, learnerKnowledge=from_profile(personal), hrContext=hr_context(personal)))
        latest_project, latest_personal = snapshot()
        if latest_project != project or latest_personal != personal:
            raise ApiError(409, 'SKILL_INPUT_CHANGED', '추천 중 입력이나 개인 정보가 변경됐어요. 현재 내용으로 다시 추천받아 주세요.')
        return result
