"""V_2 코스별 추천·선택·주차·활동 캐시. 공통 점검 스킬은 유지한다."""
from copy import deepcopy
FIELDS=('recommendations','resourceChoices','durationEstimates','activityProposal','activityVersions','materialsSelectionKey','skillSelectionKey','learningOutcomes')

def scope_view(saved,course,option=None):
    if not course:return deepcopy(saved)
    scoped=deepcopy(saved)
    scoped['_course']=course
    cache=(saved.get('courseRecommendations') or {}).get(course) or {}
    for field in FIELDS:scoped[field]=deepcopy(cache.get(field))
    scoped['resourceChoices']=scoped.get('resourceChoices') or {}
    from app.services.course_skills import selected
    learning=selected(option or {})
    if (saved.get('project') or {}).get('selectedSkills'):
        fixed=(saved.get('selection') or {}).get('skills') or []
        by_name={row['name']:row for row in learning or []}
        learning=[dict(row,**{k:v for k,v in by_name.get(row['name'],{}).items() if k not in ('name','application','enabled')},enabled=True) for row in fixed]
    if learning is not None:
        active=[row for row in learning if row['enabled']]
        scoped['selection']={'skills':[{k:v for k,v in row.items() if k!='enabled'} for row in active]}
        scoped['skillOrder']=[row['name'] for row in active]
        from hashlib import sha256
        import json
        key=sha256(json.dumps([option.get('learningSkillsVersion'),sorted(scoped['selection']['skills'],key=lambda row:row['name'])],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if cache.get('skillSelectionKey')!=key:
            for field in FIELDS:scoped[field]=None
            scoped['resourceChoices']={}
            scoped['skillOrder']=[row['name'] for row in active]
        scoped['skillSelectionKey']=key
        for choice in scoped['resourceChoices'].values():choice['enabled']=True
        return scoped
    for name,choice in scoped['resourceChoices'].items():
        choice['enabled']=(saved.get('resourceChoices') or {}).get(name,{}).get('enabled',True)
    if course=='A2':
        active=[name for name in (saved.get('skillOrder') or []) if (saved.get('resourceChoices') or {}).get(name,{}).get('enabled',True)][:3]
        scoped['skillOrder']=active
        scoped['selection']=deepcopy(saved.get('selection') or {'skills':[]})
        scoped['selection']['skills']=[next(row for row in saved['selection']['skills'] if row['name']==name) for name in active]
        scoped['resourceChoices']={name:choice for name,choice in scoped['resourceChoices'].items() if name in active}
    scoped['_course']=course
    return scoped

def merge_scope(base,scoped):
    course=scoped.get('_course')
    if not course:return {k:deepcopy(v) for k,v in scoped.items() if not k.startswith('_course')}
    result=deepcopy(base)
    result.setdefault('courseRecommendations',{})[course]={field:deepcopy(scoped.get(field)) for field in FIELDS}
    return result

def free_cache_valid(recommendations,items):
    if not recommendations:return False
    for skill in recommendations['skills']:
        for kind in ('courses','books'):
            for resource in skill[kind]:
                latest=items.get(resource['id'])
                if not latest or not latest.get('usable'):return False
                if kind=='courses' and (resource.get('cost')!=0 or latest.get('cost')!=0):return False
    return True


def dependency_key(scoped):
    import hashlib,json
    return hashlib.sha256(json.dumps([scoped.get('generationId'),scoped.get('_course'),scoped.get('skillSelectionKey'),scoped.get('skillOrder'),scoped.get('selection')],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def invalidate_course_tail(w,course):
    """바뀐 계획 이후의 자료·과제·검토를 모두 제거하고 다른 계획은 보존한다."""
    if course:
        ((w.get('v2Survey') or {}).get('courseRecommendations') or {}).pop(course,None)
    if w['draft'].get('chosen')==course:w['draftPlan']=None
