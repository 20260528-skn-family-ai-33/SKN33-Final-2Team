"""도서는 세 코스에 같은 정책으로 공통 후보 최대 30권을 제공한다."""
from copy import deepcopy
from app import catalog_candidates as evidence
from app.services import resource_evidence

REVIEW_LIMIT = 30
LIMIT = 30
MIN_PER_SKILL = 3
DESCRIPTION_CHARS = 180


def _rank(rows: list[dict], skill: dict) -> list[dict]:
    # 넓은 태그의 벡터 점수만으로 비동기 같은 구체적인 학습 대상이 밀리지 않게 한다.
    # 관련 표현의 반복 횟수는 가점하지 않고 동점에서는 검색 순위를 유지한다.
    terms = resource_evidence.focus_terms({}, skill)
    if not terms:
        return rows
    def score(row):
        title = resource_evidence.normalize(row.get('title')).casefold()
        content = resource_evidence.normalize(row.get('content')).casefold()
        return (min(evidence.matches(title, terms), 3),
                min(evidence.matches(title + '\n' + content, terms), 5))
    return sorted(rows, key=score, reverse=True)


def common_pool(pools: list[dict], items: dict, *, limit: int | None = None,
                selection: dict | None = None) -> tuple[list[dict], list[dict]]:
    """스킬별 3권을 먼저 확보한 뒤 공통 30권을 채운다. 실제 후보 부족은 숨기지 않는다."""
    limit = LIMIT if limit is None else limit
    details = {row['name']: row for row in (selection or {}).get('skills', [])}
    available = {}
    origins = {}
    for pool in pools:
        for row in pool['books']:
            source = items.get(row['id']) or {}
            if (source.get('usable') and source.get('type') == 'book'
                    and pool['name'] in (source.get('skills') or [])):
                available.setdefault(row['id'], row)
                origins.setdefault(row['id'], pool['name'])
    ranked = []
    for pool in pools:
        local = {row['id']: row for row in pool['books'] if row['id'] in available}
        eligible = {**local, **{key: row for key, row in available.items() if key not in local}}
        rows = [row for key, row in eligible.items() if pool['name'] in (items[key].get('skills') or [])]
        ranked.append(_rank(rows, details.get(pool['name'], pool)))

    selected = {}
    # 최대 3스킬이므로 기본 한도 30권 안에서 스킬별 3권(최대 9권)을 보존할 수 있다.
    for rows in ranked:
        for row in rows[:MIN_PER_SKILL]:
            selected.setdefault(row['id'], row)
    if len(selected) > limit:
        raise ValueError('공통 도서 한도가 스킬별 최소 후보를 담기에 부족합니다.')
    for rank in range(max((len(rows) for rows in ranked), default=0)):
        for rows in ranked:
            if rank >= len(rows):
                continue
            row = rows[rank]
            if row['id'] not in selected and len(selected) < limit:
                selected[row['id']] = row
        if len(selected) >= limit:
            break
    result = []
    for pool, rows in zip(pools, ranked):
        local = {row['id']: row for row in pool['books']}
        books = []
        for row in rows:
            key = row['id']
            if key not in selected:
                continue
            card = deepcopy(local.get(key) or row)
            if key not in local:
                card.pop('retrievalScore', None)
                card.update(sharedCandidate=True, sourceSkill=origins[key])
            books.append(card)
        result.append({**pool, 'books': books, 'bookCandidateTarget': MIN_PER_SKILL,
                       'bookCandidateCount': len(books), 'bookCandidateShortfall': max(0, MIN_PER_SKILL-len(books))})
    return result, [deepcopy(row) for row in selected.values()]


def model_catalog(books: list[dict], items: dict, names: list[str]) -> list[dict]:
    """모델에는 책마다 한 행과 현재 선정 스킬의 연결만 전달한다."""
    return [{'choiceKey': f'B{index}',
             **{key: deepcopy(row.get(key)) for key in ('title', 'provider', 'cost', 'hours', 'estimated')},
             'eligibleSkills': [name for name in names if name in (items[row['id']].get('skills') or [])],
             'content': str(row.get('content') or '')[:DESCRIPTION_CHARS]}
            for index, row in enumerate(books, 1)]
