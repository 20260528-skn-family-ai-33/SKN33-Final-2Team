"""V_2: 자료 선택 후 활동 제안, 전체 기본 선택 및 제외."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4
from app import catalog, db
from app.agents import runtime, roadmap as RM
from app.errors import ApiError
from app.services import drafts
from app.services.survey_store import _write

SYSTEM = """선택한 코스와 스킬 순서, 프로젝트 요약, 선택 자료만으로 학습 활동을 제안한다.
각 스킬에 자료 학습과 정확히 하나의 프로젝트 적용 산출물 과제(res=null)를 작성한다. 외부 자료는 materials의 id만 res로 사용한다.
선택된 자료를 모두 다루고, 제외 스킬이나 선택하지 않은 자료를 추가하지 않는다. 자료 없는 스킬은 직접 수행 과제로 쓴다.
원본 단계 체계(stage 1~4)를 유지한다. 자료 학습 활동의 title은 짧고 구체적으로, how는 수행 내용과 완료 기준을 쓴다. 프로젝트 산출물 과제는 아래 과제 명세 형식을 따른다.
자료 목차·시간 등 없는 정보는 사실처럼 만들지 않는다. 코스 특성은 course의 reason·scope를 참고한다.
선택 강좌·도서를 함께 학습해서 얻는 통합 역량을 skillSummaries에 스킬별로 정확히 3개씩 쓴다. 각 항목은 짧은 명사형 요약이며, 자료별 역량을 나누지 않는다. 선택 자료의 content·skills와 프로젝트 목표에 근거하고 자료에 없는 내용을 보장하지 않는다.
각 줄은 학습 주제·목차·활동 지시가 아니라, 학습자가 해당 자료를 활용해 수행할 수 있게 되는 구체적인 역량을 표현한다. 대상과 수행 능력을 함께 쓰고 명사형으로 끝낸다. 예: "SQL 문법 학습" 대신 "다중 테이블 조인과 집계 쿼리 작성 능력", "데이터 분석" 대신 "분석 결과의 해석 및 근거 기반 설명 능력". 예시의 기술을 그대로 복사하지 않고 해당 스킬·선택 자료의 DB 근거에 맞춘다. "이해", "활용", "역량 강화" 같은 추상적인 단어만 나열하지 않는다.
프로젝트 산출물 과제는 choices[스킬].course로 선택한 강좌의 실제 content·curriculum·skills에 근거한 핵심 실습을 중심으로 설계한다. 선택 도서는 그 실습의 개념·검증을 보조한다. 강좌가 없으면 선택 도서 근거로 설계하고, 자료가 모두 없으면 프로젝트 직접 수행 과제로 명확히 한정한다.
과제 title은 만들 대상과 핵심 기능이 드러나는 하나의 구체적인 결과물 이름이다. 단순 학습·조사·요약·브리프 작성처럼 무엇을 제출할지 불명확한 제목으로 끝내지 않는다.
과제 how는 다음 네 항목을 줄바꿈으로 구분한다: "만들 것: [프로젝트에 적용할 구체적인 결과물과 사용 입력]", "필수 항목: [강좌 근거로 구현·분석할 2~3개 핵심 요구사항]", "제출물: [결과물 파일·형식 및 실행/확인 방법, 필요한 검증 증거]", "평가 기준: [제출물에서 통과 여부를 확인할 2~3개 관찰 가능한 기준]". 각 항목은 짧고 구체적으로 쓰고 스킬당 하나의 집중된 과제 안에서 연결한다.
사후 점검과 역량 보고서에서 제출물과 실행 결과로 해당 스킬을 판단할 수 있어야 한다. 평가 기준은 필수 항목과 대응시키고 결과 정확성·재현성·설명 근거 중 해당 과제에 맞는 증거를 요구한다. 수강 완료·자기평가·설명 분량만으로 역량을 입증했다고 하지 않는다. 아직 제출하지 않은 결과나 획득 역량을 사실로 단정하지 않는다.
DB에서 확인되지 않은 강좌 실습·제공 데이터·평가 방식은 존재한다고 쓰지 않는다. 별도 입력이 필요하면 학습자가 준비할 예제·합성 데이터의 조건을 명시한다. 개인정보·비공개 프로젝트 데이터 제출을 요구하지 않는다. 임의의 성능 목표 수치 대신 예상 결과·검증 방법을 제시한다.
재제안은 같은 스킬과 강좌 근거·도달 수준을 유지하면서 구체적인 구현 대상이나 문제를 바꾸며, 제출물과 평가 기준도 새 과제에 맞춘다.
JSON: {"skillSummaries":{"선택 스킬명":["통합 역량 명사형 요약 1","통합 역량 명사형 요약 2","통합 역량 명사형 요약 3"]},"acts":[{"skill":"선택 스킬명","stage":2,"title":"활동","res":null,"hours":2,"how":"만들 것: 구체적인 결과물\n필수 항목: 구현 요구사항\n제출물: 파일 형식과 검증 증거\n평가 기준: 관찰 가능한 통과 기준","skills":["선택 스킬명"]}]}
"""

def materials_key(saved):
    data = [saved['generationId'], (saved.get('recommendations') or {}).get('id'),
            saved.get('resourceChoices'), saved.get('skillOrder') or [row['name'] for row in (saved.get('recommendations') or {}).get('skills', [])]]
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def materials_ready(saved):
    return bool(saved.get('recommendations') and saved.get('materialsSelectionKey') == materials_key(saved))


def fingerprint(saved, draft):
    data=[saved['generationId'], (saved.get('recommendations') or {}).get('id'), saved.get('resourceChoices'), saved.get('skillOrder'), draft.get('chosen'), (draft.get('handoff') or {}).get('key')]
    return sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def current_record(saved, draft):
    record=saved.get('activityProposal')
    return record if record and record.get('key')==fingerprint(saved,draft) else None

def proposal_id(record):
    if record.get('id'):
        return record['id']
    return sha256(json.dumps([record['key'], record['option']], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]


def versions(saved, draft):
    key = fingerprint(saved, draft)
    records = list(saved.get('activityVersions') or [])
    current = current_record(saved, draft)
    if current:
        records.append(current)
    result = {}
    for record in records:
        if record.get('key') == key:
            value = deepcopy(record)
            value['id'] = proposal_id(value)
            result[value['id']] = value
    return list(result.values())


def view(saved, draft):
    current = current_record(saved, draft)
    if current:
        current = dict(current, id=proposal_id(current))
    return {'proposal': current, 'versions': versions(saved, draft)}


def append_proposal(saved, draft, proposal):
    history = versions(saved, draft)
    value = deepcopy(proposal)
    value['id'] = proposal_id(value)
    saved['activityVersions'] = history + [value]
    saved['activityProposal'] = value


def context(t, employee_id, project_id, course=None):
    from app.routers.preassessment import course_context
    from app.services.survey_store import read
    saved=read(t, employee_id, project_id)
    raw=drafts._row(t,employee_id,project_id,lock=False)['draft_choices']
    d=deepcopy(raw['draft']); chosen=course or d.get('chosen')
    if course is not None:d['chosen']=course
    if not chosen or not d.get('gen') or chosen not in d['gen']['options']:
        raise ApiError(409,'COURSE_REQUIRED','로드맵 코스를 먼저 선택해 주세요.')
    saved=course_context(t,employee_id,project_id,chosen)
    if not saved.get('recommendations'):raise ApiError(409,'RECOMMENDATIONS_CHANGED','코스에 맞는 자료 추천을 먼저 받아 주세요.')
    if not materials_ready(saved) and not current_record(saved,d):raise ApiError(409,'MATERIAL_SELECTION_REQUIRED','자료 선택을 저장한 뒤 과제를 제안받아 주세요.')
    return saved,d

def learning_context(saved, draft):
    choices=saved['resourceChoices']; order=saved['skillOrder']
    active=[name for name in order if choices[name].get('enabled',True)]
    if not active: raise ApiError(422,'SKILL_REQUIRED','스킬을 하나 이상 포함해 주세요.')
    resources=catalog.items(); ids=list(dict.fromkeys(rid for name in active for rid in [choices[name]['course']]+choices[name]['books'] if rid))
    materials=[]
    for rid in ids:
        resource=resources.get(rid)
        if not resource: raise ApiError(409,'MATERIAL_CHANGED','선택한 자료를 다시 확인해 주세요.')
        if draft['chosen']=='A1' and resource.get('type')!='book' and resource.get('cost')!=0:
            raise ApiError(409,'FREE_TRACK_PRICE_CHANGED','Free Course는 0원으로 확인된 자료만 선택할 수 있어요.')
        from app import catalog_evidence
        materials.append({**{key:deepcopy(resource.get(key)) for key in ('id','title','type','hours','cost','skills')},
            **catalog_evidence.evidence(resource,[saved['project']['goal'],saved['project'].get('projectSummary') or '']+active)})
    from app.learner_knowledge import from_profile,hr_context
    payload={'learnerKnowledge':from_profile(saved.get('profile')),'hrContext':hr_context(saved.get('profile')),'project':saved['project'],'skillOrder':active,'choices':{name:choices[name] for name in active},'materials':materials,'course':draft['gen']['options'][draft['chosen']]}
    if draft['chosen']=='A3':payload['skillTargets']={row['name']:deepcopy(row) for row in (saved.get('selection') or {}).get('skills',[]) if row['name'] in active}
    return active, payload


def validate_summaries(summaries, active):
    if not isinstance(summaries,dict) or set(summaries)!=set(active) or any(
        not isinstance(lines,list) or len(lines)!=3 or any(not isinstance(line,str) or not line.strip() for line in lines)
        for lines in summaries.values()
    ):
        raise ApiError(422,'ACTIVITIES_INVALID','스킬별 통합 역량 요약 3개를 확인하지 못했어요. 다시 제안받아 주세요.')
    return {name:[line.strip() for line in summaries[name]] for name in active}


def propose(saved, draft, generate, source, *, previous=None):
    active,payload=learning_context(saved,draft)
    choices=saved['resourceChoices']
    ids=[row['id'] for row in payload['materials']]
    from app.track_policy import challenge_guidance
    from app.learner_knowledge import POLICY
    system=SYSTEM+POLICY+challenge_guidance(draft['chosen'],'tasks')
    if previous:
        payload['previousProposals']=[{'acts':record['option']['acts']} for record in previous]
        system+='\n같은 스킬·순서·코스·선택 자료를 유지하되 previousProposals와 구별되는 프로젝트 적용 과제와 산출물을 제안한다. 자료 학습을 누락하거나 선택 자료를 바꾸지 않는다.'
    raw=generate(system,payload)
    acts=raw.get('acts') if isinstance(raw,dict) else None
    if not isinstance(acts,list) or not acts: raise ApiError(422,'ACTIVITIES_INVALID','활동 제안을 확인하지 못했어요.')
    summaries=validate_summaries(raw.get('skillSummaries'),active)
    used=set(); covered=set(); task_skills=set()
    for act in acts:
        if not isinstance(act,dict) or act.get('skill') not in active or not str(act.get('title') or '').strip() or not str(act.get('how') or '').strip():
            raise ApiError(422,'ACTIVITIES_INVALID','활동의 역량 또는 설명이 일치하지 않아요.')
        skill=act['skill'];allowed=set(choices[skill]['books'])|{choices[skill]['course']}
        if act.get('res') and act['res'] not in allowed: raise ApiError(422,'ACTIVITIES_INVALID','선택하지 않은 자료가 활동에 포함됐어요.')
        if act.get('res'):used.add(act['res'])
        covered.add(skill)
        if not act.get('res'):task_skills.add(skill)
    if covered!=set(active) or task_skills!=set(active) or used!=set(ids): raise ApiError(422,'ACTIVITIES_INVALID','선택한 역량·자료를 모두 반영하지 못했어요. 다시 제안받아 주세요.')
    if any(sum(1 for act in acts if act['skill']==name and not act.get('res'))!=1 for name in active):
        raise ApiError(422,'ACTIVITIES_INVALID','스킬마다 산출물 과제 하나가 필요해요.')
    base=deepcopy(draft['gen']['options'][draft['chosen']]);base['acts']=acts
    option=RM.finish_option(draft['chosen'],base,source)
    for target,source in zip(option['acts'],acts):target['skill']=source['skill']
    return {'id':str(uuid4()),'key':fingerprint(saved,draft),'option':option,'skillSummaries':summaries,'selectedIds':[act['id'] for act in option['acts']]}

def selection_option(saved,draft,selected,proposal_id_=None):
    record=next((record for record in versions(saved,draft) if record['id']==proposal_id_),None) if proposal_id_ else current_record(saved,draft)
    if not record: raise ApiError(409,'ACTIVITIES_CHANGED','자료를 선택하고 활동을 다시 제안받아 주세요.')
    valid={a['id'] for a in record['option']['acts']}
    if not selected or len(set(selected))!=len(selected) or not set(selected)<=valid:
        raise ApiError(422,'ACTIVITY_SELECTION_INVALID','활동을 하나 이상 선택해 주세요.')
    option=deepcopy(record['option']);option['acts']=[a for a in option['acts'] if a['id'] in selected]
    estimates=saved.get('durationEstimates') or {}
    names=[name for name in saved.get('skillOrder',[]) if saved['resourceChoices'][name].get('enabled',True)]
    if names and all(isinstance((estimates.get(name) or {}).get('weeks'),int) for name in names):
        option['materialSchedule']=[{'skill':name,'weeks':estimates[name]['weeks']} for name in names]
    if (saved.get('recommendations') or {}).get('skills'):
        from app.services.material_plan import report
        summaries=record.get('skillSummaries') or {}
        if not summaries:
            from app.services.learning_outcomes import current
            summaries=current(saved,draft) or {}
        option['learningReport']=report(saved,summaries)
    return option

def compose_skill_selection(saved,draft,base_id,picks):
    history=versions(saved,draft)
    base=next((row for row in history if row['id']==base_id),None)
    if not base:raise ApiError(409,'ACTIVITIES_CHANGED','자료를 선택하고 활동을 다시 제안받아 주세요.')
    record=deepcopy(base)
    active={act['skill'] for act in record['option']['acts'] if not act.get('res')}
    if not set(picks)<=active:raise ApiError(422,'ACTIVITY_SELECTION_INVALID','계획에 포함된 스킬을 선택해 주세요.')
    for skill,pid in picks.items():
        source=next((row for row in history if row['id']==pid and row['key']==fingerprint(saved,draft)),None)
        tasks=[act for act in source['option']['acts'] if not act.get('res') and act['skill']==skill] if source else []
        if len(tasks)!=1:raise ApiError(409,'ACTIVITIES_CHANGED','해당 스킬의 과제를 다시 선택해 주세요.')
        record['option']['acts']=[deepcopy(tasks[0]) if not act.get('res') and act['skill']==skill else act for act in record['option']['acts']]
    record['id']=str(uuid4())
    record['skillProposalIds']={**base.get('skillProposalIds',{}),**picks}
    return record


def save_selection(employee_id,project_id,key,selected,proposal_id_=None,skill_picks=None):
    def save(t,w):
        saved,d=context(t,employee_id,project_id)
        if key!=fingerprint(saved,d):raise ApiError(409,'ACTIVITIES_CHANGED','자료 또는 코스가 바뀌었어요. 활동을 다시 제안받아 주세요.')
        if skill_picks:
            record=compose_skill_selection(saved,d,proposal_id_,skill_picks)
            append_proposal(saved,d,record)
            proposal_id_local=record['id']
        else:proposal_id_local=proposal_id_
        option=selection_option(saved,d,selected,proposal_id_local)
        history=versions(saved,d)
        chosen=proposal_id_local or proposal_id(current_record(saved,d))
        record=next(row for row in history if row['id']==chosen)
        record['selectedIds']=list(selected)
        saved['activityVersions']=history
        saved['activityProposal']=deepcopy(record)
        from app.services.course_recommendations import merge_scope
        w['v2Survey']=merge_scope(w['v2Survey'],saved)
        w['draftPlan']=RM.build_plan(option,RM.params_of(d['handoff'],option),d['goal'])
        w['lastNew']='new-review'
    return drafts.present(drafts._mutate(employee_id,project_id,save),project_id)


def repropose_skill(saved,draft,skill,generate,source):
    record=current_record(saved,draft)
    if not record:raise ApiError(409,'ACTIVITIES_REQUIRED','최초 과제 제안을 먼저 받아 주세요.')
    if skill not in saved['skillOrder'] or not saved['resourceChoices'][skill].get('enabled',True):
        raise ApiError(422,'SKILL_REQUIRED','계획에 포함된 스킬을 선택해 주세요.')
    scoped=deepcopy(saved);scoped['skillOrder']=[skill];scoped['resourceChoices']={skill:deepcopy(saved['resourceChoices'][skill])}
    old=deepcopy(record);old['option']['acts']=[act for act in old['option']['acts'] if act.get('skill')==skill]
    replacement=propose(scoped,draft,generate,source,previous=[old])
    tasks=[dict(act,id=f"task-{uuid4()}") for act in replacement['option']['acts'] if not act.get('res')]
    result=deepcopy(record);result['id']=str(uuid4());result['key']=fingerprint(saved,draft)
    kept=[act for act in record['option']['acts'] if act.get('skill')!=skill or act.get('res')]
    result['option']['acts']=[act for name in saved['skillOrder'] for act in kept+tasks if act.get('skill')==name]
    kept_ids={act['id'] for act in kept}
    result['selectedIds']=[aid for aid in record['selectedIds'] if aid in kept_ids]+[act['id'] for act in tasks]
    result.setdefault('skillSummaries',{}).setdefault(skill,replacement['skillSummaries'][skill])
    result['changedSkill']=skill
    return result
