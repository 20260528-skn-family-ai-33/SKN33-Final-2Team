"""V_2: 자료 선택 후 활동 제안, 전체 기본 선택 및 제외."""
from copy import deepcopy
from hashlib import sha256
import json
from app import catalog, db
from app.agents import runtime, roadmap as RM
from app.errors import ApiError
from app.services import drafts
from app.services.survey_store import _write

SYSTEM = """선택한 코스와 스킬 순서, 프로젝트 요약, 선택 자료만으로 학습 활동을 제안한다.
각 스킬에 자료 학습과 프로젝트 적용 활동을 구체적으로 작성한다. 외부 자료는 materials의 id만 res로 사용한다.
선택된 자료를 모두 다루고, 제외 스킬이나 선택하지 않은 자료를 추가하지 않는다. 자료 없는 스킬은 직접 수행 과제로 쓴다.
원본 단계 체계(stage 1~4)를 유지한다. title은 짧고 구체적으로, how는 수행 내용과 완료 기준을 2문장으로 쓴다.
자료 목차·시간 등 없는 정보는 사실처럼 만들지 않는다. 코스 특성은 course의 reason·scope를 참고한다.
JSON: {"acts":[{"skill":"선택 스킬명","stage":2,"title":"활동","res":null,"hours":2,"how":"수행과 완료 기준","skills":["선택 스킬명"]}]}
"""

def fingerprint(saved, draft):
    data=[saved['generationId'], (saved.get('recommendations') or {}).get('id'), saved.get('resourceChoices'), saved.get('skillOrder'), draft.get('chosen'), (draft.get('handoff') or {}).get('key')]
    return sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def current_record(saved, draft):
    record=saved.get('activityProposal')
    return record if record and record.get('key')==fingerprint(saved,draft) else None

def context(t, employee_id, project_id):
    from app.routers.preassessment import course_context
    from app.services.survey_store import read
    saved=read(t, employee_id, project_id)
    raw=drafts._row(t,employee_id,project_id,lock=False)['draft_choices']
    d=raw['draft']; chosen=d.get('chosen')
    if not chosen or not d.get('gen') or chosen not in d['gen']['options']:
        raise ApiError(409,'COURSE_REQUIRED','로드맵 코스를 먼저 선택해 주세요.')
    saved=course_context(t,employee_id,project_id,chosen)
    if not saved.get('recommendations'):raise ApiError(409,'RECOMMENDATIONS_CHANGED','코스에 맞는 자료 추천을 먼저 받아 주세요.')
    return saved,d

def propose(saved, draft, generate, source):
    choices=saved['resourceChoices']; order=saved['skillOrder']
    active=[name for name in order if choices[name].get('enabled',True)]
    if not active: raise ApiError(422,'SKILL_REQUIRED','스킬을 하나 이상 포함해 주세요.')
    resources=catalog.items(); ids=list(dict.fromkeys(rid for name in active for rid in [choices[name]['course']]+choices[name]['books'] if rid))
    materials=[]
    for rid in ids:
        resource=resources.get(rid)
        if not resource: raise ApiError(409,'MATERIAL_CHANGED','선택한 자료를 다시 확인해 주세요.')
        if draft['chosen']=='A1' and resource.get('cost')!=0:
            raise ApiError(409,'FREE_TRACK_PRICE_CHANGED','Free Course는 0원으로 확인된 자료만 선택할 수 있어요.')
        materials.append({key:deepcopy(resource.get(key)) for key in ('id','title','hours','cost','skills','content')})
    raw=generate(SYSTEM,{'project':saved['project'],'skillOrder':active,'choices':{name:choices[name] for name in active},'materials':materials,'course':draft['gen']['options'][draft['chosen']]})
    acts=raw.get('acts') if isinstance(raw,dict) else None
    if not isinstance(acts,list) or not acts: raise ApiError(422,'ACTIVITIES_INVALID','활동 제안을 확인하지 못했어요.')
    used=set(); covered=set()
    for act in acts:
        if not isinstance(act,dict) or act.get('skill') not in active or not str(act.get('title') or '').strip() or not str(act.get('how') or '').strip():
            raise ApiError(422,'ACTIVITIES_INVALID','활동의 역량 또는 설명이 일치하지 않아요.')
        skill=act['skill'];allowed=set(choices[skill]['books'])|{choices[skill]['course']}
        if act.get('res') and act['res'] not in allowed: raise ApiError(422,'ACTIVITIES_INVALID','선택하지 않은 자료가 활동에 포함됐어요.')
        if act.get('res'):used.add(act['res'])
        covered.add(skill)
    if covered!=set(active) or used!=set(ids): raise ApiError(422,'ACTIVITIES_INVALID','선택한 역량·자료를 모두 반영하지 못했어요. 다시 제안받아 주세요.')
    base=deepcopy(draft['gen']['options'][draft['chosen']]);base['acts']=acts
    option=RM.finish_option(draft['chosen'],base,source)
    for target,source in zip(option['acts'],acts):target['skill']=source['skill']
    return {'key':fingerprint(saved,draft),'option':option,'selectedIds':[act['id'] for act in option['acts']]}

def selection_option(saved,draft,selected):
    record=current_record(saved,draft)
    if not record: raise ApiError(409,'ACTIVITIES_CHANGED','자료를 선택하고 활동을 다시 제안받아 주세요.')
    valid={a['id'] for a in record['option']['acts']}
    if not selected or len(set(selected))!=len(selected) or not set(selected)<=valid:
        raise ApiError(422,'ACTIVITY_SELECTION_INVALID','활동을 하나 이상 선택해 주세요.')
    option=deepcopy(record['option']);option['acts']=[a for a in option['acts'] if a['id'] in selected]
    return option

def save_selection(employee_id,project_id,key,selected):
    def save(t,w):
        saved,d=context(t,employee_id,project_id)
        if key!=fingerprint(saved,d):raise ApiError(409,'ACTIVITIES_CHANGED','자료 또는 코스가 바뀌었어요. 활동을 다시 제안받아 주세요.')
        option=selection_option(saved,d,selected)
        saved['activityProposal']['selectedIds']=list(selected)
        from app.services.course_recommendations import merge_scope
        w['v2Survey']=merge_scope(w['v2Survey'],saved)
        w['draftPlan']=RM.build_plan(option,RM.params_of(d['handoff'],option),d['goal'])
        w['lastNew']='new-review'
    return drafts.present(drafts._mutate(employee_id,project_id,save),project_id)
