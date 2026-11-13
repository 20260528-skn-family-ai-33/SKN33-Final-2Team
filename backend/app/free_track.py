"""무료 강좌 조건을 확정하는 트랜잭션에서 최신 가격을 잠그고 검증한다."""
from . import db
from .course_levels import zero_budget
from .errors import ApiError


def validate_free_plan(t: db.Tx, plan: dict, *, budget=None) -> None:
    free_track = plan.get('opt') == 'A1'
    if not free_track and not zero_budget(budget):
        return
    keys = sorted({a['res'] for a in plan.get('acts', []) if a.get('res')})
    if keys:
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

        if any(key not in prices or violates_price(prices[key]) for key in keys):
            if free_track:
                raise ApiError(409, 'FREE_TRACK_PRICE_CHANGED',
                               'Free Course에 유료·비용 미확인 강좌 또는 삭제된 자료가 있어요. 최신 무료 자료로 다시 생성하거나 다른 코스를 선택해 주세요.')
            raise ApiError(409, 'ZERO_BUDGET_PRICE_CHANGED',
                           '예산 0원으로 선택할 수 없는 자료가 있어요. 최신 무료 강좌로 다시 선택해 주세요.')
    # 강좌 0원 조건을 검증하고 도서는 최신 가격을 합산한다. 미확인 도서 가격은 별도 표시한다.
    plan['cost'] = sum(prices[key]['cost_won'] or 0 for key in keys) if keys else 0
    plan['costUnknown'] = any(prices[key]['cost_won'] is None for key in keys) if keys else False
