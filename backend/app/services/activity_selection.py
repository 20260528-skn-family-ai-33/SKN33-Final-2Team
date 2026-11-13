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
    # Challenge 심화 목표와 Crash 핵심 완료 기준을 과제 평가 기준에 이어 준다.
    if draft['chosen'] in ('A2','A3'):payload['skillTargets']={row['name']:deepcopy(row) for row in (saved.get('selection') or {}).get('skills',[]) if row['name'] in active}
    return active, payload


def validate_summaries(summaries, active, *, normalize=False):
    if normalize and isinstance(summaries, dict):
        keys = [key.strip() for key in summaries]
        if len(set(keys)) == len(keys):
            summaries = {
                key.strip(): [lines] if isinstance(lines, str) else lines
                for key, lines in summaries.items()
            }
    if not isinstance(summaries,dict) or set(summaries)!=set(active) or any(
        not isinstance(lines,list) or not 1 <= len(lines) <= 3 or any(not isinstance(line,str) or not line.strip() for line in lines)
        for lines in summaries.values()
    ):
        raise ApiError(422,'ACTIVITIES_INVALID','스킬별 통합 역량 요약 1~3개를 확인하지 못했어요. 다시 제안받아 주세요.')
    return {name:[line.strip() for line in summaries[name]] for name in active}


def _answer(raw):
    if isinstance(raw, dict) and 'acts' not in raw and 'answer' in raw:
        raw = raw['answer']
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return {}
    return raw if isinstance(raw, dict) else {}


def _read_activities(acts, choices, source, *, requested_skills=None):
    """기존 모델의 자료 활동도 보존하되, 다른 스킬이나 미선택 자료는 거절한다."""
    tasks = {}
    materials = {}
    requested = choices if requested_skills is None else requested_skills
    if not isinstance(acts, list):
        raise ApiError(422, 'ACTIVITIES_INVALID', '활동 제안을 확인하지 못했어요.')
    for row in acts:
        if not isinstance(row, dict):
            raise ApiError(422, 'ACTIVITIES_INVALID', '활동의 형식을 확인하지 못했어요.')
        rid = row.get('res')
        if source == 'ollama' and 'res' not in row:
            aliases = [row[key] for key in ('resourceId', 'materialId') if row.get(key) is not None]
            if aliases:
                rid = aliases[0]
                if not isinstance(rid, str) or not rid or any(value != rid for value in aliases):
                    raise ApiError(422, 'ACTIVITIES_INVALID', '활동의 자료 ID를 확인하지 못했어요.')
        if source == 'ollama' and isinstance(rid, dict):
            rid = rid.get('id', rid)
        if rid is not None and not isinstance(rid, str):
            raise ApiError(422, 'ACTIVITIES_INVALID', '활동의 자료 ID를 확인하지 못했어요.')
        skill = row.get('skill')
        if not skill:
            tags = row.get('skills')
            if isinstance(tags, list):
                skill = next((tag for tag in tags if isinstance(tag, str) and tag in choices), None)
            if not skill and rid:
                skill = next((name for name, choice in choices.items()
                             if rid == choice['course'] or rid in choice['books']), None)
            if not skill and len(requested) == 1 and (not tags or requested_skills is None):
                skill = next(iter(requested))
        if not isinstance(skill, str) or skill not in choices:
            raise ApiError(422, 'ACTIVITIES_INVALID', '활동의 역량 또는 설명이 일치하지 않아요.')
        if rid and rid != choices[skill]['course'] and rid not in choices[skill]['books']:
            raise ApiError(422, 'ACTIVITIES_INVALID', '선택하지 않은 자료가 활동에 포함됐어요.')
        if skill not in requested:
            continue
        title = str(row.get('title') or row.get('name') or '').strip()
        how = str(row.get('how') or row.get('description') or row.get('content') or row.get('detail') or '').strip()
        if not title or not how:
            raise ApiError(422, 'ACTIVITIES_INVALID', '활동의 역량 또는 설명이 일치하지 않아요.')
        act = dict(row, skill=skill, title=title, how=how, res=rid)
        if not rid:
            if skill in tasks:
                raise ApiError(422, 'ACTIVITIES_INVALID', f'「{skill}」의 산출물 과제가 여러 개예요. 하나만 필요해요.')
            tasks[skill] = act
            continue
        pair = (skill, rid)
        if pair not in materials:
            materials[pair] = act
        elif how not in materials[pair]['how']:
            materials[pair]['how'] += '\n' + how
    return tasks, materials


def _parse_proposal(raw, choices, source):
    answer = _answer(raw)
    summaries = validate_summaries(answer.get('skillSummaries'), choices, normalize=source == 'ollama')
    rows = answer.get('acts')
    if source != 'ollama' or not isinstance(rows, list):
        tasks, materials = _read_activities(rows, choices, source)
        return summaries, tasks, materials

    # Keep valid tasks when another skill returns a malformed activity.
    task_rows = [
        row for row in rows if isinstance(row, dict) and isinstance(row.get('skill'), str) and row['skill'] in choices
        and 'res' in row and row['res'] is None
    ]
    other_rows = [row for row in rows if not any(row is task for task in task_rows)]
    tasks, materials = _read_activities(other_rows, choices, source)
    duplicates = set()
    for row in task_rows:
        try:
            parsed_tasks, _ = _read_activities([row], choices, source)
        except ApiError:
            continue
        duplicates.update(tasks.keys() & parsed_tasks.keys())
        tasks.update(parsed_tasks)
    for skill in duplicates:
        tasks.pop(skill)
    return summaries, tasks, materials


def propose(saved, draft, generate, source, *, previous=None):
    active, payload = learning_context(saved, draft)
    system = instructions(draft['chosen'])
    if previous:
        payload['previousProposals'] = [{'acts': record['option']['acts']} for record in previous]
    choices = payload['choices']
    retried = False
    try:
        summaries, tasks, material_acts = _parse_proposal(generate(system, payload), choices, source)
    except ApiError as error:
        if source != 'ollama' or error.code != 'ACTIVITIES_INVALID':
            raise
        retried = True
        retry_system = (f'{system}\n[검증 실패 후 재시도] {error.message} '
                        'skillOrder의 각 스킬에 res=null인 산출물 과제 하나와 역량 요약 1~3개를 담은 전체 JSON을 반환한다.')
        summaries, tasks, material_acts = _parse_proposal(generate(retry_system, payload), choices, source)

    missing = [name for name in active if name not in tasks]
    if missing and not retried:
        name_list = ', '.join(missing)
        scoped = dict(saved, skillOrder=missing)
        _, retry_payload = learning_context(scoped, draft)
        if previous:
            retry_payload['previousProposals'] = [{'acts': [a for a in row['option']['acts'] if a.get('skill') in missing]}
                                                  for row in previous]
        repair_system = (
            '[누락 과제 보완] project 목표와 choices·materials의 선택 자료를 근거로 과제 작성. '
            'skillOrder의 각 스킬에 과제 정확히 하나. 자료 활동·역량 요약 제외. '
            '이전 과제와 다른 제안. JSON: {"acts":[{"skill":"정확한 스킬명","stage":2,'
            '"title":"과제 제목","res":null,"hours":2,"how":"만들 것·필수 항목·제출물·평가 기준"}]}'
        ) if source == 'ollama' else system + '\n[누락 과제 보완] skillOrder에 지정한 스킬의 과제를 하나씩 acts에 반환한다. 기존 역량 요약은 다시 작성할 필요가 없다.'
        repair = _answer(generate(repair_system, retry_payload))
        try:
            additional, _ = _read_activities(repair.get('acts'), choices, source, requested_skills=missing)
        except ApiError as error:
            raise ApiError(422, 'ACTIVITIES_INVALID', f'산출물 과제를 보완하지 못했어요({name_list}). {error.message}') from error
        tasks.update(additional)
        missing = [name for name in missing if name not in tasks]
    if missing:
        raise ApiError(422, 'ACTIVITIES_INVALID', f'산출물 과제가 빠졌어요({", ".join(missing)}). 다시 제안받아 주세요.')

    resources = {row['id']: row for row in payload['materials']}
    start_stage = (draft.get('handoff') or {}).get('startStage') or 1
    acts = []
    for name in active:
        choice = choices[name]
        for rid in [choice['course'], *choice['books']]:
            if not rid:
                continue
            material = material_acts.get((name, rid))
            if material is None:
                resource = resources[rid]
                material = {'skill': name, 'stage': 2, 'res': rid, 'title': resource['title'],
                            'hours': resource.get('hours'), 'how': f'선택한 자료에서 {name} 과제에 적용할 내용을 정리하세요.'}
            acts.append(material)
        acts.append(tasks[name])
    base = deepcopy(draft['gen']['options'][draft['chosen']])
    base['acts'] = acts
    option = RM.finish_option(draft['chosen'], base, source)
    # 최종 계획은 시작 단계보다 앞선 활동을 제외하므로 선택한 자료와 과제를 시작 단계부터 편성한다.
    for act in option['acts']:
        act['stage'] = max(act['stage'], start_stage)
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
