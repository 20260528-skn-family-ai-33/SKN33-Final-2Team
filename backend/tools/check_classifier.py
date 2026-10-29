"""실제 로컬 모델의 대표 질문 4개를 점검한다. 독립 평가셋 성능 평가가 아니다."""
from __future__ import annotations

import json

from app.question_classifier import classify

CASES = (
    ('오늘 부산 날씨 알려줘', '범위 밖'),
    ('연차휴가는 며칠 사용할 수 있나요?', '사내 규정'),
    ('구내식당 식단은 어디서 확인하나요?', '사내 생활안내'),
    ('한국수자원공사는 어떤 일을 하는 기관인가요?', '수자원공사 정보'),
)


def main() -> None:
    matched = 0
    for question, expected in CASES:
        result = classify(question)
        matched += result['label'] == expected
        print(json.dumps({'question': question, 'expected': expected, **result}, ensure_ascii=False))
    print(json.dumps({'smoke_cases': len(CASES), 'matched': matched}, ensure_ascii=False))
    if matched != len(CASES):
        raise SystemExit('대표 질문 중 예상과 다른 분류가 있어요. 학습 담당자 검토가 필요해요.')


if __name__ == '__main__':
    main()
