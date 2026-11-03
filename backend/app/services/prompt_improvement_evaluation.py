"""개선안 생성 모델의 자기 승인과 운영 적용을 분리하는 비교 평가 문턱."""
import math

CHECKS = frozenset(('schema', 'projectScope', 'freePolicy', 'crashPolicy', 'challengePolicy', 'knownKnowledge', 'security'))
SCORES = frozenset(('projectFit', 'clarity', 'actionability', 'constraints'))


def evaluate_gate(baseline: list[dict], candidate: list[dict]) -> dict:
    """별도 평가기가 같은 사례에 대해 만든 검사·0~1 점수를 비교한다. DB 쓰기 없음.

점수 생성 방법과 평가 사례는 실행 담당에서 제공한다. 개선안 LLM의 응답을 그대로
평가 결과로 간주하지 않으며, 평가 증거가 불완전하면 적용을 승인하지 않는다.
"""
    def index(rows):
        if not isinstance(rows, list) or not rows:
            raise ValueError('비교 평가 사례가 없습니다.')
        result = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('caseId'), str) or not row['caseId'] or row['caseId'] in result:
                raise ValueError('평가 사례 식별자가 없거나 중복되었습니다.')
            if not isinstance(row.get('checks'), dict) or set(row['checks']) != CHECKS or any(type(value) is not bool for value in row['checks'].values()):
                raise ValueError('필수 정합성 검사 결과가 부족합니다.')
            scores = row.get('scores')
            if not isinstance(scores, dict) or set(scores) != SCORES or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1 for value in scores.values()):
                raise ValueError('평가 점수는 모든 항목의 유한한 0~1 값이어야 합니다.')
            result[row['caseId']] = row
        return result
    try:
        old, new = index(baseline), index(candidate)
        if set(old) != set(new):
            raise ValueError('기존·개선 프롬프트의 평가 사례가 다릅니다.')
    except ValueError as error:
        return {'approved': False, 'reason': str(error)}
    if any(not all(row['checks'].values()) for row in new.values()):
        return {'approved': False, 'reason': '개선안의 필수 정합성 검사가 실패했습니다.'}
    improved = False
    for case in old:
        for key in SCORES:
            before, after = old[case]['scores'][key], new[case]['scores'][key]
            if after < before:
                return {'approved': False, 'reason': '기존보다 악화된 평가 항목이 있습니다.'}
            improved |= after > before
    return {'approved': bool(improved), 'reason': '동일 사례에서 개선·악화 없음·필수 검사 통과' if improved else '기존 대비 개선이 확인되지 않았습니다.',
            'caseCount': len(old)}
