"""새 사전 점검에서 기존 3안 생성으로 넘기는 V_2 전용 계약."""
from copy import deepcopy
from app import track_policy
import hashlib
import json

def build_handoff(saved, prefs, profile):
    if not saved.get('completed'):
        raise ValueError('사전 점검을 먼저 완료해 주세요.')
    independent = bool((saved.get('selection') or {}).get('skills')) or not saved.get('recommendations')
    if independent:
        saved=deepcopy(saved)
        rows=(saved.get('selection') or {}).get('skills') or []
        saved['recommendations']={'skills':[{'name':row['name'],'courses':[],'books':[]} for row in rows]}
        saved['skillOrder']=[row['name'] for row in rows]
        saved['resourceChoices']={row['name']:{'course':None,'books':[],'enabled':True} for row in rows}
    rec = saved.get('recommendations') or {}
    by_name = {row['name']: row for row in rec.get('skills', [])}
    choices = saved.get('resourceChoices') or {}
    order = saved.get('skillOrder') or list(by_name)
    from app.agents.resource_recommendations import validate_choices, validate_skill_order
    validate_choices(rec, choices)
    validate_skill_order(rec, order)
    # 이전 상한(5개)으로 저장된 점검은 사용자 순서의 앞 3개만 계획에 넘긴다.
    names = [name for name in order if choices[name].get('enabled', True)][:track_policy.MAX_SKILLS]
    if not names:
        raise ValueError('계획에 포함할 스킬을 하나 이상 선택해 주세요.')
    hints = list(dict.fromkeys(rid for name in names for rid in ([choices[name]['course']] + choices[name]['books']) if rid))
    project = saved['project']
    details = {row['name']: row for row in (saved.get('selection') or {}).get('skills', [])}
    from app.learner_knowledge import from_profile,hr_context
    knowledge=from_profile(saved.get('profile') or profile)
    h = {'learnerKnowledge':knowledge,'hrContext':hr_context(saved.get('profile') or profile),'goal':project['goal'],'projectSummary':project.get('projectSummary'),'projectFile':(project.get('projectFile') or {}).get('name'),
        'planningContextVersion':'project-application/v1','details':deepcopy(project.get('details') or {}),
        'desiredCompetencies':deepcopy(project.get('desiredCompetencies') or project['goal']),
        'domain':' · '.join(names),'startStage':1,'startSuggested':1,
        'startReason':'프로젝트에 필요한 선정 스킬을 순서대로 학습합니다. 수준 판정에 따른 시작 단계가 아닙니다.',
        'known':list(knowledge['technologies']),'gaps':[],'focus':names,'outcome':project['goal'],'resourceHints':hints,'prefs':deepcopy(prefs),
        'profile':deepcopy(profile),'userNotes':[project.get('details',{}).get('etc')] if project.get('details',{}).get('etc') else [],
        'agentNotes':['skillOrder의 포함 스킬을 모두 다루고 순서를 지킨다. 제외 스킬을 다시 추가하지 않는다. 설문 수준 때문에 스킬을 빼지 않는다. 도서·강좌는 로드맵·자료 선택에서 고르고, 산출물은 마지막 검토·확정에서 고른다.'],
        'userEdited':['스킬 순서·포함 여부'],'skillOrder':names,
        'skillNames':list(names),'trackPolicyVersion':track_policy.VERSION,
        'skillDetails':[deepcopy(details[name]) for name in names if name in details],
        'skillMaterials':{name:deepcopy(choices[name]) for name in names},
        'excludedSkills':[name for name in order if name not in names],
        'assessment':{'groups':deepcopy(saved['survey']['groups']),'answers':deepcopy(saved['answers'])},
        'durationEstimates':{name:deepcopy((saved.get('durationEstimates') or {}).get(name)) for name in names},
        'assessmentGenerationId':saved['generationId']}
    h['courseSkillSelection']=True
    if project.get('selectedSkills'):
        h['selectedSkillsFixed']=True
    h['agentNotes']=['각 Track이 후보 역량 중 관점에 맞는 지식·역량을 따로 추천한다. 사용자는 로드맵 선택에서 포함 여부와 순서를 정한다. 자료는 자료 선택에서 고른다.']
    if h.get('selectedSkillsFixed'):
        h['agentNotes']=['사용자가 앞 단계에서 확정한 skillOrder 전체와 순서를 유지한다. 스킬을 추가·제외·재정렬하지 않고 관점별 수행 깊이와 자료를 조정한다.']
    h['key']=hashlib.sha1(json.dumps(h,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    return h
