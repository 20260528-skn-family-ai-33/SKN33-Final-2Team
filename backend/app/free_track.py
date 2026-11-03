"""Free Track 저장 직전 가격 검증. 호출자의 저장 트랜잭션과 가격 행 잠금을 공유한다."""
from . import db
from .errors import ApiError


def validate_free_plan(t: db.Tx, plan: dict) -> None:
    if plan.get('opt') != 'A1':
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
        if any(key not in prices or (prices[key].get('resource_type') != 'book' and prices[key]['cost_won'] != 0) for key in keys):
            raise ApiError(409, 'FREE_TRACK_PRICE_CHANGED',
                           'Free Course에 유료·비용 미확인 강좌 또는 삭제된 자료가 있어요. 최신 무료 자료로 다시 생성하거나 다른 Track을 선택해 주세요.')
    # 강좌 0원 조건을 검증하고 도서는 최신 가격을 합산한다. 미확인 도서 가격은 별도 표시한다.
    plan['cost'] = sum(prices[key]['cost_won'] or 0 for key in keys) if keys else 0
    plan['costUnknown'] = any(prices[key]['cost_won'] is None for key in keys) if keys else False
