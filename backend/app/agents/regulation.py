"""규정 에이전트 · 사내 생활 도우미(API-09) / 교육비 규정 안내 (4차 gp-ai.js · 4차 묶음 5·7).

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

from .. import db, hybrid_search, knowledge, llm, question_classifier, regstore
from ..errors import AgentError
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
FOLLOW_HISTORY_LIMIT = 5
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
    b = ((prev or {}).get('a') or {}).get('basis') or []
    a = regstore.article(b[0]) if b else None
    return a['reg'] if a else None


def _clean(t: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', t or '')).strip()


def _ref_answer(ref: dict, me: dict) -> dict:
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
    hits = regstore.keyword_search(q, 3, group, all_groups=False)
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


def _history_answer(turn: dict) -> str:
    answer = turn['a']
    summary = answer.get('summary') or ''
    if not summary and answer.get('intranet'):
        # 이전 메뉴형 안내는 본문 대신 화면에 표시한 메뉴 정보를 전달한다.
        summary = ' / '.join(f"{item['menu']}: {item['covers']}" for item in D['intranet']
                             if item['id'] in answer['intranet'])
    return summary


def _follow_history(q: str, hist: list, me: dict) -> list:
    hist = hist[-FOLLOW_HISTORY_LIMIT:]
    if not hist or not _is_follow(q, hist[-1], me):
        return []
    start = len(hist) - 1
    while start > 0 and _is_follow(hist[start]['q'], hist[start - 1], me):
        start -= 1
    return hist[start:]


def _hist_msgs(history: list) -> list:
    """질문과 화면에 표시한 답변을 턴별로 전달한다."""
    messages = []
    for turn in history:
        messages.extend(({'role': 'user', 'content': turn['q']},
                         {'role': 'assistant', 'content': _history_answer(turn)}))
    return messages


def _context_query(q: str, history: list, *, classify: bool = False) -> str:
    if not history:
        return q
    # 128토큰 분류기는 현재 질문에 이어 가장 최근 턴부터 읽는다.
    turns = reversed(history) if classify else history
    context = '\n'.join(f"질문: {turn['q']}\n답변: {_history_answer(turn)}" for turn in turns)
    return f'현재 질문: {q}\n앞 대화:\n{context}'


# ==============================================================================
# ⭐ [1단계 ~ 5단계 규정 질의응답 핵심 파이프라인]
# ==============================================================================

def classify_question_roberta(question: str, history: list | None = None, me: dict | None = None,
                             emp_group: str | None = None) -> dict:
    """⭐ [1단계 - RoBERTa로 질문 분류]
    1. 사용자 정보(me 또는 emp_group)에서 사용자의 기본 직군을 가져온다. (없으면 '일반직' 자동 보장)
    2. 질문(question) 안에 특정 직군 명칭이 언급되어 있는지 확인한다.
       - 질문에 직군이 있으면: 질문에 적힌 직군을 사용 (예: "실무직 연차 휴가는?" -> '실무직')
       - 질문에 직군이 없으면: 사용자의 기본 직군을 사용 (예: "연차 휴가는?" -> 사용자 직군 '일반직')
    3. 직군과 대화 맥락을 결합하여 RoBERTa로 질문 유형을 1차 분류한다.
    """
    history = history or []
    group_list = ['일반직', '실무직', '운영직']
    user_group = emp_group or (me.get('empGroup') if isinstance(me, dict) else me) or '일반직'
    detected_group = next((g for g in group_list if g in question), None)
    effective_group = detected_group if detected_group else user_group

    me_obj = {'empGroup': effective_group}
    follow_history = _follow_history(question, history, me_obj)
    context_query = _context_query(question, follow_history, classify=True)
    result = question_classifier.classify(context_query)

    return {
        'label': result['label'],
        'confidence': result.get('confidence'),
        'model': result.get('model'),
        'usedHistory': bool(follow_history),
        'follow_history': follow_history,
        'group': effective_group,
        'detectedFromQuestion': bool(detected_group),
    }


def classify_label_with_llm(ctx: rt.Ctx, question: str, history: list | None = None) -> str | None:
    """RoBERTa 예측 정확도가 80% 미만일 때 LLM을 호출하여 라벨을 다시 분류한다."""
    if ctx.mode not in ('ollama', 'openai'):
        return None
    system = """너는 사내 질문의 유형을 정확하게 분류하는 AI 분류기다.
        사용자의 질문과 이전 대화를 읽고, 다음 4가지 라벨 중 가장 적절한 하나만 JSON으로 응답하라:
        1. '사내 규정': 취업규칙, 인사, 복무, 휴가, 출장, 교육비 지원, 승진, 징계, 퇴직 등 회사 사규·규정 관련 질문
        2. '사내 생활안내': 구내식당 메뉴 및 운영시간, 통근버스 노선 및 시간표, 사내 복지시설, 회의실 예약 등 사내 생활편의 관련 질문
        3. '수자원공사 정보': K-water 회사 소개, 설립 목적, 주요 사업(수자원, 수도, 댐 등), 기관 정보 관련 질문
        4. '범위 밖': 사내 업무 및 생활과 무관한 일반 질문 (주식, 날씨, 연예인, 스포츠, 잡담 등)

        반드시 아래 JSON 형식으로만 응답하라:
        {"label": "사내 규정" | "사내 생활안내" | "수자원공사 정보" | "범위 밖"}"""
    payload = {'question': question}
    try:
        res = rt.llm_json(ctx, system, payload, role='regulation', history=_hist_msgs(history or []),
                          temperature=0 if ctx.mode == 'ollama' else None)
        label = res.get('label')
        if label in ('사내 규정', '사내 생활안내', '수자원공사 정보', '범위 밖'):
            return label
    except Exception:
        pass
    return None


def verify_or_reclassify_label_with_llm(ctx: rt.Ctx, question: str, label: str,
                                       confidence: float | None = None,
                                       history: list | None = None) -> str:
    """⭐ [2단계 - RoBERTa 예측정확도 80% 이하 시 LLM 2차 재분류]
    1. RoBERTa 확신도가 80%(0.80) 이상이면 1단계 분류 라벨을 그대로 확정한다.
    2. 확신도가 80% 미만이거나 애매한 경우, LLM이 질문을 다시 읽고 2차 재분류를 수행한다.
    """
    if confidence is not None and confidence >= 0.8:
        return label

    if ctx.mode in ('ollama', 'openai'):
        llm_label = classify_label_with_llm(ctx, question, history)
        if llm_label:
            return llm_label

    return label


def retrieve_regulation_slots(ctx: rt.Ctx, inp: dict) -> list[str]:
    """⭐ [3단계 - RAG를 통해서 근거 가져오기 (조항 및 부모 슬롯 확보)]
    BGE-M3(벡터) + BM25(키워드) 하이브리드 검색으로 관련 조항을 찾고,
    부모 조항(parent_context) 최대 2슬롯을 우선 확보하여 7개 조항 ID(ids)를 선별한다. (이슈 #138 해결)
    """
    q, me, hist = inp['question'], inp['me'], inp.get('history') or []
    group = me.get('empGroup') or '일반직'
    follow_history = inp.get('_history') or []
    documents_only = inp.get('documents_only')

    prev = follow_history[-1] if follow_history else None

    # 1) BGE-M3 + BM25 하이브리드 검색 실행
    alone = regstore.search(q, 5, group, ctx.mode)
    joined = regstore.search(_context_query(q, follow_history), 5, group, ctx.mode) if prev else []
    mix = []
    for index in range(max(len(alone), len(joined))):
        if index < len(joined):
            mix.append(joined[index]['id'])
        if index < len(alone):
            mix.append(alone[index]['id'])

    # 이전 대화의 근거 조항들
    previous_ids = list((prev or {}).get('a', {}).get('basis') or [])
    if documents_only:
        previous_ids = [aid for aid in previous_ids if (source := regstore.article(aid)) and source.get('group') == group]

    # 중복 제거된 검색 후보 조항 리스트
    core_candidates = [v for v in rt.uniq(previous_ids + mix) if regstore.article(v)]
    if not core_candidates:
        return []

    # ⭐ [이슈 #138 핵심 해결: 7개 슬롯 예산 최적 배분]
    # (1) 핵심 검색 조항을 먼저 최대 4개까지만 담아서 부모 조항을 위한 자리(최소 3슬롯)를 예약!
    selected_ids = list(core_candidates[:4])

    # (2) 부모 문맥(parent_context) 최대 2개 슬롯 우선 확보! (조건, 예외, 상위 항 보존)
    if documents_only and ctx.mode in ('ollama', 'openai') and hybrid_search.enabled():
        parent_ids = regstore.parent_context(selected_ids, group, q, limit=2)
        selected_ids = rt.uniq(selected_ids + parent_ids)

    # (3) 참조 조항(referenced_paragraphs) 최대 2개 슬롯 보충
    if documents_only:
        ref_para_ids = regstore.referenced_paragraphs(selected_ids, limit=min(2, 7 - len(selected_ids)))
        selected_ids = rt.uniq(selected_ids + ref_para_ids)

    # (4) 7개 슬롯 중 아직 자리가 남았다면 나머지 검색 후보(mix)로 알뜰하게 채움!
    for cand in core_candidates:
        if len(selected_ids) >= 7:
            break
        if cand not in selected_ids:
            selected_ids.append(cand)

    ids = selected_ids[:7]
    return ids


def generate_regulation_summary(ctx: rt.Ctx, inp: dict, ids: list[str]) -> dict:
    """⭐ [4단계 - 근거를 통해서 LLM이 요약하기]
    3단계(RAG)에서 선별된 7개 조항 원문을 바탕으로 LLM에게 요약 답변 생성을 요청한다.
    (비공개 개인정보·타인 인사정보나 제공 금지 요청은 LLM이 status='refused'로 판단하여 거절)
    """
    q = inp['question']
    follow_history = inp.get('_history') or []
    history = _hist_msgs(follow_history)
    sources = [_art_in(regstore.article(value)) for value in ids]

    # LLM에게 조항 원문들을 주입하여 요약 답변 생성
    result = grounded_answer.generate(ctx, 'regulation', q, sources, inp['context'], history=history)
    return result


def format_and_output_response(ctx: rt.Ctx, inp: dict, ids: list[str], result: dict) -> dict:
    """⭐ [5단계 - 요약 결과 검증 및 최종 화면 출력]
    LLM의 결과 상태(refused, not_found)를 분기하고, 숫자 환각 방지 검증을 거쳐 최종 화면 응답(ans)을 출력한다.
    """
    q = inp['question']

    # 1) 제공 금지(refused) 또는 근거 없음(not_found) 상태 처리
    if result['status'] == 'refused':
        return _refused('regulation')
    if result['status'] == 'not_found':
        return _no_evidence('regulation', ids)

    basis, summary = result['sourceIds'], result['summary']
    if not hr_stated(q, basis):
        return _no_evidence('regulation', ids)

    # 2) 숫자 환각 방지 검증 (원문에 없는 숫자 사용 차단)
    if not nums_ok(summary, basis, ctx_nums(inp['context'])):
        raise llm.LlmError('답변 형식 오류: 규정 답변의 숫자가 인용 조항에 없어요')

    # 3) 최종 출력 객체 생성 및 반환
    final_response = ans(kind='regulation', topic='regulation', evidenceStatus=result['status'],
                         level='ok' if result['status'] == 'found' else 'unclear', summary=summary,
                         basis=basis, retrieved=ids)
    return final_response


# ==============================================================================
# ⭐ [통합 파이프라인 조율 함수] (1단계 -> 2단계 -> 3단계 -> 4단계 -> 5단계 순차 실행)
# ==============================================================================

def answer_with_pipeline(ctx: rt.Ctx, inp: dict) -> dict:
    """⭐ [통합 파이프라인] 1단계부터 5단계를 위에서 아래로 순서대로 실행한다."""
    q, hist = inp['question'], inp.get('history') or []
    me = inp.get('me') or {}

    # [1단계] RoBERTa 질문 1차 분류
    classified = classify_question_roberta(q, hist, me=me)
    label = classified['label']
    confidence = classified.get('confidence')
    follow_history = classified['follow_history']

    inp['_history'] = follow_history
    inp['_classification'] = {k: v for k, v in classified.items() if k not in ('follow_history', 'group', 'detectedFromQuestion')}
    if classified.get('group'):
        inp['me'] = dict(me, empGroup=classified['group'])

    # [2단계] RoBERTa 예측정확도가 80% 이하면 LLM이 다시 분류
    effective_label = verify_or_reclassify_label_with_llm(ctx, q, label, confidence, follow_history)

    # 도메인별 분기
    if effective_label == '범위 밖':
        return ans(kind='out', level='out')
    elif effective_label == '수자원공사 정보':
        return _company_answer(ctx, inp)
    elif effective_label == '사내 생활안내':
        return _life_answer(ctx, inp)

    # ── [사내 규정 처리 3 -> 4 -> 5단계] ──
    # [3단계] RAG를 통해서 근거를 가져온다.
    ids = retrieve_regulation_slots(ctx, inp)
    if not ids:
        return _no_evidence('regulation')

    # [4단계] 근거를 통해서 LLM이 요약을 한다.
    summary_result = generate_regulation_summary(ctx, inp, ids)

    # [5단계] 요약하는 거 검증하고 최종 출력한다.
    return format_and_output_response(ctx, inp, ids, summary_result)


# ==============================================================================
# ⭐ [_api 실행 진입점] (answer_with_pipeline 바로 아래에 위치)
# ==============================================================================

def _api(ctx: rt.Ctx, inp: dict) -> dict:
    """에이전트 런타임(rt.run)이 호출하는 진입점: 통합 파이프라인을 실행한다."""
    return answer_with_pipeline(ctx, inp)


def answer_with_rag_and_llm(ctx: rt.Ctx, inp: dict, label: str, confidence: float | None = None) -> dict:
    return answer_with_pipeline(ctx, inp)


def generate_regulation_output(ctx: rt.Ctx, inp: dict, ids: list[str]) -> dict:
    summary_result = generate_regulation_summary(ctx, inp, ids)
    return format_and_output_response(ctx, inp, ids, summary_result)


def retrieve_and_answer(ctx: rt.Ctx, inp: dict, label: str, confidence: float | None = None) -> dict:
    return answer_with_pipeline(ctx, inp)


def _api_answer(ctx: rt.Ctx, inp: dict, label: str, confidence: float | None = None) -> dict:
    return answer_with_pipeline(ctx, inp)


def classify_with_context(question: str, history: list, me: dict) -> dict:
    return classify_question_roberta(question, history, me)


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
    provenance = []
    for hit in selected:
        meta = hit['metadata'] or {}
        provenance.append({'chunkId': hit['chunk_id'], 'documentId': hit['document_id'],
                           'documentTitle': hit['document_title'], 'sourceUrl': meta.get('source_url'),
                           'location': meta.get('location'), 'asOf': meta.get('as_of'),
                           'sourceLimits': meta.get('source_limits'), 'isVirtual': hit['is_virtual'],
                           'textSha256': hit['chunk_text_sha256'], 'sourceFileSha256': meta.get('source_file_sha256'),
                            'textTruncated': len(hit['chunk_text']) > 3000,
                            'excerpt': passed_sources[hit['chunk_id']]['text']})
    return ans(source='work' if topic == 'company' else 'intranet', topic=topic, evidenceStatus=result['status'],
               summary=summary, knowledgeSources=provenance)


def _regulation_answer(ctx: rt.Ctx, inp: dict) -> dict:
    ids = retrieve_regulation_slots(ctx, inp)
    return format_and_output_response(ctx, inp, ids, generate_regulation_summary(ctx, inp, ids)) if ids else _no_evidence('regulation')


def scope_answer(a: dict, me: dict) -> dict:
    grp = me.get('empGroup') or '직원 구분이 확인되지 않은 직원'
    has = '·'.join(g for g in regstore.groups())
    return ans(kind='regulation', level='scope', topic='regulation', evidenceStatus='not_found', summary=f"등록된 규정은 {has} 대상이라, {grp}인 {me.get('name') or '사용자'} 님에게 적용되는 규정이 아직 없어요.",
               apply=f'{grp}의 인사·복무·교육훈련 기준은 {grp} 대상 규정을 따르는데, 아직 GrowPath에 등록되지 않아 답할 수 없어요. 인사 담당 부서(인재경영실 · 가상)에 확인해 주세요.',
               ref=list(a.get('basis') or [])[:3], retrieved=a.get('retrieved') or [])


def prepare_assistant_input(question: str, history: list | None, me: dict, context: dict | None = None,
                            *, documents_only: bool = False) -> dict:
    """사용자 질문, 앞 대화 내용, 사용자 정보를 검증하고 묶는다."""
    return {
        'question': question,
        'history': history or [],
        'context': context or {},
        'me': me or {},
        'documents_only': documents_only,
    }


def answer(ctx: rt.Ctx, question: str, history: list, context: dict, sim: str | None = None,
           *, documents_only: bool = False) -> dict:
    """history는 답을 받은 질문·답 [{q, a}]이다. 이어 묻기에는 최대 5턴을 사용한다."""
    me = ctx.me if ctx.me else {}
    inp = prepare_assistant_input(question, history, me, context, documents_only=documents_only)
    task = f"사내 생활 질문 분류·답변{f' (앞 대화 {len(history)}턴 포함)' if history else ''}"
    mock = _mock_documents if documents_only else _mock
    a = rt.run(ctx, '규정 에이전트', task, inp, mock, lambda i: _api(ctx, i), role='regulation', sim=sim, mock_delay=0.38,
               log_input={'question': question, 'context': context, 'history': history or []})
    if inp.get('_classification'):
        ctx.meta['classification'] = inp['_classification']
    if documents_only:
        return a
    return scope_answer(a, me) if a['kind'] == 'regulation' and a.get('evidenceStatus') != 'refused' and not regstore.set_for(me.get('empGroup')) else a


def education_guide(t: db.Tx, group: str | None) -> dict:
    """국내 위탁교육에 관한 현행 원문만 반환한다. 직원별 지급액이나 승인 여부는 판정하지 않는다."""
    reg = t.one("""SELECT r.name, v.regulation_version_id, v.version_label
        FROM regulations.regulations r
        JOIN app_ext.regulation_meta m ON m.regulation_id = r.regulation_id
        JOIN regulations.regulation_versions v ON v.regulation_id = r.regulation_id
        WHERE m.short_key = 'dev' AND m.search_enabled AND m.employee_group = :g
          AND v.availability_status = 'available'
        ORDER BY v.effective_from DESC NULLS LAST, v.version_label DESC LIMIT 1""", g=group)
    if reg:
        row = t.one(regstore.CHUNK_SQL + """
            WHERE c.regulation_version_id = :version AND c.search_status = 'active'
              AND p.node_type = 'article' AND p.label = '제24조'
              AND n.node_type = 'paragraph' AND n.label = '제1항'
            ORDER BY c.rag_chunk_id LIMIT 1""", version=reg['regulation_version_id'])
        if row:
            article = regstore.art_of(row, {'short_key': 'dev', 'employee_group': group, 'overseas_only': False})
            if article['text'].strip():
                return {'basis': {'name': reg['name'], 'article': article['no'], 'text': article['text'],
                                  'page': article['page'], 'version': reg['version_label'], 'chunkId': article['id']}}
    return {'basis': None}
