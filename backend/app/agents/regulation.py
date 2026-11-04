"""규정 에이전트 · 사내 생활 도우미(API-09) / 안별 지원 조건 확인 (4차 gp-ai.js · 4차 묶음 5·7).

실제 모드는 로컬 RoBERTa로 먼저 질문을 4분류하고, 규정 검색·LLM 답변으로 연결한다.
가데이터 챗봇은 추천 질문에 시연용 답을 제공한다.
  regulation  규정·인사 제도 — 내 직원 구분의 등록 규정에 명시된 경우에만 근거와 함께. 없으면 답하지 않고 담당 부서 안내
  general     회사 정보는 실제 DB 원문, 사내 생활은 등록된 가상 홈페이지 메뉴 안내만 근거로 사용한다.
  out         범위 밖 — RoBERTa 분류 뒤 검색·LLM 없이 종료한다. 가데이터의 clarify 등 이전 응답은 보존한다.
실제 답변은 found/partial/not_found/refused를 구분한다. 연결·JSON·출처·숫자 검증 실패는 오류로 유지한다.
가데이터 모드는 같은 유형을 키워드 규칙과 고정 답으로 흉내 낸다(분류 모델 아님). 고정 답의 근거는 (규정 이름, 조 번호)로 팀 DB 청크에 잇는다.
"""
from __future__ import annotations

import copy
import json
import re

from .. import knowledge, llm, question_classifier, regstore
from . import runtime as rt
from . import grounded_answer
from .demo import D

REG_HINT = re.compile(r'(규정|조항|교육비|지원금|여비|출장|근무\s*시간|근무\s*형태|교대|복무|휴가|휴직|복직|평정|보수|급여|월급|수당|성과급|승진|발령|전보|징계|상벌|퇴직|정년|복지 제도|채용|수습|교육\s*인정|교육훈련|유연근무|재택|원격근무|겸직|부업|외부\s*강의|연차|병가|직제|전결|국외근무)')
HR_TERMS = re.compile(r'(승진|발령|성과급|상여)')
OUT_HINT = re.compile(r'(주식|주가|코스피|코스닥|나스닥|비트코인|코인 시세|가상화폐|환율|날씨|기온|미세먼지|비가 와|눈이 와|야구|축구|농구|배구|골프 대회|경기 결과|스코어|월드컵|올림픽|로또|연예인|아이돌|드라마|예능)')
FOLLOW = re.compile(r'^(그럼|그러면|그건|그거|그게|그때|그런데|근데|이건|이거|거기|그 ?다음|또|그리고|혹시|아까|방금)')
CONTEXT_REF = re.compile(
    r'(?<!\w)(?:그|이|해당|위)\s+(?:규정|내용|기준|조건|경우|절차|방법|사업|제도|메뉴|설명|답변|부분)|'
    r'^(?:그|해당)\s+(?:회사|기관|시설|식당|셔틀|주차장)|'
    r'(?:앞서|앞에서|이전(?:에)?|방금|아까)\s*(?:설명|말|답|안내|알려|내용|질문)|'
    r'(?:내|제)\s*(?:상황|경우)에|'
    r'^(?:좀\s*)?더\s*(?:자세히|쉽게|구체적으로)')
ADDED_CONDITION = re.compile(r'도\s*(?:교육비\s*)?(?:지원|인정|적용|가능|신청|받을|받는)')
NAMED_RULE = re.compile(r'\w+(?:규정|규칙|세칙)')
NEW_TOPIC = re.compile(r'^(?:다른|새(?:로운)?)\s*(?:질문|주제)|^(?:주제|질문)\s*(?:를|을)?\s*바꿔')
DEMO_ANSWERS = (
    (r'교육비.*지원', 'regulation', '교육비 지원을 신청하기 전에 대상 과정과 승인 조건을 교육 담당 부서에 확인하는 예시예요.'),
    (r'통근\s*버스.*시간표', 'life', '시연 화면에서는 사내 포털의 ‘생활 → 통근버스’ 메뉴에서 시간표를 확인해요.'),
    (r'승진.*기준', 'regulation', '승진 기준을 알아볼 때 인사규정과 인사규정시행세칙을 함께 확인하는 예시예요.'),
    (r'근무\s*성적\s*평정.*언제', 'regulation', '근무성적평정의 기준일을 인사규정시행세칙에서 확인하는 예시예요.'),
    (r'수자원공사.*어떤 일', 'company', '수자원 관리와 수돗물 공급 업무를 회사 소개 자료에서 확인하는 예시예요.'),
    (r'회의실.*예약', 'life', '시연 화면에서는 사내 포털의 ‘업무 지원 → 회의실 예약’ 메뉴에서 빈 시간대를 확인해요.'),
)
GENERAL = [
    (r'(로드맵|계획).*(기간|바꾸|수정|늘리|줄이)|수정 요청', {'source': 'app', 'summary': '로드맵은 내 로드맵의 ‘수정 요청’에서 바꿀 수 있어요.', 'apply': '주당 시간·기간·예산·학습 방식·자격증·일정 제약·시작 단계·관점·활동 빼기·바꾸기·추가를 여러 개 고르거나 요청을 문장으로 적으면, 로드맵을 쓴 관점의 에이전트가 수정안을 먼저 보여 주고 확정해야 로드맵이 바뀌어요.', 'links': [['roadmap', '내 로드맵']]}),
    (r'(사후|점검 결과|보고서)', {'source': 'app', 'summary': '로드맵을 마무리하려면 점검·보고서에서 사후 점검을 시작하세요.', 'apply': '사전 점검과 같은 문항에 다시 답하면 진단 에이전트가 결과 보고서를 만들어 드려요.', 'links': [['checks', '점검·보고서']]}),
    (r'(rag|래그|검색\s*증강)', {'source': 'work', 'summary': 'RAG는 질문과 관련된 문서를 먼저 찾아서, 그 내용을 근거로 LLM이 답하게 하는 방식이에요.', 'apply': '문서를 잘게 나눠 임베딩으로 색인하고, 질문과 가까운 조각을 찾아 프롬프트에 함께 넣어요. 지금 로드맵의 ‘핵심 이해’ 단계에서 다뤄요.', 'more': ['더 알고 싶으면 학습 자료에서 ‘RAG’를 검색해 보세요.'], 'links': [['resources', '학습 자료']]}),
    (r'(임베딩|벡터)', {'source': 'work', 'summary': '임베딩은 문장을 숫자 벡터로 바꿔, 뜻이 비슷한 문장끼리 가까이 놓이게 하는 방법이에요.', 'apply': '벡터 DB에 문서 조각의 임베딩을 넣어 두면, 질문과 가까운 조각을 빠르게 찾을 수 있어요.'}),
    (r'(파이썬|python)', {'source': 'work', 'summary': 'Python은 짧은 입문 강좌로 기본 문법부터 익히는 게 빨라요.', 'apply': '학습 자료에서 ‘Python’을 검색하면 등록된 입문 강좌(예: MS Learn ‘첫 번째 Python 코드 작성’)를 볼 수 있어요.', 'links': [['resources', '학습 자료']]}),
]
AMBIG = [
    (r'점수', lambda q: not re.search(r'(평정|점검|자격|시험)', q), ['근무성적평정 점수는 어떻게 구성되나요?', '사전·사후 점검 결과는 어디서 보나요?']),
    (r'^(어디서|어떻게)\s*신청', lambda q: len(q) <= 14, ['교육 과정 신청은 어디서 하나요?', '휴가 신청은 어디서 하나요?', '통근버스 탑승 신청은 어디서 하나요?']),
]
TOPICS = [('travel', r'(여비|출장비 지급|출장 여비)'), ('hours', r'(근무\s*시간|수강|복무|근무\s*형태|교대|통상)'), ('support', r'(교육비|지원금|지원을 받)'),
          ('edu', r'(교육\s*인정|교육훈련|교육.*규정|규정.*교육)'), ('eval', r'(근무성적평정|평정).*(언제|시기|기준일|하나요|해요)|언제.*평정'),
          ('promo', r'승진.*(기준|요건|조건|어떻게|하려면|궁금|방법)')]

# 가데이터 고정 답 (일반직): 시연 질문마다 규정 원문을 읽고 그 조항에 적힌 내용만 썼다(4차 10/15 사용자 결정).
# basis: (규정 이름, 조 번호, 항) — 팀 DB 청크로 잇는다. annex: (규정, 별표, 경로에 들어갈 글자) — '{직급}'은 로그인한 직원 직급
CANNED_GEN = {
    'edu': {'level': 'ok', 'summary': '일반직 직원의 교육에 관한 세부사항은 「인재개발규정」이 정해요(「취업규칙」 제76조의2).',
            'apply': '교육은 자체교육과 위탁교육으로 나뉘고, 학습주체별로 인재개발담당부서 주관학습·부서자체학습·개인학습으로 구분돼요(「인재개발규정」 제3조). {이름} 님도 매년 기준학습시간 이상을 이수해야 하고, 개인학습도 학습시간에 포함돼요(제7조).',
            'more': ['직급별 연간 기준학습시간은 「인재개발규정」 별표 1에 있어요. 아래 근거에서 {직급} 행을 확인해 주세요.'],
            'basis': [('취업규칙', '제76조의2', ''), ('인재개발규정', '제3조', ''), ('인재개발규정', '제7조', '제1항'), ('인재개발규정', '제7조', '제2항')],
            'annex': ('인재개발규정', '별표 1', '일반직 및 운영직 {직급}'), 'missing_if_no_annex': ['「인재개발규정」 별표 1(직급별 연간 기준학습시간)']},
    'support': {'level': 'unclear', 'summary': '교육비를 어떤 기준으로 지원하는지는 등록된 조항에 적혀 있지 않아요. 국내 위탁교육 경비의 지급기준은 사장이 따로 정한다고만 되어 있어요.',
                'apply': '외부 교육기관에 맡기는 과정이면 위탁교육(「인재개발규정」 제17조)에 해당하는지 먼저 봐야 해요. 국내 위탁교육 경비 지급기준은 사장이 따로 정하고(제24조 ①), 교육 신청은 통합교육포털에서 해요(제9조). 그래서 계획의 예상 비용에서 지원금을 빼지 않았어요.',
                'more': ['담당 부서에 물어볼 질문: 온라인 무료·유료 과정도 위탁교육 경비 지원 대상인가요?'],
                'basis': [('인재개발규정', '제17조', ''), ('인재개발규정', '제24조', '제1항'), ('인재개발규정', '제9조', '')], 'missing': ['국내 위탁교육 경비 지급기준(사장이 따로 정함)']},
    'travel': {'level': 'ok', 'summary': '교육명령을 받은 교육에 가면 교육출장 명령을 받고, 「여비규정」으로 정한 출장여비를 받아요(「인재개발규정」 제11조 ③).',
               'apply': '편도 40킬로미터를 넘고 전체 80킬로미터를 넘는 다른 행정단위로 가면 운임·일비·식비는 정액, 숙박비는 실비로 받아요(「여비규정」 제8조 ①). 가까운 곳은 사장이 정하는 바에 따라 예산 범위에서 근거리출장비를 받을 수 있어요(「여비규정」 제13조의2). 지금 계획의 교육은 대부분 온라인이라 출장이 생기지 않을 수도 있어요.',
               'more': ['정액 금액은 「여비규정」 별표 1(국내여비 지급기준)에 있어요. 아래 근거 원문을 확인해 주세요.'],
               'basis': [('인재개발규정', '제11조', '제3항'), ('취업규칙', '제47조', ''), ('여비규정', '제8조', ''), ('여비규정', '제13조의2', '')],
               'annex': ('여비규정', '별표 1', ''), 'missing_if_no_annex': ['「여비규정」 별표 1(국내여비 지급표)']},
    'hours': {'level': 'unclear', 'summary': '근무시간 중에 하는 개인 학습을 근무로 인정하는지는 등록된 조항에 적혀 있지 않아요. 확인되는 부분까지 알려드릴게요.',
              'apply': '{이름} 님이 통상근무자라면 기본 근무시간은 09시부터 18시까지이고, 1주 근로시간은 휴게시간을 빼고 40시간이에요(「취업규칙」 제12조). 교육명령을 받은 교육은 교육출장 명령을 받아 참석해요(「인재개발규정」 제11조 ③). 학습시간의 세부 인정기준과 절차는 인재개발담당부서의 장이 따로 정해요(제7조 ②).',
              'more': ['근무시간 중 온라인 강의를 들어도 되는지', '개인학습 시간이 기준학습시간으로 인정되는 방법'],
              'basis': [('취업규칙', '제12조', ''), ('인재개발규정', '제11조', '제3항'), ('인재개발규정', '제7조', '제2항')], 'missing': ['학습시간 인정기준(인재개발담당부서의 장이 따로 정함)']},
    'eval': {'level': 'ok', 'summary': '정기평정은 매년 10월 말일을 기준으로 그 전 1년간을 평정해요(「인사규정시행세칙」 제27조).',
             'apply': '수시평정은 정기평정 이후 사장이 특히 필요하다고 인정할 때 해요. 평정 전에 {이름} 님은 인사시스템의 본인기술서와 업무실적평가표를 입력하고, 1차·2차 평정자가 인사시스템으로 평정해요(제29조의3).',
             'more': ['평정기준일에 휴직·파견·교육 중이라 본인기술서를 쓰지 못할 것 같으면 미리 본사 인사담당부서장에게 낼 수 있어요(제29조의3 제2호).'],
             'basis': [('인사규정시행세칙', '제27조', ''), ('인사규정시행세칙', '제29조의3', '')], 'missing': []},
    'promo': {'level': 'ok', 'summary': '승진은 상위직 결원 범위 안에서 차하위 직급자 중에서 근무성적, 경력, 그 밖의 능력의 실증에 따라요(「인사규정」 제22조).',
              'apply': '직급마다 승진소요최저연수가 있어요(예: 5급에서 4급 2년, 4급에서 3급 3년 · 제23조). 3급 이상은 승진후보자 명부에 오른 사람 중에서, 4급과 6급 이하는 승진소요최저연수가 지난 사람 중에서 임용하고, 세부 방법은 세칙으로 정해요(제24조). {이름} 님이 승진할 수 있는지는 예측하지 않아요.',
              'more': ['종합근무평정과 승진후보자 명부 작성 기준은 「인사규정시행세칙」 제5장에 있어요.'],
              'basis': [('인사규정', '제22조', ''), ('인사규정', '제23조', ''), ('인사규정', '제24조', '')], 'missing': []},
}
FOLLOW_GEN = [
    ('support', r'(신청|언제|기한|마감|어디)', {'level': 'unclear', 'summary': '교육 신청은 통합교육포털에서 해요(「인재개발규정」 제9조). 신청 마감일은 조항에 정해져 있지 않아요.',
                                             'apply': '선정된 교육대상자는 교육명령이 확정되기 전까지 통합교육포털에서 취소신청을 할 수 있고(제10조 ②), 교육명령은 교육 시작 1주 전까지 내려요(제11조 ①). 과정마다 신청 기간은 통합교육포털 공지에서 확인해 주세요.',
                                             'more': [], 'basis': [('인재개발규정', '제9조', ''), ('인재개발규정', '제10조', '제2항'), ('인재개발규정', '제11조', '제1항')], 'missing': []}),
    ('travel', r'(금액|얼마|일비|식비|숙박)', {'level': 'unclear', 'summary': '출장 여비 정액은 「여비규정」 별표 1(국내여비 지급기준)에 있어요. 금액은 직급·구분마다 달라 아래 근거 원문에서 확인해 주세요.',
                                          'apply': '조항에는 운임·일비·식비는 별표 1에 따른 정액, 숙박비는 별표 1의 범위에서 실비로 준다고 적혀 있어요(「여비규정」 제8조 ①).',
                                          'more': ['가데이터 모드라 표의 금액을 읽어 드리지 않아요. 여비 담당 부서에 확인할 수도 있어요.'], 'basis': [('여비규정', '제8조', '')],
                                          'annex': ('여비규정', '별표 1', ''), 'missing_if_no_annex': ['「여비규정」 별표 1(국내여비 지급표)']}),
]
# 가데이터 고정 답 (실무직): 「실무직 관리규정」만 근거. 실무직 묶음에는 일반직 규정을 넣지 않았다(10/15 사용자 결정)
CANNED_PRAC = {
    'edu': {'level': 'ok', 'summary': '실무직의 교육훈련은 「인재개발규정」을 따라요.', 'apply': '{이름} 님은 실무직이라 이 조항이 적용돼요. 교육 신청·승인, 비용 지원, 교육 인정 조건은 「인재개발규정」에서 확인해야 해요.',
            'more': ['「인재개발규정」은 실무직 규정 묶음에 들어 있지 않아 세부 조건은 답할 수 없어요.'], 'basis': [('실무직 관리규정', '제3조', ''), ('실무직 관리규정', '제35조', '')], 'missing': ['인재개발규정']},
    'support': {'level': 'missing', 'summary': '교육비 지원 여부는 지금 등록된 자료로는 확인할 수 없어요.', 'apply': '교육훈련은 「인재개발규정」을 따르는데(제35조), 실무직 규정 묶음에는 그 규정이 없어요. 그래서 계획의 예상 비용에서 지원금을 빼지 않았어요.',
                'more': ['담당 부서에 물어볼 질문: 온라인 과정도 교육비 지원 대상인가요?', '사전 승인이 필요하다면 언제까지 신청해야 하나요?'], 'basis': [('실무직 관리규정', '제35조', '')], 'missing': ['인재개발규정']},
    'travel': {'level': 'missing', 'summary': '교육 출장 여비는 「여비규정」을 따르는데, 실무직 규정 묶음에 없어 지급 여부를 확인할 수 없어요.', 'apply': '실무직의 업무 수행에 따른 여비는 「여비규정」을 준용해요(제34조). 지금 계획의 교육은 대부분 온라인이라 출장이 생기지 않을 수도 있어요.',
               'more': ['교육 참석 출장이 ‘업무 수행’에 해당하는지', '「여비규정」의 지급 기준과 사전 승인 절차'], 'basis': [('실무직 관리규정', '제34조', '')], 'missing': ['여비규정']},
    'hours': {'level': 'unclear', 'summary': '근무시간 중 수강이 되는지는 확정할 수 없어요. 확인되는 부분까지 알려드릴게요.', 'apply': '{이름} 님이 통상근무자라면 휴게시간을 빼고 1주 40시간·1일 8시간 근무해요(제4조). 복무는 「취업규칙」, 교육훈련은 「인재개발규정」을 따르는데 두 규정은 실무직 규정 묶음에 없어요.',
              'more': ['근무시간 중 교육 참여에 승인이 필요한지', '교육 시간이 근무시간으로 인정되는지'], 'basis': [('실무직 관리규정', '제4조', ''), ('실무직 관리규정', '제15조', ''), ('실무직 관리규정', '제35조', '')], 'missing': ['취업규칙', '인재개발규정']},
}


ART_MAX = 2000
NUM_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(점|년|개월|일|시간|분|퍼센트|%|만원|원|킬로미터|km|급|회|명)')


def ans(**o) -> dict:
    base = {'kind': 'general', 'level': 'general', 'source': '', 'summary': '', 'basis': [], 'intranet': [],
            'question': '', 'options': [], 'retrieved': []}
    base.update(o)
    return base


def intranet_hits(q: str) -> list[str]:
    t = (q or '').lower()
    hits = [(x, sum(1 for k in x['keys'] if k.lower() in t)) for x in D['intranet']]
    return [x['id'] for x, n in sorted((h for h in hits if h[1]), key=lambda h: -h[1])[:2]]


def grade_short(g: str | None) -> str:
    return re.sub(r'^일반직\s*', '', g or '')


def _resolve(c: dict, me: dict) -> dict:
    """고정 답의 (규정, 조) 근거를 팀 DB 청크 id로 바꾸고, 이름·직급을 채운다. 별표가 등록돼 있으면 별표 행도 근거로"""
    o = copy.deepcopy(c)
    ids = []
    for reg, label, para in o.pop('basis', []):
        ids += regstore.find_article(reg, label, para)
    annex = o.pop('annex', None)
    miss_no = o.pop('missing_if_no_annex', [])
    if annex:
        aid = regstore.find_annex(annex[0], annex[1], annex[2].replace('{직급}', grade_short(me.get('grade'))))
        if aid:
            ids.append(aid)
        else:
            o['missing'] = list(o.get('missing') or []) + miss_no
            o['more'] = [m for m in o.get('more', []) if '별표' not in m]
    o.setdefault('missing', [])
    o['basis'] = rt.uniq(ids)
    s = json.dumps(o, ensure_ascii=False).replace('{이름}', me.get('name') or '사용자').replace('{직급}', grade_short(me.get('grade')) or '내 직급')
    return json.loads(s)


def _canned(me: dict) -> dict:
    return CANNED_GEN if me.get('empGroup') == '일반직' else CANNED_PRAC


def _topic(q: str, me: dict) -> str | None:
    t = next((k for k, pat in TOPICS if re.search(pat, q)), None)
    return t if t and t in _canned(me) else None


def miss_label(m: str) -> str:
    return m if re.search(r'[「」]', m) or not re.search(r'(규정|규칙|세칙|운영기준)$', m) else f'「{m}」'


def nums_ok(txt: str, basis: list, extra=None) -> bool:
    src = re.sub(r'(\d),(?=\d{3})', r'\1', re.sub(r'\s+', '', ' '.join((regstore.article(i) or {}).get('text', '') for i in basis)))
    ok = set(extra or [])
    txt = re.sub(r'(\d),(?=\d{3})', r'\1', str(txt))
    for m in NUM_RE.finditer(txt):
        n = m.group(1)
        if n in ok:
            continue
        if not re.search(r'(?<![\d.])' + re.escape(n) + r'(?![\d])', src):
            return False
    return True


def ctx_nums(context: dict) -> set[str]:
    """사용자 상황(직급·진행 중인 로드맵의 주당 시간·비용 등)에 있는 숫자는 조항 원문에 없어도 답에 써도 된다(예: '5급인 문시우 님은')"""
    return set(re.findall(r'\d+(?:\.\d+)?', re.sub(r'(\d),(?=\d{3})', r'\1', json.dumps(context or {}, ensure_ascii=False))))


def hr_stated(q: str, ids: list) -> bool:
    m = HR_TERMS.search(q)
    return not m or any(m.group(1) in ((regstore.article(i) or {}).get('title', '') + (regstore.article(i) or {}).get('text', '')) for i in ids)


def _is_follow(q: str, prev: dict | None, me: dict) -> bool:
    if not prev or OUT_HINT.search(q) or NEW_TOPIC.search(q):
        return False
    # 앞 내용을 명시적으로 가리키면 길이·가데이터 주제 키워드와 관계없이 이어 받는다.
    if CONTEXT_REF.search(q):
        return True
    if NAMED_RULE.search(q):
        return False
    if ADDED_CONDITION.search(q):
        return True
    return bool(prev) and not _topic(q, me) and not intranet_hits(q) and (
        bool(FOLLOW.search(q)) or (len(q) <= 16 and not re.search(r'규칙|세칙', q) and not REG_HINT.search(q) and not any(re.search(p, q, re.I) for p, _ in GENERAL)
                                    and not any(re.search(p, q) and ok(q) for p, ok, _ in AMBIG)))


def _mock_general(q: str) -> dict:
    hit = next((v for p, v in GENERAL if re.search(p, q, re.I)), None)
    base = hit or {'source': 'work', 'summary': '가데이터 모드라 이 질문에는 준비된 답이 없어요.',
                   'apply': '좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 업무·학습 질문에도 답해요. 업무·사내 생활과 관계없는 질문에는 답하지 않아요.'}
    return ans(**copy.deepcopy(base))


def _mock_documents(inp: dict) -> dict:
    question = inp['question']
    if OUT_HINT.search(question):
        return ans(kind='out', level='out')
    for pattern, topic, summary in DEMO_ANSWERS:
        if re.search(pattern, question):
            return ans(kind='regulation' if topic == 'regulation' else 'general', topic=topic,
                       source={'regulation': '', 'company': 'work', 'life': 'intranet'}[topic], summary=summary)
    return ans(summary='시연용 가데이터에 준비된 답변이 없어요. 화면의 추천 질문을 선택해 주세요.')


def _prev_reg(prev: dict | None) -> str | None:
    """앞 답변의 첫 근거 조항이 속한 규정(이어 묻기에서 규정 이름 없이 '그럼 제3조는?'이라고 물을 때)"""
    b = ((prev or {}).get('a') or {}).get('basis') or []
    a = regstore.article(b[0]) if b else None
    return a['reg'] if a else None


def _clean(t: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', t or '')).strip()


def _ref_answer(ref: dict, me: dict) -> dict:
    """직접 물은 조·항·호를 원문 그대로 보여 주는 답(가데이터 모드)"""
    reg = ref['reg']
    if not ref['ids']:
        return ans(kind='regulation', level='none', summary=f"{ref['note']}. 등록된 규정에 없는 조항이라 답하지 않아요.")
    a0 = regstore.article(ref['ids'][0])
    title = f"({a0['title']})" if a0.get('title') else ''
    body = _clean(ref['focus'] or a0['text'])
    head = f"「{reg['name']}」 {ref['label']}{title}{ref['where'][len(ref['label']):]}"
    os_ = ' 국외근무 직원 대상 규정이라 국내에서 근무하면 적용되지 않아요.' if reg.get('overseas') else ''
    return ans(kind='regulation', level='ok', summary=f"{head}: {body[:320]}{'…' if len(body) > 320 else ''}",
               apply=' '.join(x for x in (ref['note'], f"{me.get('name') or '사용자'} 님의 규정 묶음({me.get('empGroup') or ''})에 등록된 원문이에요.{os_}",
                                          '아래 ‘규정 근거 보기’에서 조항 원문 전체를 볼 수 있어요.') if x),
               more=['내 상황에 그대로 적용되는지는 담당 부서에 확인해 주세요.'], basis=ref['ids'], retrieved=ref['ids'])


def _mock(inp: dict) -> dict:
    q, me, hist = inp['question'], inp['me'], inp.get('history') or []
    group = me.get('empGroup')
    hits = regstore.keyword_search(q, 3, group)
    prev = hist[-1] if hist else None
    if OUT_HINT.search(q):
        return ans(kind='out', level='out')
    ref = regstore.explicit_ref(q, group, _prev_reg(prev))
    if ref:
        return _ref_answer(ref, me)
    if _is_follow(q, prev, me):
        return _mock_follow(q, prev, me)
    t = _topic(q, me)
    if t:
        return dict(ans(kind='regulation', topic=t, **_resolve(_canned(me)[t], me)), retrieved=[h['id'] for h in hits])
    if HR_TERMS.search(q) and not hr_stated(q, [h['id'] for h in hits]):
        return ans(kind='regulation', level='none')
    intra = intranet_hits(q)
    if intra:
        return ans(source='intranet', intranet=intra)
    amb = next((x for x in AMBIG if re.search(x[0], q) and x[1](q)), None)
    if amb:
        return ans(kind='clarify', level='clarify', question='어떤 내용을 물어보신 건지 골라 주세요.', options=amb[2])
    if not REG_HINT.search(q):
        return _mock_general(q)
    if not hits:
        return ans(kind='regulation', level='none')
    a = regstore.article(hits[0]['id'])
    reg = regstore.reg_public(a['reg']) or {}
    have = {r['name'] for r in ((regstore.set_for(group) or {}).get('regs') or [])}
    refs = [n for n in rt.uniq(x[1:-1] for x in re.findall(r'「[^」]+」', a['text'])) if not re.search(r'법$|법률|시행령$', n) and n not in have]
    name = f"「{reg.get('name', '')}」 {a['no']}({a['title']})" if a['title'] else f"「{reg.get('name', '')}」 {a['no']}"
    if '준용' in a['text'] and refs:
        return ans(kind='regulation', level='missing', summary=f'{name}는 「{refs[0]}」을 따르도록 정하고 있어요. 그 원문이 아직 등록되지 않아 자세한 기준은 확인할 수 없어요.',
                   apply=f"{group or ''} 대상으로 등록된 규정에서 찾은 조항이에요.", more=[f'「{refs[0]}」 원문 확인'], basis=[h['id'] for h in hits], missing=refs, retrieved=[h['id'] for h in hits])
    first = re.sub(r'\s+', ' ', re.sub(r'<[^>]*>|\[[^\]]*\]', '', a['text'])).strip()
    m = re.match(r'^.*?다\.', first)
    os_ = ' 국외근무 직원 대상 규정이라 국내에서 근무하면 적용되지 않아요.' if reg.get('overseas') else ''
    return ans(kind='regulation', level='ok', summary=f"{name}: {(m.group(0) if m else first)[:170]}",
               apply=f"{me.get('name') or '사용자'} 님은 {group or ''}이라 「{reg.get('name', '')}」 조항으로 답했어요.{os_} 자세한 내용은 아래 ‘규정 근거 보기’에서 원문을 확인하세요.",
               more=['내 상황에 그대로 적용되는지는 담당 부서에 확인해 주세요.'], basis=[h['id'] for h in hits], retrieved=[h['id'] for h in hits])


def _mock_follow(q: str, prev: dict, me: dict) -> dict:
    a, head = prev['a'], f"앞에서 물으신 ‘{prev['q']}’에 이어서 답할게요."
    if a.get('kind') != 'regulation' or a.get('level') in ('none', 'scope'):
        return ans(source='work', summary=head, apply='가데이터 모드라 이어지는 질문에 쓸 답은 준비돼 있지 않아요. 좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 앞 대화를 이어 받아 답해요.')
    tp = a.get('topic') or _topic(prev['q'], me)
    f = next((x for x in FOLLOW_GEN if x[0] == tp and re.search(x[1], q)), None) if me.get('empGroup') == '일반직' else None
    if f:
        o = ans(kind='regulation', topic=tp, **_resolve(f[2], me))
        o['summary'] = f"{head} {o['summary']}"
        return o
    arts = [regstore.article(i) for i in a.get('basis') or [] if regstore.article(i)]
    nos = '·'.join(f"{x['no']}({x['title']})" if x['title'] else x['no'] for x in arts)
    if a.get('missing'):
        ms = '·'.join(miss_label(m) for m in a['missing'])
        return ans(kind='regulation', level='missing', summary=f'{head} ‘{q}’도 지금 등록된 자료로는 확인할 수 없어요.',
                   apply=f"앞 답변의 근거{f'({nos})' if nos else ''}는 {ms}에 기준을 넘기고 있는데, 그 내용이 등록되지 않았어요. 원문에 없는 기한·절차를 짐작해서 답하지 않을게요.",
                   more=[f'담당 부서에 물어볼 질문: {q}'], basis=list(a.get('basis') or []), missing=list(a['missing']))
    return ans(kind='regulation', level='none')


def _art_in(a: dict) -> dict:
    reg = regstore.reg_public(a['reg']) or {}
    return {'id': a['id'], 'regulation': reg.get('name', ''), 'no': a['no'], 'title': a['title'], 'chapter': a['chapter'],
            'appliesTo': a.get('group') or reg.get('group', ''),
            'text': a['text'][:ART_MAX] + (' …(뒤 생략)' if len(a['text']) > ART_MAX else '')}


def _history_summary(turn: dict) -> str:
    answer = turn['a']
    summary = answer.get('summary') or ''
    if not summary and answer.get('intranet'):
        # 생활 안내는 모델 원문 대신 검증된 메뉴만 표시하므로 그 안내를 요약으로 쓴다.
        summary = ' / '.join(f"{item['menu']}: {item['covers']}" for item in D['intranet']
                             if item['id'] in answer['intranet'])
    return summary


def _follow_history(q: str, hist: list, me: dict) -> list:
    if not hist or not _is_follow(q, hist[-1], me):
        return []
    start = len(hist) - 1
    while start > 0 and _is_follow(hist[start]['q'], hist[start - 1], me):
        start -= 1
    return hist[start:]


def _hist_msgs(h: list) -> list:
    """이미 생성된 답변 요약으로 주제·최근 맥락을 압축한다. 출처 ID·옛 JSON은 넘기지 않는다."""
    if not h:
        return []
    # 질문은 처음 주제·최근 맥락만, 답변은 이미 생성한 요약을 중복 없이 누적한다.
    # 중간 답변의 적용 조건을 버리거나 요약용 모델을 추가 호출하지 않는다.
    questions = list(dict.fromkeys(turn['q'] for turn in [h[0], *h[-2:]]))
    summaries = list(dict.fromkeys(filter(None, (_history_summary(turn) for turn in h))))
    return [{'role': 'user', 'content': '\n'.join(questions)},
            {'role': 'assistant', 'content': '\n'.join(summaries)}]


def _context_query(q: str, history: list, *, classify: bool = False) -> str:
    if not history:
        return q
    messages = _hist_msgs(history)
    if classify:
        # 분류기는 128토큰 입력이므로 처음 주제와 최근 답변 요약을 짧게 전달한다.
        context = f"{history[0]['q'][:60]} {_history_summary(history[-1])[:60]}"
    else:
        context = ' '.join(message['content'] for message in messages)
    # 입력 길이 제한에서 현재 질문이 과거 요약 뒤로 잘리지 않게 먼저 둔다.
    return f'현재 질문: {q}\n앞 대화 요약: {context}'


def _api(ctx: rt.Ctx, inp: dict) -> dict:
    q, hist = inp['question'], inp.get('history') or []
    history = _follow_history(q, hist, inp['me'])
    inp['_history'] = history
    classification = question_classifier.classify(_context_query(q, history, classify=True))
    inp['_classification'] = dict(classification, usedHistory=bool(history))
    if classification['label'] == '범위 밖':
        return ans(kind='out', level='out')
    return _api_answer(ctx, inp, classification['label'])


def _no_evidence(topic: str, retrieved: list | None = None, note: str = '') -> dict:
    title = {'regulation': '규정', 'company': '회사 정보', 'life': '사내 생활'}[topic]
    return ans(kind='regulation' if topic == 'regulation' else 'general',
               level='none' if topic == 'regulation' else 'general',
               source={'regulation': '', 'company': 'work', 'life': 'intranet'}[topic],
               topic=topic, evidenceStatus='not_found',
               summary=note or f'이번에 검색한 {title} 자료에서 질문에 답할 근거를 찾지 못했어요. 질문을 구체적으로 적거나 담당 부서에 확인해 주세요.',
               retrieved=retrieved or [], **({'knowledgeSources': []} if topic in ('company', 'life') else {}))


def _refused(topic: str) -> dict:
    return ans(kind='regulation' if topic == 'regulation' else 'general', level='refused',
               source={'regulation': '', 'company': 'work', 'life': 'intranet'}[topic],
               topic=topic, evidenceStatus='refused',
               summary='개인정보·비공개 정보 공개나 권한 우회처럼 제공하면 안 되는 요청에는 답변하지 않아요.',
               **({'knowledgeSources': []} if topic in ('company', 'life') else {}))


def _empty_evidence_answer(ctx: rt.Ctx, topic: str, inp: dict, note: str = '', retrieved: list | None = None,
                           history: list | None = None) -> dict:
    # 검색 자료가 없어도 제공 금지 요청과 단순 근거 부족은 구분해야 한다.
    if history is None:
        history = _hist_msgs(inp.get('_history') or [])
    result = grounded_answer.generate(ctx, topic, inp['question'], [], inp['context'],
                                     history=history)
    return _refused(topic) if result['status'] == 'refused' else _no_evidence(topic, retrieved, note)


def _life_answer(ctx: rt.Ctx, inp: dict) -> dict:
    return _knowledge_answer(ctx, inp, 'life')


def _company_answer(ctx: rt.Ctx, inp: dict) -> dict:
    return _knowledge_answer(ctx, inp, 'company')


def _knowledge_answer(ctx: rt.Ctx, inp: dict, topic: str) -> dict:
    q = inp['question']
    history = inp.get('_history') or []
    query = _context_query(q, history)
    title = '회사 정보' if topic == 'company' else '사내 생활'
    category = knowledge.CATEGORY if topic == 'company' else knowledge.LIFE_CATEGORY
    hits = knowledge.search_company(query) if topic == 'company' else knowledge.search_life(query)
    if not hits:
        return _empty_evidence_answer(ctx, topic, inp)
    sources = []
    for hit in hits:
        if hit['category'] != category or (topic == 'company' and hit['is_virtual']):
            raise llm.LlmError(f'답변 형식 오류: {title} 검색 자료의 범주가 맞지 않아요')
        meta = hit['metadata'] or {}
        sources.append({'id': hit['chunk_id'], 'document': hit['document_title'],
                        'location': meta.get('location'), 'asOf': meta.get('as_of'),
                        'sourceLimits': meta.get('source_limits'), 'isVirtual': hit['is_virtual'],
                        'text': hit['chunk_text'][:3000], 'textTruncated': len(hit['chunk_text']) > 3000})
    result = grounded_answer.generate(ctx, topic, q, sources, inp['context'],
                                     history=_hist_msgs(history))
    if result['status'] == 'refused':
        return _refused(topic)
    if result['status'] == 'not_found':
        return _no_evidence(topic)
    by_id = {hit['chunk_id']: hit for hit in hits}
    selected = [by_id[value] for value in result['sourceIds']]
    summary = result['summary']
    passed_sources = {source['id']: source for source in sources}
    cited_text = ' '.join(' '.join(str(passed_sources[hit['chunk_id']].get(key) or '') for key in ('text', 'document', 'asOf')) for hit in selected)
    allowed_numbers = set(re.findall(r'\d+(?:\.\d+)?', re.sub(r'(\d),(?=\d{3})', r'\1', cited_text)))
    if any(match.group(1) not in allowed_numbers for match in NUM_RE.finditer(re.sub(r'(\d),(?=\d{3})', r'\1', summary))):
        raise llm.LlmError(f'답변 형식 오류: {title} 답변의 숫자가 인용 자료에 없어요')
    provenance, citations = [], []
    for hit in selected:
        meta = hit['metadata'] or {}
        citation = ' · '.join(str(value) for value in (hit['document_title'], meta.get('location'), meta.get('as_of')) if value)
        citations.append(citation)
        provenance.append({'chunkId': hit['chunk_id'], 'documentId': hit['document_id'],
                           'documentTitle': hit['document_title'], 'sourceUrl': meta.get('source_url'),
                           'location': meta.get('location'), 'asOf': meta.get('as_of'),
                           'sourceLimits': meta.get('source_limits'), 'isVirtual': hit['is_virtual'],
                           'textSha256': hit['chunk_text_sha256'], 'sourceFileSha256': meta.get('source_file_sha256'),
                            'textTruncated': len(hit['chunk_text']) > 3000,
                            'excerpt': passed_sources[hit['chunk_id']]['text']})
    return ans(source='work' if topic == 'company' else 'intranet', topic=topic, evidenceStatus=result['status'],
               summary=summary + '\n\n출처: ' + ' / '.join(rt.uniq(citations)), knowledgeSources=provenance)


def _api_answer(ctx: rt.Ctx, inp: dict, label: str) -> dict:
    if label == '수자원공사 정보':
        return _company_answer(ctx, inp)
    if label == '사내 생활안내':
        return _life_answer(ctx, inp)
    if label != '사내 규정':
        raise llm.LlmError('답변 형식 오류: 알 수 없는 질문 분류 결과예요')
    q, me, hist = inp['question'], inp['me'], inp.get('history') or []
    group = me.get('empGroup')
    follow_history = inp.get('_history') or []
    scope = {'all_groups': True} if inp.get('documents_only') else {}
    ref = regstore.explicit_ref(q, group, **scope)
    # 규정 이름이 없는 조항 질문은 일반 이어 묻기 판별과 별도로 직전 규정을 참조한다.
    if ref is None and hist and regstore.REF_ART.search(q):
        default_reg = _prev_reg(hist[-1])
        if default_reg:
            ref = regstore.explicit_ref(q, group, default_reg, **scope)
            if ref is not None and not follow_history:
                follow_history = [hist[-1]]
    prev = follow_history[-1] if follow_history else None
    history = _hist_msgs(follow_history)
    alone = regstore.search(q, 4, group, ctx.mode, **scope)
    joined = regstore.search(_context_query(q, follow_history), 4, group, ctx.mode, **scope) if prev else []
    mix = []
    for index in range(max(len(alone), len(joined))):
        if index < len(joined):
            mix.append(joined[index]['id'])
        if index < len(alone):
            mix.append(alone[index]['id'])
    ref_ids = (ref or {}).get('ids') or []
    previous_ids = list((prev or {}).get('a', {}).get('basis') or [])
    ids = [value for value in rt.uniq(ref_ids + previous_ids + mix) if regstore.article(value)][:max(7, len(ref_ids))]
    if ref and not ref_ids:
        note = f"{ref['note']}. 규정명과 조 번호를 확인하거나 담당 부서에 문의해 주세요."
        return _empty_evidence_answer(ctx, 'regulation', inp, note, ids, history=history)
    if not ids:
        return _empty_evidence_answer(ctx, 'regulation', inp, history=history)
    requested = {'where': ref['where'], 'focus': ref['focus'], 'note': ref['note']} if ref else None
    result = grounded_answer.generate(ctx, 'regulation', q, [_art_in(regstore.article(value)) for value in ids],
                                     inp['context'], history=history, requested=requested)
    if result['status'] == 'refused':
        return _refused('regulation')
    if result['status'] == 'not_found':
        return _no_evidence('regulation', ids)
    basis, summary = result['sourceIds'], result['summary']
    if not hr_stated(q, basis):
        return _no_evidence('regulation', ids)
    if not nums_ok(summary, basis, ctx_nums(inp['context'])):
        raise llm.LlmError('답변 형식 오류: 규정 답변의 숫자가 인용 조항에 없어요')
    return ans(kind='regulation', topic='regulation', evidenceStatus=result['status'],
               level='ok' if result['status'] == 'found' else 'unclear', summary=summary,
               basis=basis, retrieved=ids)


def scope_answer(a: dict, me: dict) -> dict:
    grp = me.get('empGroup') or '직원 구분이 확인되지 않은 직원'
    has = '·'.join(g for g in regstore.groups())
    return ans(kind='regulation', level='scope', topic='regulation', evidenceStatus='not_found', summary=f"등록된 규정은 {has} 대상이라, {grp}인 {me.get('name') or '사용자'} 님에게 적용되는 규정이 아직 없어요.",
               apply=f'{grp}의 인사·복무·교육훈련 기준은 {grp} 대상 규정을 따르는데, 아직 GrowPath에 등록되지 않아 답할 수 없어요. 인사 담당 부서(인재경영실 · 가상)에 확인해 주세요.',
               ref=list(a.get('basis') or [])[:3], retrieved=a.get('retrieved') or [])


def answer(ctx: rt.Ctx, question: str, history: list, context: dict, sim: str | None = None,
           *, documents_only: bool = False) -> dict:
    """history: 앞 대화 중 답을 받은 질문·답 [{q, a}] (대화 전체 · 10/14 사용자 결정)"""
    me = {} if documents_only else ctx.me
    context = {} if documents_only else context
    inp = {'question': question, 'history': history or [], 'context': context, 'me': me,
           'documents_only': documents_only}
    task = f"사내 생활 질문 분류·답변{f' (앞 대화 {len(history)}턴 포함)' if history else ''}"
    mock = _mock_documents if documents_only else _mock
    a = rt.run(ctx, '규정 에이전트', task, inp, mock, lambda i: _api(ctx, i), role='regulation', sim=sim, mock_delay=0.38,
               log_input={'question': question, 'context': context, 'history': history or []})
    if inp.get('_classification'):
        ctx.meta['classification'] = inp['_classification']
    if documents_only:
        return a
    return scope_answer(a, me) if a['kind'] == 'regulation' and a.get('evidenceStatus') != 'refused' and not regstore.set_for(me.get('empGroup')) else a


def reg_context(me: dict, plans: list, drafting: dict | None) -> dict:
    """규정 에이전트가 볼 사용자 상황: 로그인한 직원, 진행 중인 로드맵 전부와 작성 중인 안"""
    s = regstore.set_for(me.get('empGroup'))
    return {'name': me.get('name'), 'employeeGroup': me.get('empGroup'), 'grade': me.get('grade'), 'department': me.get('dept'), 'job': me.get('job'),
            'registeredRegulation': {'appliesTo': s['group'], 'regulations': [r['name'] for r in s['regs'] if not r['overseas']],
                                     'overseasOnly': [r['name'] for r in s['regs'] if r['overseas']]} if s else {'appliesTo': regstore.groups(), 'regulations': []},
            'regulationApplies': bool(s), 'plans': plans, 'drafting': drafting}


# ── 안별 지원 조건 확인 ──
SUP_QUERY = {'일반직': '위탁교육 교육경비 지급 교육신청 학습시간 인정 개인학습 근무시간 교육출장', '실무직': '교육훈련 교육비 지원 근무시간 학습 인정 복무'}
SUP_SYS = """너는 GrowPath '규정 에이전트'다. 로드맵 후보(plans)마다 교육비 지원과 근무시간 중 학습 인정을 받을 수 있는지, 입력의 articles(사용자에게 적용되는 등록 규정에서 찾은 조항 · regulation은 규정 이름)만 근거로 확인한다.
- articles에 쓰인 내용만 근거로 쓴다. 지원 여부·금액·한도·절차·승인 주체를 조항에 없는데 추측하거나 지어내지 않는다.
- 일반 상식, 다른 기관 사례, 인터넷·웹 검색 정보로 답하지 않는다.
- 조항이 등록되지 않은 규정·별표나 '사장이(담당 부서의 장이) 따로 정한다'는 기준으로 넘기면 그 기준은 모른다. level은 unclear 또는 missing으로 하고 missing에 그 규정·별표·기준 이름을 넣는다.
- plans의 unknownCostResources는 수강료·도서 가격·응시료를 아직 모르는 자료다. 비용이 든다고 단정하지 말고 확인이 필요하다고 쓴다.
- level: ok(조항으로 확인됨) / unclear(일부만 확인) / missing(관련 자료 미확보). ok나 unclear면 basis에 근거 id를 넣는다.
- summary: 그 안의 유료 자료·비용·자격을 짚어, 무엇을 확인해야 하는지 1~2문장(해요체). 규정 이름과 조 번호를 함께 쓰고, 확인되지 않은 것을 확정처럼 쓰지 않는다.
JSON 형식: {"plans":[{"pid":"A1","level":"unclear","summary":"...","basis":["근거 id"],"missing":["국내 위탁교육 경비 지급기준"]}]}"""


def won(n) -> str:
    return f'{int(n):,}원'


def _mock_support_one(x: dict, me: dict) -> dict:
    paid, unknown = x.get('paidResources') or [], x.get('unknownCostResources') or []
    total = sum(r.get('costWon') or 0 for r in paid)
    if me.get('empGroup') == '일반직':
        ids17, ids24, ids7 = regstore.find_article('인재개발규정', '제17조'), regstore.find_article('인재개발규정', '제24조', '제1항'), regstore.find_article('인재개발규정', '제7조', '제2항')
        if paid or unknown:
            what = f'유료 자료 {len(paid)}개({won(total)})' if paid else f'비용을 확인해야 하는 자료 {len(unknown)}개(수강료·도서 가격)'
            head = (f'이 안의 {what}가 외부 교육기관 과정이면 위탁교육(「인재개발규정」 제17조)에 해당하는지 먼저 확인해야 해요. '
                    '국내 위탁교육 경비의 지급기준은 사장이 따로 정한다고만 되어 있어(제24조) 지원 여부와 금액은 확인할 수 없어요.')
            return {'level': 'unclear', 'summary': head + (' 자격 응시료 지원은 등록된 조항에서 찾지 못했어요.' if x.get('certification') else ''),
                    'basis': ids17 + ids24, 'missing': ['국내 위탁교육 경비 지급기준(사장이 따로 정함)']}
        head = '이 안은 비용이 0원으로 확인된 자료만 써서 교육비가 들지 않아요. 개인학습도 학습시간에 포함되지만(「인재개발규정」 제7조 ②), 세부 인정기준은 인재개발담당부서의 장이 따로 정해 근무시간 중 학습 인정은 확인이 필요해요.'
        return {'level': 'unclear', 'summary': head + (' 자격 응시료 지원은 등록된 조항에서 찾지 못했어요.' if x.get('certification') else ''),
                'basis': ids7, 'missing': ['학습시간 인정기준(인재개발담당부서의 장이 따로 정함)']}
    a35, a15 = regstore.find_article('실무직 관리규정', '제35조'), regstore.find_article('실무직 관리규정', '제15조')
    head = (f"이 안의 {'유료 자료 %d개(%s)' % (len(paid), won(total)) if paid else '비용을 확인해야 하는 자료 %d개' % len(unknown)}가 교육비 지원 대상인지는 「인재개발규정」을 따르는데(제35조), 실무직 기준은 확인할 수 없어요."
            if paid or unknown else '이 안은 비용이 0원으로 확인된 자료만 써서 교육비가 들지 않아요. 근무시간 중 학습 인정은 「취업규칙」(제15조)·「인재개발규정」(제35조)을 따르는데 실무직 기준은 확인할 수 없어요.')
    return {'level': 'missing', 'summary': head + (' 자격 응시료 지원도 같은 이유로 확인이 필요해요.' if x.get('certification') else ''),
            'basis': a35 if (paid or unknown) else a15 + a35, 'missing': ['인재개발규정'] if (paid or unknown) else ['취업규칙', '인재개발규정']}


def support_scope(me: dict) -> dict:
    grp = me.get('empGroup') or '직원 구분이 확인되지 않은 직원'
    return {'level': 'scope', 'summary': f"등록된 규정은 {'·'.join(regstore.groups())} 대상이라, {grp}인 {me.get('name') or '사용자'} 님의 교육비 지원·근무시간 중 학습 인정은 확인할 수 없어요. {grp} 대상 규정이 등록되면 확인할 수 있어요.",
            'basis': [], 'missing': []}


def support(ctx: rt.Ctx, plans: list[dict], context: dict, sim: str | None = None) -> dict:
    """plans: [{pid, name, weeks, weeklyHours, totalCostWon, paidResources[], unknownCostResources[], certification, onlineOnly}] → {pid: 결과}"""
    me = ctx.me
    if not regstore.set_for(me.get('empGroup')):
        return {x['pid']: support_scope(me) for x in plans}

    def api(_):
        hits = regstore.search(SUP_QUERY.get(me.get('empGroup'), SUP_QUERY['일반직']), 6, me.get('empGroup'), ctx.mode)
        arts = [regstore.article(h['id']) for h in hits if regstore.article(h['id'])]
        ids = [a['id'] for a in arts]
        r = rt.llm_json(ctx, SUP_SYS, {'plans': plans, 'user': context, 'articles': [_art_in(a) for a in arts]}, role='regulation')
        out = {}
        for x in r.get('plans') if isinstance(r.get('plans'), list) else []:
            pid = str(x.get('pid') or '')
            if not any(p['pid'] == pid for p in plans):
                continue
            basis = [str(i) for i in x.get('basis') or [] if str(i) in ids]
            level = x.get('level') if x.get('level') in ('ok', 'unclear', 'missing') else 'missing'
            summary = str(x.get('summary') or '').strip()
            # 근거 없이 확인됐다고 하면 믿지 않는다: 문장은 버리고 '관련 자료 미확보'로 낮춘다
            if level != 'missing' and not basis:
                level, summary = 'missing', '등록된 규정에서 이 안의 지원 조건을 뒷받침하는 조항을 찾지 못해 확인할 수 없어요. 담당 부서에 확인해 주세요.'
            elif basis and not nums_ok(summary, basis, re.findall(r'\d+', json.dumps(next((p for p in plans if p['pid'] == pid), {}), ensure_ascii=False))):
                level, summary = 'unclear', '관련 조항은 찾았지만, 확인 문장의 숫자가 조항 원문과 맞지 않아 그대로 보여 드리지 않아요. 근거 조항 원문을 확인해 주세요.'
            if summary:
                out[pid] = {'level': level, 'summary': summary, 'basis': basis, 'missing': [str(m) for m in x.get('missing') or [] if str(m)][:3]}
        if not out:
            raise llm.LlmError('지원 조건 확인 결과가 비어 있어요')
        return out
    return rt.run(ctx, '규정 에이전트', '안별 지원 조건 확인', {'plans': plans}, lambda i: {x['pid']: _mock_support_one(x, me) for x in i['plans']}, api,
                  role='regulation', sim=sim, mock_delay=0.8)
