"""새 사전 점검에서 기존 3안 생성으로 넘기는 V_2 전용 계약."""
from copy import deepcopy
import hashlib
import json

def build_handoff(saved, prefs, profile):
    if not saved.get('completed'):
        raise ValueError('사전 점검을 먼저 완료해 주세요.')
    rec = saved.get('recommendations') or {}
    by_name = {row['name']: row for row in rec.get('skills', [])}
    choices = saved.get('resourceChoices') or {}
    order = saved.get('skillOrder') or list(by_name)
    from app.agents.resource_recommendations import validate_choices, validate_skill_order
    validate_choices(rec, choices)
    validate_skill_order(rec, order)
    names = [name for name in order if choices[name].get('enabled', True)]
    if not names:
        raise ValueError('계획에 포함할 스킬을 하나 이상 선택해 주세요.')
    hints = list(dict.fromkeys(rid for name in names for rid in ([choices[name]['course']] + choices[name]['books']) if rid))
    project = saved['project']
    details = {row['name']: row for row in (saved.get('selection') or {}).get('skills', [])}
    h = {'goal':project['goal'],'projectSummary':project.get('projectSummary'),'projectFile':(project.get('projectFile') or {}).get('name'),
        'domain':' · '.join(names),'startStage':1,'startSuggested':1,
        'startReason':'프로젝트에 필요한 선정 스킬을 순서대로 학습합니다. 수준 판정에 따른 시작 단계가 아닙니다.',
        'known':[],'gaps':[],'focus':names,'outcome':project['goal'],'resourceHints':hints,'prefs':deepcopy(prefs),
        'profile':deepcopy(profile),'userNotes':[project.get('details',{}).get('etc')] if project.get('details',{}).get('etc') else [],
        'agentNotes':['skillOrder의 포함 스킬을 모두 다루고 순서를 지킨다. 제외 스킬을 다시 추가하지 않는다. 설문 수준 때문에 스킬을 빼지 않는다. 도서·강좌의 최종 선택은 검토·확정에서 한다.'],
        'userEdited':['스킬 순서·포함 여부'],'skillOrder':names,
        'skillDetails':[deepcopy(details[name]) for name in names if name in details],
        'skillMaterials':{name:deepcopy(choices[name]) for name in names},
        'excludedSkills':[name for name in order if name not in names],
        'assessment':{'groups':deepcopy(saved['survey']['groups']),'answers':deepcopy(saved['answers'])},
        'durationEstimates':{name:deepcopy((saved.get('durationEstimates') or {}).get(name)) for name in names},
        'assessmentGenerationId':saved['generationId']}
    h['key']=hashlib.sha1(json.dumps(h,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    return h
