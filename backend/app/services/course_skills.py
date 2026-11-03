"""로드맵별 추천 역량과 사용자 순서·포함 선택. 기존 초안 JSON만 사용한다."""
from copy import deepcopy
import hashlib
import json

CONTRACT = """
[로드맵별 지식·역량 추천]
기존 Track 정책과 후보 조건을 유지한다. 이 로드맵에서 실제 익힐 핵심 지식·역량을
handoff.skillDetails 중에서 관점·목표·계획 범위에 맞춰 직접 고르고 우선순위 순으로 learningSkills에 쓴다.
다른 관점과 같은 목록을 기계적으로 복사하지 않는다. Free는 무료 강좌 중심의 학습 가능 범위,
Crash는 최소 기능 구현 핵심(최대 3개), Challenge는 설계·측정·검증의 심화 범위를 반영한다.
태그 이름은 후보 이름 그대로 쓰되 application은 이 로드맵에서 익힐 구체적인 지식·역량을 짧은 명사형으로 쓴다.
새 태그나 프로젝트 밖의 목표를 추가하지 않는다. 최소 1개이며 추천한 역량은 활동에서도 다룬다.
JSON에 "learningSkills":[{"name":"선정 스킬명","application":"이 로드맵의 구체적인 지식·역량"}]을 추가한다.
새 안을 요청받으면 이전 learningSkills도 참고하여 관점 안에서 학습 범위·강조점과 추천을 다시 검토한다.
차이를 만들기 위해 필수 역량을 억지로 빼거나 무관한 역량을 추가하지 않는다.
[프로젝트 적합성]
스킬 태그가 같아도 handoff.skillDetails의 application과 실제 프로젝트 포함 범위에 맞춰 배울 부분을 좁힌다.
목표·기획서 요약의 포함/제외 범위와 desiredCompetencies·details를 함께 확인한다. 없는 업무·데이터·시스템·목차를 추가하지 않는다.
각 application에는 프로젝트에서 수행할 대상과 행동이 드러나야 한다. '기초 이해', '실무 활용', '역량 강화'만으로 끝내지 않는다.
learnerKnowledge에 이미 사용하는 기술이 있으면 반복 입문 대신 이번 프로젝트에서 새로 배울 구체적인 적용·검증 범위를 쓴다.
Free는 실제 가용 자료 안에서 핵심 수행, Crash는 핵심 기능의 최소 완성, Challenge는 같은 수행의 설계 대안·결과 검증·개선 근거로 도달 수준을 구별한다.
코스 간 차이를 보이려고 무관한 스킬을 넣거나 근거 없이 기간·자료 개수를 늘리지 않는다. 선택 자료는 후속 단계에서 정하므로 특정 강좌를 이미 선택했다고 단정하지 않는다.
"""


def validate_recommendations(rows, allowed, course, *, require_depth=False):
    limit = 3 if course == 'A2' else 5
    if not isinstance(rows, list) or not 1 <= len(rows) <= limit:
        raise ValueError('로드맵별 지식·역량 추천을 확인하지 못했어요. 새 안을 만들어 주세요.')
    result=[]; seen=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('name'),str) or row.get('name') not in allowed or row['name'] in seen or not isinstance(row.get('application'),str) or not row['application'].strip():
            raise ValueError('로드맵별 역량의 이름·설명을 확인하지 못했어요.')
        value={'name':row['name'],'application':row['application'].strip()}
        if course=='A3':
            if require_depth and (not row.get('targetOutcome') or not row.get('completionCriteria')):
                raise ValueError('Challenge 추천에는 구체적인 산출물과 완료 기준 2~4개가 필요해요.')
            if 'targetOutcome' in row:
                if not isinstance(row['targetOutcome'],str) or not row['targetOutcome'].strip():raise ValueError('Challenge 산출물 목표가 비어 있어요.')
                value['targetOutcome']=row['targetOutcome'].strip()
            if 'completionCriteria' in row:
                criteria=row['completionCriteria']
                if not isinstance(criteria,list) or not 2<=len(criteria)<=4 or any(not isinstance(item,str) or not item.strip() for item in criteria):raise ValueError('Challenge 완료 기준은 2~4개가 필요해요.')
                if require_depth and len({' '.join(item.split()) for item in criteria}) != len(criteria):
                    raise ValueError('Challenge 완료 기준은 서로 다른 확인 항목이어야 해요.')
                value['completionCriteria']=[item.strip() for item in criteria]
        seen.add(row['name']);result.append(value)
    return result


def recommendation_key(option):
    return hashlib.sha256(json.dumps([option.get('learningSkillsVersion'),option.get('learningSkills')],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def selected(option):
    rows = option.get('learningSkills') or []
    if not rows:return None
    selection=option.get('learningSkillSelection')
    if selection is None:return [dict(row,enabled=True) for row in rows]
    by_name={row['name']:row for row in rows}
    if not isinstance(selection,list) or len(selection)!=len(rows) or any(not isinstance(row,dict) or not isinstance(row.get('name'),str) or row.get('name') not in by_name or type(row.get('enabled')) is not bool for row in selection) or len({row['name'] for row in selection})!=len(rows) or not any(row['enabled'] for row in selection):
        raise ValueError('로드맵에 포함할 역량과 순서를 확인해 주세요.')
    return [dict(deepcopy(by_name[row['name']]),enabled=row['enabled']) for row in selection]


def save(employee_id,project_id,course,key,selection):
    from app.services import drafts
    from app.errors import ApiError
    def apply(t,w):
        g=w['draft'].get('gen') or {}
        if (g.get('regenRun') or {}).get(course):raise ApiError(409,'REGEN_RUNNING','새 안을 만드는 중이에요.')
        drafts._sync(g)
        option=(g.get('options') or {}).get(course)
        if not option or not option.get('learningSkills') or recommendation_key(option)!=key:
            raise ApiError(409,'SKILLS_CHANGED','보고 있는 안의 역량 추천이 바뀌었어요. 다시 확인해 주세요.')
        candidate=dict(option,learningSkillSelection=selection)
        try:selected(candidate)
        except ValueError as e:raise ApiError(422,'SKILL_SELECTION_INVALID',str(e)) from e
        changed=selected(option)!=selected(candidate)
        option['learningSkillSelection']=deepcopy(selection)
        if changed:
            from app.services.course_recommendations import invalidate_course_tail
            invalidate_course_tail(w,course)
    return drafts.present(drafts._mutate(employee_id,project_id,apply),project_id)


from app.services.generation_lock import generation_guard


def option_signature(option):
    return hashlib.sha256(json.dumps({k:option.get(k) for k in ('id','name','reason','scope','acts')},ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def initialize(employee_id,project_id,course):
    """기존 안에 빠진 최초 추천만 보완한다. 이미 있으면 모델을 다시 호출하지 않는다."""
    from app import db
    from app.agents import runtime
    from app.services import drafts
    from app.routers.preassessment import recommendation_context
    from app.errors import ApiError
    from uuid import uuid4
    with generation_guard('draft', str(project_id)):
        with db.tx() as t:
            saved=recommendation_context(t,employee_id,project_id)
            w=drafts._wrap(drafts._row(t,employee_id,project_id,lock=False)['draft_choices'])
            g=w['draft'].get('gen') or {};drafts._sync(g)
            option=(g.get('options') or {}).get(course)
            if not option:raise ApiError(409,'NO_OPTION','먼저 로드맵 제안을 받아 주세요.')
            if option.get('learningSkills'):return drafts.present(w,project_id)
            if (g.get('regenRun') or {}).get(course):raise ApiError(409,'REGEN_RUNNING','새 안을 만드는 중이에요.')
            signature=option_signature(option)
            candidates=deepcopy((saved.get('selection') or {}).get('skills') or [])
            if course=='A2':candidates=candidates[:3]
            generation=saved['generationId']
            from app.learner_knowledge import from_profile,hr_context
            payload={'learnerKnowledge':from_profile(saved.get('profile')),'hrContext':hr_context(saved.get('profile')),'handoff':{'goal':saved['project']['goal'],'projectSummary':saved['project'].get('projectSummary'),'desiredCompetencies':deepcopy(saved['project'].get('desiredCompetencies') or saved['project']['goal']),'details':deepcopy(saved['project'].get('details') or {}),'skillDetails':candidates},'course':course,'existingPlan':deepcopy(option)}
        ctx=runtime.context(employee_id)
        if not ctx.live:raise ApiError(422,'LIVE_MODEL_REQUIRED','역량 추천에는 연결된 AI 모델이 필요해요.')
        from app.track_policy import challenge_guidance
        from app.learner_knowledge import POLICY
        raw=runtime.llm_json(ctx,CONTRACT+POLICY+challenge_guidance(course,'plan')+'\n기존 로드맵 existingPlan은 바꾸지 않고, 그 계획에서 익히게 될 learningSkills만 반환한다.',payload,role='roadmap')
        try:rows=validate_recommendations(raw.get('learningSkills') if isinstance(raw,dict) else None,{row['name'] for row in candidates},course,require_depth=True)
        except ValueError as e:raise ApiError(422,'SKILLS_INVALID',str(e)) from e
        def apply(t,current):
            pre=recommendation_context(t,employee_id,project_id)
            gen=current['draft'].get('gen') or {};drafts._sync(gen)
            target=(gen.get('options') or {}).get(course)
            if pre['generationId']!=generation or not target or option_signature(target)!=signature or (gen.get('regenRun') or {}).get(course):
                raise ApiError(409,'SKILLS_CHANGED','로드맵이 변경됐어요. 최신 안을 확인해 주세요.')
            if not target.get('learningSkills'):
                target['learningSkills']=rows
                target['learningSkillsVersion']=str(uuid4())
                target['learningSkillsKey']=recommendation_key(target)
        return drafts.present(drafts._mutate(employee_id,project_id,apply),project_id)
