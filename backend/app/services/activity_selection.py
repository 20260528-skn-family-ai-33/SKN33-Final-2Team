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

from .activity_instructions import SYSTEM, instructions


def materials_key(saved):
    data = [saved['generationId'], (saved.get('recommendations') or {}).get('id'),
            saved.get('resourceChoices'), saved.get('skillOrder') or [row['name'] for row in (saved.get('recommendations') or {}).get('skills', [])],
            (saved.get('project') or {}).get('details')]
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def materials_ready(saved):
    return bool(saved.get('recommendations') and saved.get('materialsSelectionKey') == materials_key(saved))


def fingerprint(saved, draft):
    data=[saved['generationId'], (saved.get('recommendations') or {}).get('id'), saved.get('resourceChoices'), saved.get('skillOrder'), draft.get('chosen'), (draft.get('handoff') or {}).get('key'),
          ((draft.get('handoff') or {}).get('prefs') or {}).get('weeklyHours'),
          ((((draft.get('gen') or {}).get('options') or {}).get(draft.get('chosen')) or {}).get('weeklyHours'))]
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
    system=instructions(draft['chosen'])
    if previous:
        payload['previousProposals']=[{'acts':record['option']['acts']} for record in previous]
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
    deduped=[]; by_pair={}; by_res={}
    for act in acts:
        if not act.get('res'):
            deduped.append(deepcopy(act))
            continue
        by_res.setdefault(act['res'], deepcopy(act))
        pair=(act['skill'],act['res'])
        if pair not in by_pair:
            item=deepcopy(act); by_pair[pair]=item; deduped.append(item)
        else:
            how=str(act.get('how') or '').strip()
            if how and how not in by_pair[pair]['how']:
                by_pair[pair]['how']=f"{by_pair[pair]['how'].rstrip()}\n{how}"
    for name in active:
        for rid in [choices[name]['course']]+list(choices[name]['books']):
            if rid and (name,rid) not in by_pair and rid in by_res:
                item=dict(deepcopy(by_res[rid]),skill=name)
                by_pair[(name,rid)]=item; deduped.append(item)
    acts=deduped
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
    if (saved.get('recommendations') or {}).get('skills'):
        from app.services.material_plan import report, duration_estimates
        from app.services.duration_proposals import schedule_rows
        estimates=duration_estimates(saved,draft)
        option['materialSchedule']=schedule_rows(estimates)
        summaries=record.get('skillSummaries') or {}
        if not summaries:
            from app.services.learning_outcomes import current
            summaries=current(saved,draft) or {}
        option['learningReport']=report(dict(saved,durationEstimates=estimates),summaries)
    elif names and all(isinstance((estimates.get(name) or {}).get('weeks'),int) for name in names):
        option['materialSchedule']=[{'skill':name,'weeks':estimates[name]['weeks']} for name in names]
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
