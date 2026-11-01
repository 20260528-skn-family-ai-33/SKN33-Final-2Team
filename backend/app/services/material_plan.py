"""자료 저장 이후의 검토 초안. 이전 계획의 활동·기간을 재사용하지 않는다."""
from copy import deepcopy
from app.agents import roadmap


def report(saved,summaries):
    rec=deepcopy(saved.get('recommendations') or {'skills':[]})
    for row in rec['skills']:
        choice=saved['resourceChoices'][row['name']]
        row['courses']=[item for item in row['courses'] if item['id']==choice['course']]
        row['books']=[item for item in row['books'] if item['id'] in choice['books']]
    return {'recommendations':rec,'choices':deepcopy(saved['resourceChoices']),'skillOrder':list(saved['skillOrder']),
        'skillDetails':[{'name':name,'application':'','competencySummary':summaries.get(name,[])} for name in saved['skillOrder']],
        'durationEstimates':deepcopy(saved.get('durationEstimates') or {})}


def preview(saved,draft):
    chosen=draft.get('chosen');option=deepcopy(((draft.get('gen') or {}).get('options') or {}).get(chosen))
    if not option:return None
    acts=[]
    names=[name for name in saved.get('skillOrder',[]) if saved['resourceChoices'].get(name,{}).get('enabled',True)]
    rows={row['name']:row for row in (saved.get('recommendations') or {}).get('skills',[])}
    for index,name in enumerate(names):
        choice=saved['resourceChoices'][name];row=rows[name]
        for resource in row['courses']+row['books']:
            if resource['id']!=choice['course'] and resource['id'] not in choice['books']:continue
            acts.append({'id':f"material-{index}-{resource['id']}",'skill':name,'stage':2,'title':resource['title'],'res':resource['id'],'hours':resource.get('hours') or 2,'how':''})
    option['acts']=acts
    estimates=saved.get('durationEstimates') or {}
    if names and all(isinstance((estimates.get(name) or {}).get('weeks'),int) for name in names):
        option['materialSchedule']=[{'skill':name,'weeks':estimates[name]['weeks']} for name in names]
    return roadmap.build_plan(option,roadmap.params_of(draft['handoff'],option),draft['goal'])
