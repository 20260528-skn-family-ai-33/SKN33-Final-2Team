"""로드맵 저장 이후 코스·버전별 자료 추천 작업 등록. 화면 열림과 독립."""
from threading import Lock
from app import db,jobs
from app.services.course_recommendations import option_cache_key
_lock=Lock()
_flights={}


def pending(employee,draft,course,option):
    with _lock:
        key=(employee,str(draft),course,option_cache_key(option))
        return (_flights[key] or '') if key in _flights else None


def prepare(employee,draft,courses=None):
    from app.services import drafts
    from app.routers import preassessment as api
    from app.auth import Account
    try:
        with db.tx() as t:
            raw=drafts._row(t,employee,str(draft),lock=False)['draft_choices']
            options=((raw.get('draft') or {}).get('gen') or {}).get('options') or {}
            if not raw.get('v2Survey'):return
        for course,option in options.items():
            if courses is not None and course not in courses:continue
            key=(employee,str(draft),course,option_cache_key(option))
            with _lock:
                if key in _flights:continue
                _flights[key]=None
            def work(_,course=course,key=key):
                try:
                    with db.tx() as t:
                        latest=drafts._row(t,employee,str(draft),lock=False)['draft_choices']
                        current=(((latest.get('draft') or {}).get('gen') or {}).get('options') or {}).get(course)
                        if option_cache_key(current)!=key[-1]:return {}
                    return api.generate_recommendations(str(draft),Account('employee',employee,''),course=course)
                finally:
                    with _lock:_flights.pop(key,None)
            work._resume={'operation':'materials','kwargs':{'employee_id':employee,'draft_id':str(draft),'course':course},'optionKey':key[-1]}
            try:
                jid=jobs.start('learning_generation',employee,f'{draft}:{course}:{key[-1]}',work)
                with _lock:
                    if key in _flights:_flights[key]=jid
            except Exception:
                with _lock:_flights.pop(key,None)
                raise
    except Exception:
        import logging
        logging.getLogger(__name__).exception('로드맵 후속 자료 준비 등록 실패')
