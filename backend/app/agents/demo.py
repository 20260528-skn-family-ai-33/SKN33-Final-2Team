"""가데이터(시연용 고정 응답) 자료.

화면 문구·척도·관점처럼 고정된 값은 4차 gp-data.js 에서 옮긴 demo_data.json 을 쓴다.
가데이터 로드맵 안(RAG 시나리오)은 팀 DB의 실제 강좌·도서 키로 다시 짰다(4차의 가상 강좌·공식 문서는 쓰지 않음 · 사용자 결정).
팀 DB에서 그 자료가 지워지면 그 활동은 안에서 빠진다(finish_option 이 목록에 없는 자료를 뺌).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

D = json.loads((Path(__file__).with_name('demo_data.json')).read_text(encoding='utf-8'))
for _d in D['domains'].values():
    _d['re'] = re.compile(_d['test'], re.I if 'i' in _d['flags'] else 0)


def domain_of(goal: str) -> str:
    return next((k for k, v in D['domains'].items() if v['re'].search(goal or '')), 'rag')


def skill_label(s: str) -> str:
    return D['skills'].get(s, s)


# 팀 DB 자료 키 (2026-10-22 백업 기준 · 팀이 학습 자료를 IT 분야로 다시 모아 10/21 키 10개가 모두 빠져 다시 고름 · 2026-10-22 사용자 결정)
# MS Learn 은 비용 0원, K-MOOC·도서는 비용 '확인 필요'. 맞는 자료가 없는 활동(생성형 AI·RAG 개념, 프롬프트, 위험 점검)은 직접 수행 과제로 바꿨다
R = {
    'python': 'MS_16b4312ecd92',       # 첫 번째 Python 코드 작성 (MS Learn · 입문 · 10/21 의 같은 강좌가 다른 키로 남음)
    'ragsql': 'MS_d27d12b003b6',       # SQL을 사용하여 RAG 디자인 및 구현 (MS Learn · 중급 · 10/21 의 같은 강좌가 다른 키로 남음)
    'agentmem': 'MS_7f3f508b9083',     # Azure Cosmos DB 에이전트 메모리 저장소 디자인 및 구현 (MS Learn · 중급)
    'genai': 'KMOOC_21288',            # AI와의 첫 만남 : 생성형 인공지능으로 보는 미래 (K-MOOC · 15주)
    'llmbook': 'book_9791194587347',   # LLM 프로덕션 엔지니어링 : 프롬프트, RAG, 파인튜닝으로 설계하는 신뢰성 높은 생성형 AI 시스템 (도서)
    'ragbook': 'book_9791194587842',   # 라마인덱스로 배우는 데이터 기반 AI 애플리케이션 : 생성형 AI와 RAG 실전 LLM 개발 (도서)
}

# 직접 수행 과제가 다루는 스킬(팀 DB skill_tags 이름 · 2026-10-23 사용자 확인 표). 자료 활동은 자료에 붙은 DB 스킬을 쓰므로 적지 않는다.
# 이름이 팀 DB와 달라지면 finish_option 이 버리고 화면이 같은 단계 자료의 스킬로 채운다
SK = {'rag': 'RAG & 생성형 AI 에이전트', 'llm': '자연어 처리(NLP) & LLM 기초', 'py': 'Python 프로그래밍 & 비동기 I/O',
      'gov': '데이터 거버넌스 & 보안 규정 준수', 'etl': 'ETL & 데이터 파이프라인', 'nosql': 'NoSQL & 분산 DB'}

TEMPLATES = {
    'A1': {'tagline': 'MS Learn 무료 강좌와 직접 실습으로 비용 없이', 'reason': '비용이 0원으로 확인된 MS Learn 강좌와 직접 실습만 써서 교육비가 들지 않아요.',
           'pros': ['교육 비용 0원(MS Learn)', '짧은 모듈을 필요할 때 반복해 보기 쉬워요'], 'cons': ['자료를 직접 연결하고 오류를 해결할 시간이 필요해요'],
           'scope': '공개 샘플 문서로 질의응답 최소 기능',
           'acts': [{'stage': 1, 'title': '첫 번째 Python 코드 작성 복습', 'res': R['python']},
                    {'stage': 1, 'title': '생성형 AI·RAG 동작 순서 한 장으로 정리', 'hours': 2, 'how': '문서 나누기 → 임베딩 → 검색 → 답변 생성 순서를 그림 한 장으로 정리해요.', 'skills': [SK['rag'], SK['llm']]},
                    {'stage': 2, 'title': 'SQL로 RAG 디자인·구현 모듈 따라 하기', 'res': R['ragsql']},
                    {'stage': 2, 'title': '문서 분할·검색 방법을 작은 예제로 비교', 'hours': 4, 'how': '같은 문서를 두세 가지 방식으로 나눠 검색 결과를 비교해 보세요.', 'skills': [SK['rag'], SK['py']]},
                    {'stage': 3, 'title': '공개 샘플 문서로 질의응답 최소 기능 구현', 'hours': 12, 'how': '공개된 샘플 문서로 질문을 받고 관련 문단을 찾아 답하는 기능을 만들어요.', 'skills': [SK['rag'], SK['llm'], SK['py']]},
                    {'stage': 3, 'title': '답변 근거를 원문과 대조하는 방법 정리', 'hours': 4, 'how': '답변마다 근거 문단을 함께 보여주고, 원문과 맞는지 확인하는 순서를 정리해요.', 'skills': [SK['rag']]},
                    {'stage': 4, 'title': '결과물 정리와 시연 메모 작성', 'hours': 4, 'how': '만든 기능과 한계를 한 장으로 정리해요.', 'skills': [SK['rag']]}]},
    'A2': {'tagline': '핵심 강좌 둘과 필수 실습만 짧게', 'reason': '짧은 MS Learn 모듈 둘과 꼭 필요한 실습만 담아 가장 빨리 끝나요.',
           'pros': ['기간이 가장 짧아요', '주마다 할 일이 단순해요'], 'cons': ['깊이 있는 실습은 적어요', '사내 문서 적용은 다음 계획으로 미뤄요'],
           'scope': '강좌 예제 범위의 질의응답 데모',
           'acts': [{'stage': 1, 'title': '첫 번째 Python 코드 작성 복습', 'res': R['python']},
                    {'stage': 2, 'title': 'SQL로 RAG 디자인·구현 모듈 수강', 'res': R['ragsql']},
                    {'stage': 2, 'title': '강좌 예제로 RAG 데모 실행', 'hours': 2, 'how': '강좌에서 제공하는 예제를 그대로 실행해 동작을 확인해요.', 'skills': [SK['rag'], SK['py']]},
                    {'stage': 3, 'title': '예제 범위의 질의응답 데모 완성', 'hours': 6, 'how': '예제 문서를 바꿔 넣고 질문·답변이 되는지 확인해요.', 'skills': [SK['rag'], SK['py']]},
                    {'stage': 4, 'title': '데모 결과 정리', 'hours': 2, 'how': '되는 것과 안 되는 것을 짧게 정리해요.', 'skills': [SK['rag']]}]},
    'A3': {'tagline': '사내 규정 문서로 시제품 만들기', 'reason': '생성형 AI 영상 강좌와 RAG 실전 도서로 익힌 뒤 사내 규정 문서로 시제품을 만들어, 목표한 결과물을 바로 얻어요.',
           'pros': ['업무에 쓸 시제품이 결과물로 남아요', 'K-water GPT·Water-Chat과 같은 분야를 직접 다뤄요'],
           'cons': ['기간이 가장 길어요', '사내 문서를 쓸 수 있는 범위를 먼저 확인해야 해요', 'K-MOOC 수강료·도서 가격은 확인이 필요해요'],
           'scope': '공개 가능한 사내 규정 문서로 근거 조항을 보여주는 시제품',
           'acts': [{'stage': 1, 'title': '생성형 AI 첫 만남(K-MOOC) 수강', 'res': R['genai']},
                    {'stage': 2, 'title': '「라마인덱스로 배우는 데이터 기반 AI 애플리케이션」 읽기', 'res': R['ragbook']},
                    {'stage': 3, 'title': '공개 가능한 사내 규정 문서 10건 정리·색인', 'hours': 6, 'how': '공개해도 되는 규정 문서만 골라 조항 단위로 나누고 색인을 만들어요.', 'skills': [SK['gov'], SK['etl']]},
                    {'stage': 3, 'title': '질문에 근거 조항을 함께 보여주는 시제품 구현', 'hours': 14, 'how': '질문을 받으면 관련 조항을 찾아 답변과 함께 조항 번호를 보여줘요.', 'skills': [SK['rag'], SK['llm'], SK['py']]},
                    {'stage': 3, 'title': '답변·원문 대조 품질 점검 20문항', 'hours': 4, 'how': '질문 20개로 답변이 원문 조항과 맞는지 하나씩 확인해요.', 'skills': [SK['rag'], SK['llm']]},
                    {'stage': 4, 'title': '시제품 시연과 결과 정리', 'hours': 4, 'how': '팀에 시연하고 받은 의견과 한계를 정리해요.', 'skills': [SK['rag']]}]},
}
# '이 안만 다시 만들기'를 누르면 번갈아 쓰는 두 번째 구성
TEMPLATES_ALT = {
    'A1': {'tagline': 'MS Learn 실습 모듈로 직접 만들어 보기', 'reason': '강의 대신 MS Learn 실습 모듈을 따라 하며 무료로 익혀요.',
           'pros': ['교육 비용 0원(MS Learn)', '실제 코드 흐름을 바로 익혀요'], 'cons': ['막히는 부분을 스스로 찾아 해결해야 해요'],
           'scope': '실습 모듈을 바탕으로 한 문서 검색기',
           'acts': [{'stage': 1, 'title': '첫 번째 Python 코드 작성 복습', 'res': R['python']},
                    {'stage': 2, 'title': 'SQL로 RAG 디자인·구현 모듈 따라 하기', 'res': R['ragsql']},
                    {'stage': 2, 'title': 'Cosmos DB 에이전트 메모리 저장소 모듈 따라 하기', 'res': R['agentmem']},
                    {'stage': 2, 'title': '실습 모듈대로 문서 검색기 만들기', 'hours': 6, 'how': '문서 로딩부터 벡터 검색까지 모듈 예제를 그대로 따라 만들어요.', 'skills': [SK['rag'], SK['nosql'], SK['py']]},
                    {'stage': 3, 'title': '공개 샘플 문서로 질의응답 기능 구현', 'hours': 14, 'how': '만든 검색기에 질문·답변 단계를 붙여 샘플 문서로 시험해요.', 'skills': [SK['rag'], SK['llm'], SK['py']]},
                    {'stage': 3, 'title': '답변에 근거 문단 표시 추가', 'hours': 4, 'how': '답변마다 어느 문단을 근거로 썼는지 함께 보여줘요.', 'skills': [SK['rag']]},
                    {'stage': 4, 'title': '결과 정리와 다음 과제 메모', 'hours': 3, 'how': '만든 기능과 한계, 다음에 해 볼 것을 정리해요.', 'skills': [SK['rag']]}]},
    'A2': {'tagline': '프롬프트 연습과 RAG 모듈 하나로 가장 짧게', 'reason': '프롬프트는 직접 연습하고 RAG는 MS Learn 모듈 하나만 따라 해 비용 없이 빨리 끝나요.',
           'pros': ['기간이 짧고 비용이 없어요'], 'cons': ['강좌 범위를 넘는 내용은 따로 찾아야 해요', '사내 문서 적용은 다음 계획으로 미뤄요'],
           'scope': '강좌 예제 범위의 질의응답 데모',
           'acts': [{'stage': 1, 'title': '프롬프트 작성 요령 정리와 연습', 'hours': 2, 'how': '같은 질문을 지시·예시·답 형식을 바꿔 써 보며 답이 어떻게 달라지는지 기록해요.', 'skills': [SK['llm'], SK['rag']]},
                    {'stage': 2, 'title': 'SQL로 RAG 디자인·구현 모듈 수강', 'res': R['ragsql']},
                    {'stage': 2, 'title': '강좌 예제로 RAG 데모 실행', 'hours': 2, 'how': '강좌 예제를 그대로 실행해 동작을 확인해요.', 'skills': [SK['rag'], SK['py']]},
                    {'stage': 3, 'title': '예제 범위의 질의응답 데모 완성', 'hours': 6, 'how': '예제 문서를 바꿔 넣고 질문·답변이 되는지 확인해요.', 'skills': [SK['rag'], SK['py']]},
                    {'stage': 4, 'title': '데모 결과 정리', 'hours': 2, 'how': '되는 것과 안 되는 것을 짧게 정리해요.', 'skills': [SK['rag']]}]},
    'A3': {'tagline': '규정 질의응답 시제품과 품질 점검까지', 'reason': '사내 규정 문서로 시제품을 만들고, 답변 위험 점검에 시간을 더 써요.',
           'pros': ['업무에 쓸 시제품이 남아요', '답변 품질·위험을 기준을 정해 확인해요'],
           'cons': ['기간이 길어요', '사내 문서를 쓸 수 있는 범위를 먼저 확인해야 해요', '도서 가격은 확인이 필요해요'],
           'scope': '근거 조항을 보여주고 품질 점검 기록을 남긴 규정 질의응답 시제품',
           'acts': [{'stage': 1, 'title': '첫 번째 Python 코드 작성 복습', 'res': R['python']},
                    {'stage': 2, 'title': 'SQL로 RAG 디자인·구현 모듈 따라 하기', 'res': R['ragsql']},
                    {'stage': 2, 'title': '「LLM 프로덕션 엔지니어링」의 프롬프트·RAG 장 읽기', 'res': R['llmbook']},
                    {'stage': 3, 'title': '공개 가능한 사내 규정 문서 10건 정리·색인', 'hours': 6, 'how': '공개해도 되는 규정 문서만 골라 조항 단위로 나누고 색인을 만들어요.', 'skills': [SK['gov'], SK['etl']]},
                    {'stage': 3, 'title': '질문에 근거 조항을 함께 보여주는 시제품 구현', 'hours': 12, 'how': '질문을 받으면 관련 조항을 찾아 답변과 함께 조항 번호를 보여줘요.', 'skills': [SK['rag'], SK['llm'], SK['py']]},
                    {'stage': 3, 'title': '생성형 AI 답변 위험 점검 기준 정리', 'hours': 3, 'how': '틀린 근거·개인정보 노출·지나친 단정 같은 위험을 항목으로 나누고 점검 기준을 정해요.', 'skills': [SK['gov'], SK['rag']]},
                    {'stage': 3, 'title': '답변·원문 대조 품질 점검 30문항', 'hours': 6, 'how': '질문 30개로 답변이 원문 조항과 맞는지 기준표로 확인해요.', 'skills': [SK['rag'], SK['llm']]},
                    {'stage': 4, 'title': '시제품 시연과 결과 정리', 'hours': 4, 'how': '팀에 시연하고 받은 의견과 한계를 정리해요.', 'skills': [SK['rag']]}]},
}

GOAL_RULES = [
    (r'(규정|매뉴얼|문서|검색|근거)', '사내 규정·매뉴얼 문서에서 근거를 찾아 주는 RAG 검색 도구를 만들고 싶어요.'),
    (r'(API|백엔드|FastAPI|서비스)', '사내 서비스 API에 생성형 AI 기능을 연결하고 응답 품질을 점검하고 싶어요.'),
    (r'(데이터|지표|정제|pandas|누락|적재)', '운영 데이터의 이상값을 AI로 찾아내고 결과를 검증하는 역량을 기르고 싶어요.'),
    (r'(로그|장애|배포|서버)', '운영 로그를 생성형 AI로 요약하고 장애 원인 후보를 찾는 도구를 만들고 싶어요.'),
    (r'(화면|UI|React|TypeScript|대시보드|포털)', '업무 포털 화면에 AI 도우미 기능을 넣고 사용성을 점검하고 싶어요.'),
    (r'(인사|엑셀|현황 표|계정)', '엑셀로 하던 현황 정리를 생성형 AI와 간단한 자동화로 줄이고 싶어요.'),
    (r'(Python|파이썬|스크립트)', 'Python 업무 스크립트에 생성형 AI API를 붙여 반복 작업을 줄이고 싶어요.'),
]
