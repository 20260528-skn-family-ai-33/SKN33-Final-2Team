"""무료 강좌 조건을 확정하는 트랜잭션에서 최신 가격을 잠그고 검증한다."""
from . import db
from .course_levels import book_cost, zero_budget
from .errors import ApiError


def validate_free_plan(t: db.Tx, plan: dict, *, budget=None, previous: dict | None = None) -> None:
    free_track = plan.get('opt') == 'A1'
    if not free_track and not zero_budget(budget):
        return
    activities = [a for a in plan.get('acts', []) if a.get('res')]
    keys = sorted({a['res'] for a in activities})
    if keys:
        # 수정 전부터 같은 활동에 배정된 자료는 0원 예산에서 다시 구매할 강좌로 보지 않는다.
        retained = {(a['id'], a['res']) for a in (previous or {}).get('acts', [])
                    if a.get('id') and a.get('res')}
        check_price = {a['res'] for a in activities
                       if free_track or (a.get('id'), a['res']) not in retained}
        rows = t.all(
            'SELECT m.resource_key, m.resource_type, m.cost_won, '
            "coalesce(c.content_status, b.content_status, x.content_status, '') = 'deleted' AS deleted "
            'FROM app_ext.resource_meta m '
            'LEFT JOIN public.courses c ON c.course_id = m.course_id '
            'LEFT JOIN public.books b ON b.isbn = m.isbn '
            'LEFT JOIN public.certifications x ON x.cert_id = m.cert_id '
            'WHERE m.resource_key = ANY(CAST(:keys AS text[])) '
            'ORDER BY m.resource_key FOR SHARE OF m',
            keys=keys,
        )
        prices = {r['resource_key']: r for r in rows if not r.get('deleted')}
        def violates_price(row):
            restricted = row.get('resource_type') != 'book' if free_track else row.get('resource_type') == 'course'
            return restricted and row['cost_won'] != 0

        if any(key not in prices for key in keys) or any(violates_price(prices[key]) for key in check_price):
            if free_track:
                raise ApiError(409, 'FREE_TRACK_PRICE_CHANGED',
                               'Free Course에 유료·비용 미확인 강좌 또는 삭제된 자료가 있어요. 최신 무료 자료로 다시 생성하거나 다른 코스를 선택해 주세요.')
            raise ApiError(409, 'ZERO_BUDGET_PRICE_CHANGED',
                           '예산 0원으로 선택할 수 없는 자료가 있어요. ' +
                           ('무료 강좌로 수정안을 다시 요청해 주세요.' if previous is not None else '최신 무료 강좌로 다시 선택해 주세요.'))
    # 강좌 0원 조건을 검증하고 최신 가격을 합산한다. 도서는 가격을 받지 않아 0원으로 본다.
    costs = [book_cost(prices[key].get('resource_type'), prices[key]['cost_won']) for key in keys]
    plan['cost'] = sum(cost or 0 for cost in costs)
    plan['costUnknown'] = any(cost is None for cost in costs)
