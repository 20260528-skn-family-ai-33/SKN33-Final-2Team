"""V_2 코스별 추천·선택·주차·활동 캐시. 공통 점검 스킬은 유지한다."""
from copy import deepcopy
from hashlib import sha256
import json
FIELDS=('recommendations','resourceChoices','durationEstimates','activityProposal','activityVersions','materialsSelectionKey','skillSelectionKey','learningOutcomes')

def option_cache_key(option):
    """지원 조건 등 비동기 부가 정보와 무관한 자료 버전 식별자."""
    if not option:
        return None
    if option.get('optionId'):
        data = [option['optionId'], option.get('learningSkillsVersion')]
    else:
        data = {key: option.get(key) for key in ('id','name','scope','reason','tagline','acts','weeklyHours',
                'learningSkills','learningSkillsVersion')}
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def archive_course_cache(w, course, option=None):
    """기존 JSON 안에 현재 버전의 추천·선택을 보관한다. DB 스키마 변경 없음."""
    saved = w.get('v2Survey') or {}
    cache = (saved.get('courseRecommendations') or {}).get(course)
    if not cache:
        return
    option = option or (((w['draft'].get('gen') or {}).get('options') or {}).get(course))
    key = cache.get('optionKey') or option_cache_key(option)
    if key:
        cache['optionKey'] = key
        saved.setdefault('courseRecommendationVersions', {}).setdefault(course, {})[key] = deepcopy(dict(cache, optionKey=key))


def prune_course_versions(w, course):
    saved = w.get('v2Survey') or {}
    versions = (saved.get('courseRecommendationVersions') or {}).get(course)
    if not versions:
        return
    generation = w['draft'].get('gen') or {}
    options = (generation.get('hist') or {}).get(course) or [(generation.get('options') or {}).get(course)]
    keep = {option_cache_key(option) for option in options}
    saved['courseRecommendationVersions'][course] = {key: value for key, value in versions.items() if key in keep}


def scope_view(saved,course,option=None):
    if not course:return deepcopy(saved)
    scoped=deepcopy(saved)
    scoped['_course']=course
    key = option_cache_key(option)
    scoped['_optionKey'] = key
    cache=(saved.get('courseRecommendations') or {}).get(course) or {}
    if key and cache.get('optionKey') != key:
        version = ((saved.get('courseRecommendationVersions') or {}).get(course) or {}).get(key)
        cache = version if version is not None else (cache if not cache.get('optionKey') else {})
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
        key=sha256(json.dumps([(option or {}).get('learningSkillsVersion'),sorted(scoped['selection']['skills'],key=lambda row:row['name'])],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
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
    cache = {field:deepcopy(scoped.get(field)) for field in FIELDS}
    if scoped.get('_optionKey'):
        cache['optionKey'] = scoped['_optionKey']
        result.setdefault('courseRecommendationVersions', {}).setdefault(course, {})[scoped['_optionKey']] = deepcopy(cache)
    result.setdefault('courseRecommendations',{})[course] = cache
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


def recommendation_cache_compatible(saved: dict, version: str) -> bool:
    """규칙이 바뀌어도 현재 카탈로그에서 유효한 선택은 재사용한다."""
    recommendations = saved.get('recommendations')
    if not recommendations:
        return False
    choices = saved.get('resourceChoices') or {}
    if (recommendations.get('retrieval') or {}).get('version') != version:
        if not recommendations.get('skills') or not choices:
            return False
        from app.agents.resource_recommendations import RecommendationError, validate_choices
        try:
            validate_choices(recommendations, choices)
        except RecommendationError:
            return False

    selected = {(choice['course'], 'course') for choice in choices.values() if choice.get('course')}
    selected.update((rid, 'book') for choice in choices.values() for rid in choice.get('books') or [])
    if not selected:
        return True
    from app import catalog
    items = catalog.items()
    return all((item := items.get(rid)) and item.get('usable') and item.get('type') == kind
               for rid, kind in selected)


def dependency_key(scoped):
    import hashlib,json
    return hashlib.sha256(json.dumps([scoped.get('generationId'),scoped.get('_course'),scoped.get('_optionKey'),scoped.get('skillSelectionKey'),scoped.get('skillOrder'),scoped.get('selection')],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def invalidate_course_tail(w,course):
    """현재 자료는 버전별로 보관하고 활성 코스 캐시만 비운다."""
    if course:
        archive_course_cache(w,course)
        ((w.get('v2Survey') or {}).get('courseRecommendations') or {}).pop(course,None)
    if w['draft'].get('chosen')==course:w['draftPlan']=None
