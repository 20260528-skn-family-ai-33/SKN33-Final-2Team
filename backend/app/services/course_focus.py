"""명시된 학습 주제의 동의어와 차시의 실습을 연결한다. 태그·제공처는 점수에 넣지 않는다."""
from functools import lru_cache
import re
import unicodedata

from app import catalog_candidates, course_levels
from app.english_patterns import english_token

MIN_COURSE_CANDIDATES = 3

# Django 과정의 API 실습은 '구현'이라는 단어 없이도 구체적인 구성 요소와 작업으로 기술된다.
_drf_api = r'django\s+rest\s+framework|\bdrf\b|\b\w*apiview\b|\b\w*viewset\b|\b\w*serializer\b|\bmultipartparser\b|\bapiclient\b'
_api_work = r'선언|검증|구성|구현|작성|저장|반환|거절|테스트|전송|제한|처리'
_drf_component = re.compile(_drf_api, re.I | re.ASCII)
_drf_operation = re.compile(_api_work, re.I)


def drf_practice(unit):
    return bool(_drf_component.search(unit) and _drf_operation.search(unit))


# 스킬 이름만으로 활성화하지 않는다. 같은 태그라도 사용자가 고른 학습 대상에만 적용한다.
# (사용하는 스킬, 어떤 목표에서 적용할지, 단원에서 가르치는 주제, 그 주제의 구체적인 작업)
_topics = (
    ('웹 프레임워크|RESTful', r'(?=.*(?:django|장고))(?=.*(?:rest|drf))|\bdrf\b',
     r'django|장고|\bdrf\b', rf'(?=.*(?:{_drf_api}))(?=.*(?:{_api_work}))'),
    ('IAM', r'최소\s*권한|서비스\s*계정|역할|rbac|iam', r'\b(?:iam|rbac)\b|역할\s*기반|관리\s*ID|관리형\s*ID|서비스\s*(?:계정|주체)|역할\s*할당', r'역할.{0,9}(?:할당|설정|기반|액세스|위임)|(?:권한|액세스).{0,8}(?:구성|부여|범위|제어|정책|검토)|최소\s*권한|role assignment|permission'),
    ('IAM', r'역할|최소\s*권한|서비스\s*계정|rbac', r'역할|rbac|최소\s*권한|api\s*권한|권한\s*범위', r'할당|위임|권한.{0,5}구성|리소스.{0,6}액세스|액세스\s*제어|역할.{0,8}설정'),
    # 도구를 지정한 목표는 그 도구의 실제 차시로 확인한다. 일반 ETL·캐싱 목표에는 적용하지 않는다.
    ('ETL|파이프라인', r'\bairflow\b|에어플로', r'\bairflow\b|에어플로', r'\bdag\b|태스크|작업|의존성|스케줄|재시도|백필|멱등|수집|변환|적재|실행'),
    ('Redis|캐싱|캐시|트래픽', r'\bredis\b|레디스', r'\bredis\b|레디스', r'\bttl\b|캐시|캐싱|만료|무효화|조회|부하|연결|지연|버전|정합성'),
    ('IAM|네트워크 보안', r'방화벽|보안\s*그룹', r'방화벽|firewall|보안\s*그룹', r'포트|인바운드|아웃바운드|차단|허용|규칙'),
    ('컴퓨터 비전', r'객체\s*(?:탐지|검출)|경계\s*상자|yolo', r'객체\s*(?:탐지|검출)|물체\s*(?:탐지|검출)|object detection|yolo\w*', r'탐지|검출|상자|iou|map\b|nms|라벨|bounding'),
    ('컴퓨터 비전', r'세그멘테이션|의미론적\s*분할|영상\s*분할', r'세그멘테이션|영상\s*분할|segmentation|u-net', r'마스크|픽셀|분할|mask|dice'),
    ('알고리즘|자료구조', r'최단\s*(?:거리|경로)|다익스트라|dijkstra', r'최단\s*(?:거리|경로)|다익스트라|벨만.{0,2}포드|플로이드.{0,3}워셜|dijkstra|shortest path', r'그래프|간선|가중|탐색|경로|우선순위|복잡도|graph|path'),
    ('알고리즘|자료구조', r'최소\s*(?:신장|스패닝)|크루스칼', r'최소\s*(?:신장|스패닝)|크루스칼|kruskal|spanning tree', r'간선|비용|정렬|분리\s*집합|union'),
    ('웨어하우스|OLAP', r'차원|팩트|스타\s*스키마|scd', r'차원|스타\s*스키마|팩트|사실\s*(?:표|테이블)|scd|dimensional', r'팩트|대리\s*키|차원\s*키|이력|시점|차원\s*(?:표|테이블)|사실\s*(?:표|테이블)|dimension|fact\s*table'),
    ('RDBMS', r'스키마|제약\s*조건|외래\s*키|정규화', r'관계형|스키마|데이터\s*모델|정규화|erd|관계\s*모델', r'제약|기본\s*키|외래\s*키|정규화|이력|무결성|참조|종속'),
    (r'\bSQL\b', r'실행\s*계획|인덱스|explain', r'실행\s*계획|인덱스|explain|index', r'스캔|조회|통계|성능|비용|복합|측정|분석|사용\s*여부|\bio\b|analyze|scan'),
    (r'\bSQL\b', r'조인|\bjoin\b', r'조인|\bjoin\b', r'외부|내부|행|집계|테이블|중복|결과|정합성|검증|실습|구현|inner|outer|group by'),
    ('NoSQL', r'샤딩|파티션|분할\s*키', r'파티션|샤딩|shard|분할\s*키', r'키|요청|분산|처리량|불균형|partition key'),
    ('머신러닝', r'불균형|재현율|정밀도', r'불균형|smote|재현율|recall|imbalanc', r'분류|정밀도|샘플링|임[곗계]\s*값|precision|미탐|오탐'),
    ('딥러닝', r'드롭아웃|dropout', r'드롭아웃|드랍아웃|dropout', r'과적합|학습|정규화|층|손실|검증|overfit'),
    ('RAG', r'langchain|랭체인|랑체인', r'langchain|랭체인|랑체인', r'문서|검색기|retriev|청크|질의|pdf|벡터\s*검색|검색\s*증강|\brag\b'),
    ('Docker', r'dockerfile|도커파일|이미지.{0,12}(?:빌드|만들)', r'dockerfile|도커파일|이미지.{0,10}(?:빌드|만들|작성)|docker build', r'이미지|레이어|실행|빌드|캐시|복사|build|layer'),
    ('CI/CD', r'github\s*actions|깃허브\s*액션', r'github\s*actions|깃허브\s*액션|github\s*워크플로', r'빌드|테스트|배포|워크플로|workflow|job'),
    ('클라우드 컴퓨팅', r'가용\s*영역|장애\s*조치|로드\s*밸런', r'가용\s*영역|가용성\s*영역|고가용성|부하\s*분산|로드\s*밸런|load balanc|multi[-\s]?az|availability\s*zone|장애\s*조치|failover', r'영역|배치|배포|구성|상태\s*점검|라우팅|장애|복구|failover'),
    ('거버넌스', r'계보|lineage', r'계보|lineage|변환\s*경로', r'필드|자산|원천|영향|계보|추적'),
    ('운영체제', r'잠금|경쟁|경합|교착', r'잠금|뮤텍스|교착|임계\s*구역|경쟁\s*상태|mutex|deadlock|(?:쓰레드|스레드|thread).{0,8}(?:동기화|lock)', r'공유|작업자|스레드|재현|대기|동기화|처리량|lock'),
    ('보안|탐지', r'침입\s*탐지|탐지\s*규칙|공격\s*트래픽', r'침입\s*탐지|suricata|snort|\bids\b', r'규칙|경보|패킷|오탐|트래픽|분석'),
    ('MLOps', r'추론\s*API|모델.{0,8}(?:서빙|배포)|mlflow', r'mlflow|모델.{0,12}(?:배포|서빙|레지스트리)|model serving', r'버전|배포|엔드포인트|추론|로그|모니터링|rollback'),
    ('PyTorch|TensorFlow', r'전이\s*학습|미세\s*조정|사전학습', r'전이\s*학습|미세\s*조정|파인\s*튜닝|transfer learning|fine.tun|torchvision', r'학습|동결|백본|분류|헤드|가중치|train'),
    ('NLP|자연어', r'토큰화|토크나이저|서브워드|어휘집|tokeniz|wordpiece|\bbpe\b|토큰.{0,8}(?:분절|분할|나누|분리)', r'토큰화|토크나이저|서브워드|tokeniz|wordpiece|\bbpe\b', r'문장|분절|문자|길이|토큰|어휘'),
    ('네트워크 프로토콜', r'패킷|핸드셰이크|재전송', r'\btcp\b|tcpdump|wireshark|와이어샤크', r'캡처|패킷|재전송|연결|흐름|handshake'),
    ('Kubernetes', r'롤링|롤백|롤아웃|deployment', r'쿠버네티스|kubernetes|\bk8s\b|\baks\b|디플로이먼트|deployment|rollout', r'롤링|롤아웃|롤백|워크로드.{0,10}배포|리소스\s*배포|이미지\s*배포|애플리케이션.{0,12}배포|서비스.{0,12}배포|배포\s*매니페스트|deploy'),
    ('POSIX', r'프로세스\s*간\s*통신|\bipc\b', r'\b(?:posix|ipc)\b|프로세스\s*간\s*통신', r'파이프|공유\s*메모리|큐|세마포어|소켓|pipe|fifo|shm'),
    ('마이크로서비스', r'재시도|대체\s*응답|회로\s*차단', r'마이크로서비스|microservice|\bmsa\b|서킷|회로\s*차단', r'재시도|대체\s*응답|회로\s*차단|서킷|fallback|retry'),
    ('FastAPI|웹 프레임워크', r'fastapi|패스트api', r'fastapi|패스트api', r'라우터|요청|의존성|응답|엔드포인트|pydantic|실습|rest\s*api.{0,12}(?:구현|개발|실습)'),
    ('FastAPI|웹 프레임워크', r'django|장고', r'django|장고', r'뷰|라우팅|모델|요청|템플릿|orm|view|rest\s*api.{0,12}(?:구현|개발|실습)'),
    (r'\bSQL\b', r'조인|join', r'조인|\bjoins?\b', r'집계|group by|서브쿼리|외부\s*조인|내부\s*조인|outer join|inner join'),
    (r'\bSQL\b', r'실행\s*계획|인덱스', r'쿼리\s*저장소|explain|실행\s*계획|인덱스', r'성능\s*평가|실제.{0,8}(?:시간|io)|스캔|analyze|커버링|복합\s*인덱스'),
    ('RDBMS', r'관계형|정규화|제약\s*조건', r'스키마|릴레이션|관계\s*모델|정규화|er\s*모델', r'제약\s*조건|기본\s*키|외래\s*키|이상\s*현상|정규형|함수.{0,2}종속'),
    ('EDA|탐색적', r'결측|이상치', r'결측|이상치|missing value|outlier', r'대체|제거|처리|정제|탐지|분포|보간'),
    ('머신러닝', r'불균형', r'불균형|소수\s*(?:클래스|범주)|smote|imbalanc', r'임[계곗]값|재현율|정밀도|가중치|샘플링|recall'),
    ('리눅스|Bash', r'로그', r'bash|리눅스|linux|쉘|셸|awk|grep', r'로그|접근\s*기록|log file'),
    ('컴퓨터 구조|메모리 관리', r'페이지|페이징|폴트|가상\s*메모리', r'가상\s*(?:메모리|기억)|페이징|mmap|페이지\s*(?:폴트|교체|부재)', r'페이지|주소\s*변환|참조열|fault|교체|지역성'),
    ('RESTful', r'요청.{0,6}검증|오류\s*응답|API\s*계약', r'\brest(?:ful)?\b|웹\s*api|fastapi|http\s*api', r'요청.{0,8}(?:검증|유효성)|상태\s*코드|오류\s*응답|요청\s*모델|엔드포인트|멱등'),
    ('마이크로서비스', r'실패|장애|재시도', r'마이크로\s*서비스|클라우드\s*네이티브|microservice', r'복원력|회로\s*차단|서킷|재시도|fault injection|fallback'),
    ('웹 애플리케이션', r'취약점|접근\s*통제|우회', r'웹.{0,8}(?:취약점|해킹)|owasp|xss|sql\s*(?:인젝션|injection)', r'우회|방어|입력|검증|대응|접근.{0,3}통제'),
    ('클라우드 컴퓨팅', r'가용\s*영역|로드\s*밸런', r'가용\s*영역|고가용성|부하\s*분산|로드\s*밸런', r'(?:부하\s*분산|로드\s*밸런).{0,16}(?:구성|만들|구현)|front\s*door|application gateway|영역.{0,8}배치'),
    ('Docker', r'dockerfile|이미지.{0,10}(?:빌드|만들)', r'도커|docker|컨테이너', r'이미지.{0,10}(?:만들|작성|빌드)|dockerfile|docker build'),
    ('알고리즘|자료구조', r'가중|다익스트라|우선순위', r'다익스트라|dijkstra|우선순위\s*큐', r'그래프|간선|최단|가중|비용'),
    ('운영체제', r'잠금|공유\s*(?:상태|자원)|경쟁', r'스레드|쓰레드|프로세스|thread|공유\s*(?:자원|상태)', r'뮤텍스|동기화|잠금|상호\s*배제|임계\s*구역|reader.writer lock|mutex'),
    ('RESTful', r'요청|수정\s*api|오류\s*응답', r'웹\s*api|restful|rest\s*api', r'컨트롤러|엔드포인트|crud|요청\s*모델|http\s*상태|응답\s*처리|response handling'),
    ('Docker', r'dockerfile|도커파일', r'dockerfile|도커파일', r'레이어|layer|명령|이미지|\bcopy\b|\bfrom\b|캐시|컨텍스트'),
    ('멀티스레딩', r'잠금|경쟁|경합|동기화', r'스레드|쓰레드|threads?|pthread', r'잠금|동기화|경쟁|뮤텍스|\block\b|mutex|synchroniz'),
    ('멀티스레딩', r'뮤텍스|mutex', r'뮤텍스|mutex', r'동기화|임계\s*(?:구역|영역)|상호\s*배제|잠금|synchroniz|critical.section|mutual exclusion'),
    ('멀티스레딩', r'공유|잠금|경쟁', r'멀티\s*(?:스레드|쓰레드)|pthread|multithread', r'read.write lock|spin lock|뮤텍스|동기화|임계\s*구역'),
    ('RESTful', r'오류\s*응답|요청\s*검증', r'\brest(?:ful)?\b|jax.?rs|웹\s*api|fastapi', r'오류\s*응답|응답\s*처리|response handling|유효성|validation|상태\s*코드'),
    ('클라우드 컴퓨팅', r'가용\s*영역', r'가용\s*영역|다중\s*영역|다중\s*az|multi.az|availability zone', r'영역.{0,12}(?:분산|배치|중단|장애|분배)|부하\s*분산|로드\s*밸런|failover|장애\s*조치'),
)
TOPICS = tuple(tuple(re.compile(expr, re.I | re.ASCII) for expr in row) for row in _topics)

# STORAGE 안의 RAG와 한국어 조사가 붙은 독립 용어 'RAG를'을 구분한다.
_llm_subject = r'언어\s*모델|응답|답변|' + english_token('LLM|RAG|RAGAS')
_translation_metric = english_token('BLEU|ROUGE|BERTScore')
_grounding_metric = english_token('faithfulness|groundedness')

# 사전점검의 해당 스킬 과업에서 찾을 수 있는 근거. 한 차시가 직접 다루는 작업을 구분한다.
_tasks = (
    (r'NLP|자연어', r'(?:응답|답변).{0,24}(?:품질|근거성|거절|환각|정답|평가)|(?:LLM|언어\s*모델)(?:의|을|를)?\s*(?:품질|근거성|환각|평가)|(?:평가|측정).{0,12}(?:응답|답변)\s*품질',
     ((rf'{_llm_subject}|{_translation_metric}|{_grounding_metric}',
       '(?:' + _llm_subject + r').{0,14}(?:평가|판정)|(?:정답|의미).{0,8}(?:비교|일치)|'
       + english_token(r'LLM[ ._-]as[ ._-]a[ ._-]judge') + '|' + _translation_metric),
      (r'환각|근거|충실도|거절|무응답|인용\s*적중률|' + _grounding_metric + '|' + english_token('RAGAS'),
       _grounding_metric + r'|(?:환각|충실도|근거성|거절|무응답).{0,12}(?:측정|평가|판정|지표|검증|임곗값)|(?:평가\s*지표|측정|계산).{0,24}인용\s*적중률|인용\s*적중률.{0,12}(?:측정|계산)'))),
    (r'NLP|자연어', r'(?=.*(?:자연어|텍스트|문장|문서))(?=.*(?:분류기|분류\s*(?:방법|모델|실험)|(?:텍스트|문장|문서)\s*분류))',
     ((r'토큰|토크나이|형태소|서브워드|임베딩|word2vec|TF.IDF',
       r'토큰화|토크나이[저제]|형태소\s*분석|단어\s*임베딩|워드\s*임베딩|word2vec|TF.IDF'),
      (r'텍스트|문서|문장|자연어|감성|감정',
       r'(?:텍스트|문서|문장|감성|감정).{0,12}(?:분류|분석)|분류기.{0,10}(?:학습|평가)'))),
    (r'EDA|탐색적', r'(?=.*(?:예측|체크포인트|반복\s*측정|지연|latency))(?=.*(?:지표|구간|표본|집단|그룹|비교))',
     ((r'모델|예측|평가|성능', r'(?:모델|예측|성능|평가).{0,9}(?:성능\s*향상|평가\s*지표|성능\s*평가|평가\s*방법|평가와|평가하기|오차\s*분석)|분류\s*지표'),
      (r'그룹|구간|반복\s*측정|표본|분포|groupby|groupkfold', r'그룹별\s*(?:집계|비교|기준선)|구간별\s*(?:분포|비교|집계)|반복\s*측정|소표본|groupby|groupkfold'))),
    (r'ETL|파이프라인', r'(?=.*(?:측정값|평가\s*결과|요청.{0,4}응답|이벤트|로그))(?=.*(?:집계|적재|대사|데이터\s*흐름))',
     ((r'원천|마트|스테이징|데이터|레코드|파이프라인|적재|이벤트|로그',
       r'행\s*수.{0,14}(?:대조|검증|비교)|무결성\s*검사|중복\s*레코드|집계\s*SQL|일자별\s*대사|누락\s*검증|멱등|워터마크'),
      (r'이벤트|로그|측정값|메트릭|telemetry|스트리밍', r'(?:로그|이벤트|측정값|메트릭)\s*(?:데이터|레코드|스트림)?\s*(?:를|을|의|별)?\s*(?:수집|적재|집계|처리)|로그\s*스트리밍|스트리밍\s*데이터.{0,8}(?:처리|집계)|(?:적재|집계).{0,10}(?:접근 로그|이벤트 데이터)'))),
)
TASKS = tuple((re.compile(skill, re.I), re.compile(intent, re.I),
               tuple((re.compile(subject, re.I), re.compile(action, re.I)) for subject, action in facets))
              for skill, intent, facets in _tasks)


@lru_cache(maxsize=512)
def task_topics(name, application):
    application = ' '.join(application.split())
    return tuple(facet for skill, intent, facets in TASKS if skill.search(name) and intent.search(application)
                 for facet in facets)


@lru_cache(maxsize=512)
def requested(name, context):
    context = ' '.join(context.split())
    return tuple((subject, action) for skill, trigger, subject, action in TOPICS
                 if skill.search(name) and trigger.search(context))


def lesson_score(topics, title, unit, section=''):
    """주제와 작업이 함께 확인된 차시를 찾는다. 제목의 주제만으로는 점수를 주지 않는다."""
    if re.match(r'^\s*(?:Q\s*[.:]|질문\s*[:：])', unit, re.I):
        return 0
    # 섹션은 주제만 보완한다. 하위 차시가 단순히 '실습', '소개'라고 쓰인 것은 작업 근거가 아니다.
    if section and re.fullmatch(r'\s*(?:[\d.() -]*)(?:실습|연습|소개|요약|퀴즈|practice|exercise|lab)\s*[\d.() -]*', unit, re.I):
        section = ''
    count = sum(bool(action.search(unit) and (subject.search(unit) or subject.search(title) or subject.search(section)))
                for subject, action in topics)
    return 0 if not count else 3 * count + bool(_practice.search(unit)) + bool(_lab.search(unit))


# 직접 과업은 확인되지 않지만 필요한 구성 요소를 실제 차시에서 가르치는 경우.
# 주제·작업을 서로 다른 차시에서 합치지 않고, 빠진 과업은 모델에 그대로 알린다.
_foundations = tuple((re.compile(skill, re.I), re.compile(goal, re.I), re.compile(lesson, re.I), gap,
                      re.compile(context, re.I) if context else None) for skill, goal, lesson, gap, context in (
    ('네트워크 보안', r'방화벽|firewall', r'(?:방화벽|firewall).{0,24}(?:배포|구성|구현|관리|문제 해결)|(?:구성|배포).{0,18}(?:방화벽|firewall)', '요청한 방화벽 규칙 적용', None),
    ('클라우드 컴퓨팅', r'가용\s*영역|로드\s*밸런|부하\s*분산', r'(?:aws|아마존|amazon).{0,24}(?:\bALB\b|application load balanc\w*)|(?:azure|애저).{0,24}(?:load balancer|부하\s*분산\s*장치)', '다중 가용 영역의 부하 분산 구성', None),
    ('클라우드 IAM', r'역할|서비스\s*계정|최소\s*권한|rbac', r'(?:entra|iam|rbac|서비스\s*주체).{0,24}(?:역할|권한).{0,12}(?:구성|관리|분석|할당)', '요청 대상에 대한 역할·권한 적용', None),
    ('멀티스레딩', r'뮤텍스|mutex', r'(?:스레드|쓰레드|threads?).{0,18}(?:동기화|synchroniz)|(?:임계\s*(?:영역|구역)|critical.section).{0,20}(?:상호\s*배제|mutual exclusion)', '뮤텍스를 이용한 공유 자원 보호', None),
    ('자연어|NLP', r'(?:응답|답변).{0,24}(?:품질|근거성|정답|평가)', r'(?=.*(?:\bLLM\b|언어\s*모델))(?=.*품질)(?=.*(?:지표|측정))', '답변별 근거성·정답 일치 평가', None),
    ('자연어|NLP', r'(?:응답|답변).{0,24}(?:품질|근거성|정답|평가)', r'데이터셋.{0,15}평가\s*(?:방법|지표)', '생성 답변의 평가 기준 적용', r'자연어\s*처리|\bNLP\b|언어\s*모델'),
))


@lru_cache(maxsize=256)
def foundation_rules(name, application):
    return tuple((lesson, gap, context) for family, goal, lesson, gap, context in _foundations
                 if family.search(name) and goal.search(application))


def foundation_lessons(rules, lessons, title):
    for pattern, gap, context in rules:
        for unit in lessons:
            if pattern.search(unit) and (not context or context.search(title) or context.search(unit)):
                yield unit, gap


_practice = re.compile(r'구성|실습|연습|재현|측정|검증|구현|실행|할당|적용|작성|테스트|exercise|configure|implement', re.I)
_lab = re.compile(r'^(?:.{0,12}[·:]\s*)?(?:연습|실습|hands.on lab|exercise)\s*[-:：]', re.I)


def claims(lines):
    # 전체 목차에서 멀리 떨어진 단어를 하나의 학습 근거로 합치지 않는다.
    for line in lines:
        for sentence in catalog_candidates.description_sentences(line):
            if 0 < len(sentence) <= 450:
                yield sentence.casefold()


def profile_descriptions(lines, focused_units):
    """과업 근거를 찾은 소개문만 같은 문장 단위로 판정·발췌한다."""
    if not focused_units:
        return lines
    result = []
    for line in lines:
        sentences = catalog_candidates.description_sentences(line)
        if any(sentence.casefold() in focused_units for sentence in sentences):
            result.extend(sentences)
        else:
            result.append(line)
    return result


def identity(row, rid):
    parts = tuple(' '.join(unicodedata.normalize('NFKC', row.get(k) or '').casefold().split())
                  for k in ('title', 'provider'))
    return parts if all(parts) else rid


def distinct_courses(ordered):
    """서로 다른 ID로 배포된 동일 제목·제공처의 강좌는 가장 높은 순위 하나를 사용한다."""
    seen = set()
    result = []
    for row in ordered:
        key = identity(row, row['id'])
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def curriculum_score(index, rid, topics):
    if not topics:
        return 0
    doc = index[rid]
    cache = doc['topic_scores']
    if topics not in cache:
        rows = (doc['record'].get('curriculum') or {}).get('items') or []
        units = [(unit, rows[i].get('section') or '') for i, unit in doc['own_rows'].items()]
        units.extend((line, '') for line in claims(doc['lines']))
        cache[topics] = max((lesson_score(topics, doc['record']['title'], unit, section)
                             for unit, section in units), default=0)
    return cache[topics]


def course_window(matches, items, skill, topics, track, limit, has_learning_evidence, *, allow_topic_foundation=False,
                  related_basis=None, challenge_rank=None):
    """벡터와 실습 근거가 있는 공통 후보에서 조건에 맞는 최대 20개를 자세히 검토한다."""
    index = catalog_candidates.cached_index(items) if topics and matches else {}
    scores = {row['resource_id']: curriculum_score(index, row['resource_id'], topics) for row in matches}
    relevant = [r for r in matches if course_levels.eligible(
        {**items[r['resource_id']], 'cost': r['current_cost']}, track)]

    def order(row):
        rid = row['resource_id']
        record = items[rid]
        band = course_levels.preference(record, track)
        hours = record.get('hours')
        duration = hours if (track == 'A2' and isinstance(hours, (int, float))
                             and not isinstance(hours, bool) and hours > 0
                             and record.get('timeStatus') != 'unknown') else float('inf')
        if track == 'A2':
            # 같은 관련성 문턱을 넘은 후보는 2시간 구간·키워드 횟수보다 실제 시간을 먼저 비교한다.
            return duration, -scores[rid], -row['similarity'], rid
        if challenge_rank and len(relevant) > limit and (scores[rid] or not topics):
            priority, title = challenge_rank(rid)
            return 0, priority, -row['similarity'], title, rid
        return 1, -scores[rid], band, -row['similarity'], rid

    ordered = sorted(relevant, key=order)
    seen = set()
    window = []
    for allow_foundation in (False, True):
        target = min(limit, MIN_COURSE_CANDIDATES) if allow_foundation else limit
        if len(window) >= target:
            break
        for row in ordered:
            rid = row['resource_id']
            key = identity(items[rid], rid)
            if (key not in seen and (not topics or scores[rid] or (allow_foundation and allow_topic_foundation))
                    and has_learning_evidence(rid, skill, allow_foundation)):
                seen.add(key)
                window.append(row)
                if len(window) == target:
                    break
    if related_basis and len(window) < min(limit, MIN_COURSE_CANDIDATES):
        for row in ordered:
            rid = row['resource_id']
            key = identity(items[rid], rid)
            if key not in seen and related_basis(rid, skill):
                seen.add(key)
                window.append(row)
                if len(window) == min(limit, MIN_COURSE_CANDIDATES):
                    break
    return window
