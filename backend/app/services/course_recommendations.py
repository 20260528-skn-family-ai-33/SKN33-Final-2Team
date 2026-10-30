"""V_2 코스별 추천·선택·주차·활동 캐시. 공통 점검 스킬은 유지한다."""
from copy import deepcopy
FIELDS=('recommendations','resourceChoices','durationEstimates','activityProposal')

def scope_view(saved,course):
    if not course:return deepcopy(saved)
    scoped=deepcopy(saved)
    cache=(saved.get('courseRecommendations') or {}).get(course) or {}
    for field in FIELDS:scoped[field]=deepcopy(cache.get(field))
    scoped['resourceChoices']=scoped.get('resourceChoices') or {}
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
