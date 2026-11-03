"""도서는 세 코스에 같은 정책으로 공통 후보 최대 30권을 제공한다."""
from copy import deepcopy

REVIEW_LIMIT = 30
LIMIT = 30
DESCRIPTION_CHARS = 180


def common_pool(pools: list[dict], items: dict, *, limit: int | None = None) -> tuple[list[dict], list[dict]]:
    """스킬 순서대로 교차 선택해 책을 모으고 실제 태그로 각 스킬의 선택 범위를 연결한다."""
    limit = LIMIT if limit is None else limit
    selected = {}
    origins = {}
    for rank in range(max((len(pool['books']) for pool in pools), default=0)):
        for pool in pools:
            if rank >= len(pool['books']):
                continue
            row = pool['books'][rank]
            source = items.get(row['id']) or {}
            if not source.get('usable') or source.get('type') != 'book':
                continue
            if row['id'] not in selected and len(selected) < limit:
                selected[row['id']] = row
                origins[row['id']] = pool['name']
        if len(selected) >= limit:
            break
    result = []
    for pool in pools:
        local = {row['id']: row for row in pool['books']}
        books = []
        for key, row in selected.items():
            if pool['name'] not in (items[key].get('skills') or []):
                continue
            card = deepcopy(local.get(key) or row)
            if key not in local:
                card.pop('retrievalScore', None)
                card.update(sharedCandidate=True, sourceSkill=origins[key])
            books.append(card)
        result.append({**pool, 'books': books})
    return result, [deepcopy(row) for row in selected.values()]


def model_catalog(books: list[dict], items: dict, names: list[str]) -> list[dict]:
    """모델에는 책마다 한 행과 현재 선정 스킬의 연결만 전달한다."""
    return [{'choiceKey': f'B{index}',
             **{key: deepcopy(row.get(key)) for key in ('title', 'provider', 'cost', 'hours', 'estimated')},
             'eligibleSkills': [name for name in names if name in (items[row['id']].get('skills') or [])],
             'content': str(row.get('content') or '')[:DESCRIPTION_CHARS]}
            for index, row in enumerate(books, 1)]
