"""Selected skills and completed answers: pure validation, no database access."""
from copy import deepcopy
from app.agents.skill_selection import SelectionError
from app.track_policy import MAX_SKILLS


def checked_skills(rows, available):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_SKILLS:
        raise SelectionError(f'학습할 스킬을 1~{MAX_SKILLS}개 선택해 주세요.')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or row.get('name') not in available or row['name'] in seen:
            raise SelectionError('선택 스킬의 이름과 중복 여부를 확인해 주세요.')
        if not isinstance(row.get('application'), str) or not row['application'].strip():
            raise SelectionError('선택한 스킬의 학습 내용을 확인해 주세요.')
        seen.add(row['name'])
    return {'skills': [dict(deepcopy(row), reason=row.get('reason') or row['application']) for row in rows]}
