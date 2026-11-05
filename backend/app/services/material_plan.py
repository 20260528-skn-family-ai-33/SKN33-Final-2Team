"""자료 저장 이후의 검토 초안. 이전 계획의 활동·기간을 재사용하지 않는다."""
from copy import deepcopy
from app.agents import roadmap
from app.services.duration_proposals import resource_schedule, schedule_rows, calculate_durations


def duration_estimates(saved, draft):
    """저장된 부분 캐시 대신 현재 전체 선택과 주당시간으로 계산한다."""
    option = ((draft.get('gen') or {}).get('options') or {}).get(saved.get('_course') or draft.get('chosen')) or {}
    project = deepcopy(saved.get('project') or {})
    weekly = ((draft.get('handoff') or {}).get('prefs') or {}).get('weeklyHours')
    if weekly:
        project.setdefault('details', {})['hours'] = weekly
    return calculate_durations(project, saved['recommendations'], saved['resourceChoices'], saved['skillOrder'],
                               option.get('weeklyHours') or roadmap.AUTO_HOURS)


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
    estimates=duration_estimates(saved,draft)
    option['materialSchedule']=schedule_rows(estimates)
    option['learningReport']=report(dict(saved,durationEstimates=estimates),{})
    return roadmap.build_plan(option,roadmap.params_of(draft['handoff'],option),draft['goal'])


def rebuild_revision(option, plan, handoff):
    """스킬형 계획만 재구성. 불명확한 소속은 실패시켜 기존 계획을 보존한다."""
    from app import llm
    from app.services.duration_proposals import RecommendationError
    prior = plan.get('def') or {}
    for field in roadmap.LEARNING_SKILL_FIELDS:
        if field in prior:
            option[field] = deepcopy(prior[field])
    old_report = prior.get('learningReport')
    if not isinstance(old_report, dict):
        return option  # 구형 계획의 기존 기간 계산 유지
    names = list(dict.fromkeys(old_report.get('skillOrder') or []))
    names = [name for name in names if (old_report.get('choices', {}).get(name) or {}).get('enabled', True)]
    if not names:
        raise llm.LlmError('수정할 계획의 스킬 순서를 확인할 수 없어요.')
    old_acts = plan['acts']
    used = set()
    resources = {name: {} for name in names}
    for activity in option['acts']:
        key = activity.get('key')
        matches = [a for a in old_acts if a['id'] not in used and
                   (a.get('res') or None) == (activity.get('res') or None) and
                   (a['id'] == key if key else
                    (a.get('res') == activity.get('res') if activity.get('res') else a['title'] == activity['title']))]
        if not key and activity.get('skill'):
            matches = [a for a in matches if a.get('skill') == activity['skill']]
        old = matches[0] if len(matches) == 1 else None
        if old:
            activity['key'] = old['id']
            activity['skill'] = old.get('skill')
            used.add(old['id'])
        resource = roadmap._res(activity.get('res')) if activity.get('res') else None
        if not activity.get('skill'):
            tags = set((resource or {}).get('skills') or activity.get('skills') or [])
            candidates = [name for name in names if name in tags]
            if len(candidates) == 1:
                activity['skill'] = candidates[0]
        if activity.get('skill') not in names:
            raise llm.LlmError('수정 활동의 소속 스킬을 확인할 수 없어요. 기존 계획은 유지됩니다.')
        if resource:
            if resource.get('type') not in ('course', 'book', 'cert'):
                raise llm.LlmError('스킬별 학습 자료는 강좌 또는 도서여야 합니다.')
            if resource.get('type') in ('course', 'book') and activity['stage'] >= handoff.get('startStage', plan['start']):
                resources[activity['skill']][resource['id']] = deepcopy(resource)
    weekly = (handoff.get('prefs') or {}).get('weeklyHours') or option.get('weeklyHours') or plan['hours']
    rec, choices = [], {}
    for name in names:
        items = list(resources[name].values())
        courses = [item for item in items if item['type'] == 'course']
        books = [item for item in items if item['type'] == 'book']
        rec.append({'name': name, 'courses': courses, 'books': books})
        choices[name] = {'course': courses[0]['id'] if courses else None,
                         'courses': [item['id'] for item in courses],
                         'books': [item['id'] for item in books], 'enabled': True}
    try:
        estimates = resource_schedule({'skills': rec}, choices, names, weekly)['estimates']
    except RecommendationError as error:
        raise llm.LlmError(str(error)) from error
    details = []
    for name in names:
        detail = deepcopy(next((row for row in old_report.get('skillDetails', []) if row['name'] == name), {'name': name, 'application': ''}))
        before = {a['res'] for a in old_acts if a.get('res') and a.get('skill') == name and (roadmap._res(a['res']) or {}).get('type') in ('course', 'book')}
        if before != set(resources[name]):
            detail['competencySummary'] = []
        details.append(detail)
    option['learningReport'] = {'recommendations': {'skills': rec}, 'choices': choices,
                                'skillOrder': names, 'skillDetails': details, 'durationEstimates': estimates}
    option['materialSchedule'] = schedule_rows(estimates)
    return option
