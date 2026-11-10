"""보고서 생성 시점의 실제 실행 기록을 고정한다. 계획된 활동을 완료로 간주하지 않는다."""
from copy import deepcopy
from datetime import datetime, timezone


def capture(plan,progress,now=None):
    activities=[]
    for act in plan['acts']:
        record=progress.get(act['id']) or {}
        activities.append({'id':act['id'],'title':act['title'],'skill':act.get('skill') or '',
            'status':'done' if record.get('status')=='done' else 'doing',
            'memo':record.get('memo') or '', 'file':deepcopy(record.get('file')),
            'task':not bool(act.get('res')),'requirements':act.get('how') or ''})
    return {'asOf':(now or datetime.now(timezone.utc)).isoformat(),'version':plan.get('version'),
        'early':any(act['status']!='done' for act in activities),'activities':activities}


def matches(snapshot,plan,progress):
    current=capture(plan,progress)
    # 도서를 진척에서 빼기 전에 만든 보고서도 확인할 수 있게 지금 기준의 활동만 비교한다. 같은 버전이면 활동 구성은 같다.
    ids={act['id'] for act in current['activities']}
    recorded=[act for act in snapshot.get('activities') or [] if act['id'] in ids]
    return snapshot.get('version')==current['version'] and recorded==current['activities']


def evidence(snapshot):
    return {'asOf':snapshot['asOf'],'early':snapshot['early'],'activities':[
        {'title':act['title'],'skill':act['skill'],'status':act['status'],'memo':act['memo'],
         'task':act['task'],'requirements':act['requirements'],
         'attachmentSubmitted':bool(act['file']),'attachmentContentVerified':False}
        for act in snapshot['activities']]}
