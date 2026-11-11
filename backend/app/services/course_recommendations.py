"""V_2 코스별 추천·선택·주차·활동 캐시. 공통 점검 스킬은 유지한다."""
from copy import deepcopy
from hashlib import sha256
import json
from app import db
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

def completed_course_ids(t: db.Tx, employee_id: int) -> frozenset[str]:
    """이 직원이 실제 로드맵에서 완료한 강좌 ID. 보관한 로드맵의 이수도 포함한다."""
    rows = t.all("""
        SELECT DISTINCT resource.course_id
        FROM public.projects p
        JOIN public.roadmaps r ON r.project_id = p.project_id
        JOIN public.roadmap_steps step ON step.roadmap_id = r.roadmap_id
        JOIN public.roadmap_step_resources resource ON resource.step_id = step.step_id
        WHERE p.employee_id = :employee_id AND step.is_completed AND resource.course_id IS NOT NULL
          AND (p.draft_choices ->> 'demoSeeded') IS DISTINCT FROM 'true'
        """, employee_id=employee_id)
    return frozenset(row['course_id'] for row in rows)


def available_recommendations(recommendations: dict, course: str | None, *, refresh: bool = False,
                              completed: frozenset[str] = frozenset()) -> dict:
    """추천 근거는 보존하고 현재 선택할 수 없는 후보와 기본 선택만 제거한다."""
    from app import catalog
    rows = recommendations.get('skills') or []
    items = catalog.items(refresh=refresh) if any(row['courses'] or row['books'] for row in rows) else {}

    def available(resource: dict, kind: str) -> bool:
        item = items.get(resource['id'])
        return bool(item and item.get('usable') and item.get('type') == kind
                    and (course != 'A1' or kind != 'course' or item.get('cost') == resource.get('cost') == 0))

    filtered = []
    for row in rows:
        courses = catalog.refresh_course_levels([item for item in row['courses']
                                                if item['id'] not in completed and available(item, 'course')], items)
        books = catalog.refresh_book_links([item for item in row['books'] if available(item, 'book')], items)
        result = dict(row, courses=courses, books=books)
        if 'selectedCourse' in row and not any(item['id'] == row['selectedCourse'] for item in courses):
            result['selectedCourse'] = None
        if 'selectedBooks' in row:
            book_ids = {item['id'] for item in books}
            result['selectedBooks'] = [rid for rid in row['selectedBooks'] if rid in book_ids]
        filtered.append(result)
    result = dict(recommendations, skills=filtered)
    retrieval = recommendations.get('retrieval') or {}
    if completed and 'matches' in retrieval:
        result['retrieval'] = dict(retrieval, matches=[m for m in retrieval['matches'] if m['resourceId'] not in completed])
    return result


def compatible_recommendations(saved: dict, version: str, completed: frozenset[str] = frozenset()) -> dict | None:
    """선택이 유효하면 추천 규칙이 바뀌어도 남은 후보를 재사용한다."""
    from app.agents.resource_recommendations import RecommendationError, validate_choices
    recommendations = saved.get('recommendations')
    if not recommendations:
        return None
    choices = saved.get('resourceChoices') or {}
    outdated = (recommendations.get('retrieval') or {}).get('version') != version
    if outdated and (not recommendations.get('skills') or not choices):
        return None
    available = available_recommendations(recommendations, saved.get('_course'), completed=completed)
    # 이전에 제시한 강좌를 모두 이수했다면 빈 캐시 대신 더 낮은 순위의 후보를 다시 검색한다.
    if any(row['courses'] and all(c['id'] in completed for c in row['courses']) for row in recommendations['skills']):
        return None
    if choices:
        try:
            validate_choices(available, choices)
        except RecommendationError:
            return None
    return available


def dependency_key(scoped):
    import hashlib,json
    return hashlib.sha256(json.dumps([scoped.get('generationId'),scoped.get('_course'),scoped.get('_optionKey'),scoped.get('skillSelectionKey'),scoped.get('skillOrder'),scoped.get('selection')],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def invalidate_course_tail(w,course):
    """현재 자료는 버전별로 보관하고 활성 코스 캐시만 비운다."""
    if course:
        archive_course_cache(w,course)
        ((w.get('v2Survey') or {}).get('courseRecommendations') or {}).pop(course,None)
    if w['draft'].get('chosen')==course:w['draftPlan']=None
