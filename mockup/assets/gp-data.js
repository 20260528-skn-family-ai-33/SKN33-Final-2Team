/* GrowPath 4차 목업 (Claude) · 시연 데이터
   기준: (1007) 기획서 보완안 V13 + 사용자 피드백(10/8). 규정 원문은 regulation.js
   실제 자료: KOHI 과정(2026.09.30 조사), Python·LangChain 공식 문서(2026.10.07 확인), 자격 이름. 나머지는 가상 */
window.GPD = {
  today: '2026-10-08',

  /* 계정 (10/15): 시연 인물(김하늘·이서준·정민수·최유진)은 가상 사내 DB 직원 데이터 초안에 없어 뺐다.
     로그인 계정·내 정보·부서장 권한은 employees.js(가상 사내 DB 직원 16명)만 쓴다 */

  /* 목표 후보 기본값 (4차 묶음 7 · FR-05): 프로필에 본인 입력 정보가 없어 판단 근거가 부족할 때 보여 주는 AI 활용 업무 후보 3개 */
  goalDefaults: [
    { goal: '사내 규정 문서를 검색하고 근거를 제시하는 RAG 질의응답 시제품을 개발하고 싶어요.', why: '문서가 많은 부서에서 가장 먼저 시도하는 AI 활용 업무예요.' },
    { goal: 'Python으로 운영 데이터를 정리하고 AI 분석 결과를 검증하는 역량을 기르고 싶어요.', why: '데이터를 다루는 업무라면 분석 결과를 직접 확인하는 힘이 필요해요.' },
    { goal: '생성형 AI를 사내 시스템에 연결하고 응답 품질과 보안을 점검하고 싶어요.', why: '사내 시스템에 AI를 붙일 때 품질과 보안을 함께 보는 역량이에요.' }
  ],

  /* 가상 사내 홈페이지 메뉴 안내 (4차 묶음 7 · 사내 생활 도우미의 '일반 · 사내 생활' 답변 범위).
     어느 메뉴에서 무엇을 확인하는지만 담는다. 식단·버스 시간·금액 같은 실제 값은 없다(지어내지 않게). 실제 기관 홈페이지가 아니다 */
  intranet: [
    { id: 'notice', title: '공지사항', menu: '홈 › 공지사항', covers: '전사 공지, 행사·설명회 안내, 시스템 점검 일정', dept: '각 공지 작성 부서', keys: ['공지', '행사', '설명회', '점검 일정', '안내문'] },
    { id: 'cafeteria', title: '사내 식당 식단표', menu: '생활 › 사내 식당', covers: '주간 식단, 식당 운영 시간, 식권 사용 안내', dept: '총무팀(가상)', keys: ['식단', '점심', '저녁', '메뉴', '식당', '밥', '식권', '구내식당'] },
    { id: 'shuttle', title: '통근버스', menu: '생활 › 통근버스', covers: '노선·정류장, 시간표, 탑승 신청', dept: '총무팀(가상)', keys: ['통근', '셔틀', '버스', '출퇴근 버스', '정류장'] },
    { id: 'parking', title: '주차 등록', menu: '생활 › 주차', covers: '직원 차량 등록, 방문 차량 사전 등록, 주차장 위치', dept: '총무팀(가상)', keys: ['주차', '차량 등록', '방문 차량'] },
    { id: 'meeting', title: '회의실 예약', menu: '업무 지원 › 회의실 예약', covers: '회의실 현황, 예약·취소, 화상회의 장비 대여', dept: '총무팀(가상)', keys: ['회의실', '예약', '화상회의'] },
    { id: 'welfare', title: '복지포인트·복지몰', menu: '복지 › 복지몰', covers: '복지포인트 잔액·사용처, 복지몰 구매', dept: '인재경영실 복지 담당(가상)', keys: ['복지포인트', '복지몰', '포인트'] },
    { id: 'health', title: '건강검진', menu: '복지 › 건강검진', covers: '검진 기관, 신청 기간, 결과 확인', dept: '인재경영실 복지 담당(가상)', keys: ['건강검진', '검진'] },
    { id: 'club', title: '사내 동호회', menu: '소통 › 동호회', covers: '동호회 목록, 가입 신청, 활동 공지', dept: '각 동호회 운영진', keys: ['동호회', '모임', '클럽'] },
    { id: 'family', title: '경조사 알림', menu: '소통 › 경조사', covers: '경조사 소식 게시, 경조 화환 신청 안내', dept: '총무팀(가상)', keys: ['경조사', '결혼', '부고', '화환'] },
    { id: 'cert', title: '증명서 발급', menu: '인사 › 증명서 발급', covers: '재직·경력증명서 온라인 발급', dept: '인재경영실(가상)', keys: ['증명서', '재직증명', '경력증명'] },
    { id: 'attendance', title: '근태·휴가 신청', menu: '인사 › 근태', covers: '휴가·출장 신청 화면, 근태 기록 조회 (휴가 일수·요건은 규정 질문)', dept: '인재경영실(가상)', keys: ['휴가 신청', '연차 신청', '근태', '출장 신청', '출근 기록'] },
    { id: 'payslip', title: '급여 명세서', menu: '인사 › 급여 명세서', covers: '월별 급여 명세서 조회 (보수 기준은 규정 질문)', dept: '인재경영실 급여 담당(가상)', keys: ['급여 명세서', '명세서', '월급 명세'] },
    { id: 'org', title: '조직도·직원 찾기', menu: '홈 › 조직도', covers: '부서 조직도, 직원 연락처 검색', dept: '인재경영실(가상)', keys: ['조직도', '연락처', '내선', '직원 찾기', '담당자 찾기'] },
    { id: 'helpdesk', title: 'IT 헬프데스크', menu: '업무 지원 › IT 헬프데스크', covers: '계정 잠금·비밀번호 초기화, VPN, PC·프린터 장애 신고', dept: '인프라운영팀(가상)', keys: ['비밀번호', '계정', '잠금', 'vpn', 'VPN', '프린터', 'PC 고장', '헬프데스크', '장애 신고'] },
    { id: 'software', title: '소프트웨어 사용 신청', menu: '업무 지원 › 소프트웨어 신청', covers: '사내 허용 소프트웨어 목록, 설치 신청', dept: '인프라운영팀(가상)', keys: ['소프트웨어', '프로그램 설치', '설치 신청', '라이선스'] },
    { id: 'genai', title: '생성형 AI 이용 안내', menu: '업무 지원 › 생성형 AI 이용 안내', covers: '사내에서 쓸 수 있는 AI 서비스 목록, 이용 신청, 보안 유의사항', dept: '디지털관리처(가상)', keys: ['생성형 AI 이용', 'AI 서비스', '챗GPT', 'ChatGPT', 'AI 사용 신청'] },
    { id: 'edu', title: '교육 신청(인재개발 포털)', menu: '교육 › 교육 신청', covers: '사내·위탁 교육 과정 목록, 신청 현황 (교육비 지원 기준은 규정 질문)', dept: '인재경영실 교육 담당(가상)', keys: ['교육 신청', '과정 신청', '교육 과정', '수강 신청'] },
    { id: 'library', title: '전자도서관', menu: '교육 › 전자도서관', covers: '전자책, 학술 데이터베이스 이용', dept: '인재경영실 교육 담당(가상)', keys: ['전자도서관', '전자책', '도서관', '논문'] },
    { id: 'voice', title: '제안·고충 접수', menu: '소통 › 제안·고충', covers: '업무 개선 제안, 고충 상담 신청 창구', dept: '인재경영실(가상)', keys: ['제안', '고충 접수', '건의'] },
    { id: 'safety', title: '안전보건', menu: '안전 › 안전보건', covers: '안전교육 이수 현황, 사고·위험 신고', dept: '안전관리팀(가상)', keys: ['안전교육', '사고 신고', '위험 신고'] },
    { id: 'expense', title: '출장비 정산', menu: '업무 지원 › 출장 정산', covers: '출장비 정산 신청 화면 (지급 기준은 여비 규정 질문)', dept: '재무팀(가상)', keys: ['출장비 정산', '정산', '영수증'] }
  ],

  stages: [
    { n: 1, name: '기초 다지기', desc: 'AI·데이터 기본 개념과 도구를 익혀요' },
    { n: 2, name: '핵심 이해', desc: '목표 분야의 핵심 방법을 익혀요' },
    { n: 3, name: '업무 적용', desc: '업무와 연결한 과제로 결과물을 만들어요' },
    { n: 4, name: '성과 확인', desc: '결과물이나 자격으로 학습 결과를 확인해요' }
  ],

  /* 세부 사항: 학습 선호 5가지 + 기타 고려 사항 (10/13: 입력 폼, 빈 칸은 '알아서') */
  detailFields: [['format', '학습 방식'], ['cert', '자격증 계획'], ['hours', '주당 학습 시간'], ['weeks', '정해진 기간'], ['budget', '교육 예산'], ['etc', '기타 고려 사항']],
  formatOpts: [['video', '영상 강의'], ['doc', '문서·도서 읽기'], ['practice', '직접 구현하며 학습'], ['mixed', '여러 방식 함께']],
  /* 자격증 계획 후보 26종 (10/13 · 국내 16 + 해외 10). 세부 사항에서 분야 → 자격 2단계 드롭다운으로 고른다. 기본값은 '계획 없음'.
     이름·시행 기관만 확인했고(공식 페이지 링크), 응시료·일정·응시 자격은 확인 필요. hours 는 준비 시간 계획값(가상).
     해외 10종은 AI 이해·모델 개발·생성형 AI·배포/운영 분야에서 고름 (AWS ML Specialty 는 2026.3.31 응시 종료라 뺌) */
  certGroups: [
    { key: 'data', label: '데이터·SQL·데이터 설계', skill: 'data-cert', issuer: '한국데이터산업진흥원', url: 'https://www.dataq.or.kr/www/sub/introduction.do', certs: [
      { id: 'sqld', short: 'SQLD', sub: 'SQL 개발자', hours: 20 },
      { id: 'sqlp', short: 'SQLP', sub: 'SQL 전문가', hours: 50 },
      { id: 'adsp', short: 'ADsP', sub: '데이터분석 준전문가', hours: 20 },
      { id: 'adp', short: 'ADP', sub: '데이터분석 전문가', hours: 80 },
      { id: 'bigdata', short: '빅데이터분석기사', hours: 40 },
      { id: 'dasp', short: 'DAsP', sub: '데이터아키텍처 준전문가', hours: 30 },
      { id: 'dap', short: 'DAP', sub: '데이터아키텍처 전문가', hours: 80 }] },
    { key: 'dev', label: '소프트웨어 개발', skill: 'dev-cert', issuer: '한국산업인력공단', certs: [
      { id: 'infoeng', short: '정보처리기사', hours: 60, url: 'https://www.q-net.or.kr/crf005.do?id=crf00503&jmCd=1320' },
      { id: 'infoind', short: '정보처리산업기사', hours: 40, url: 'https://www.q-net.or.kr/crf005.do?gId=&gSite=Q&id=crf00503&jmCd=2290&tabGbn=1' }] },
    { key: 'ops', label: '서버·네트워크 운영', skill: 'ops-cert', certs: [
      { id: 'linux1', short: '리눅스마스터 1급', hours: 50, issuer: '한국정보통신진흥협회', url: 'https://manager.ihd.or.kr/introducesubject1.do' },
      { id: 'linux2', short: '리눅스마스터 2급', hours: 25, issuer: '한국정보통신진흥협회', url: 'https://manager.ihd.or.kr/introducesubject1.do' },
      { id: 'net1', short: '네트워크관리사 1급', hours: 40, issuer: '한국정보통신자격협회', url: 'https://exam.icqa.or.kr/cn/page/network' },
      { id: 'net2', short: '네트워크관리사 2급', hours: 20, issuer: '한국정보통신자격협회', url: 'https://exam.icqa.or.kr/cn/page/network' }] },
    { key: 'aikr', label: '국내 AI 활용·개발', skill: 'ai-cert', issuer: 'KT', url: 'https://aice.study/certi/examSchedule', certs: [
      { id: 'aice_basic', short: 'AICE Basic', hours: 10 },
      { id: 'aice_assoc', short: 'AICE Associate', hours: 20 },
      { id: 'aice_pro', short: 'AICE Professional', hours: 40 }] },
    { key: 'global', label: '해외 AI·클라우드', skill: 'cloud-cert', certs: [
      { id: 'aws_clf', vendor: 'AWS', short: 'Cloud Practitioner', name: 'AWS Certified Cloud Practitioner', hours: 15 },
      { id: 'aws_aif', vendor: 'AWS', short: 'AI Practitioner', name: 'AWS Certified AI Practitioner', hours: 20 },
      { id: 'aws_mla', vendor: 'AWS', short: 'Machine Learning Engineer – Associate', name: 'AWS Certified Machine Learning Engineer – Associate', hours: 45 },
      { id: 'aws_dea', vendor: 'AWS', short: 'Data Engineer – Associate', name: 'AWS Certified Data Engineer – Associate', hours: 40 },
      { id: 'aws_saa', vendor: 'AWS', short: 'Solutions Architect – Associate', name: 'AWS Certified Solutions Architect – Associate', hours: 40 },
      { id: 'aws_aip', vendor: 'AWS', short: 'Generative AI Developer – Professional', name: 'AWS Certified Generative AI Developer – Professional', hours: 60 },
      { id: 'gc_gail', vendor: 'Google Cloud', short: 'Generative AI Leader', name: 'Google Cloud Generative AI Leader', hours: 15 },
      { id: 'gc_pmle', vendor: 'Google Cloud', short: 'Professional Machine Learning Engineer', name: 'Google Cloud Professional Machine Learning Engineer', hours: 60 },
      { id: 'gc_pde', vendor: 'Google Cloud', short: 'Professional Data Engineer', name: 'Google Cloud Professional Data Engineer', hours: 50 },
      { id: 'db_genai', vendor: 'Databricks', short: 'Generative AI Engineer Associate', name: 'Databricks Certified Generative AI Engineer Associate', hours: 30 }] }
  ],
  vendorUrl: { AWS: 'https://aws.amazon.com/certification/', 'Google Cloud': 'https://cloud.google.com/learn/certification', Databricks: 'https://www.databricks.com/learn/training/certification' },
  /* 주당 학습 시간을 비워 두면('알아서') 로드맵 계획 에이전트가 정한다. 가데이터 에이전트는 기간이 없을 때 이 값을 쓴다 */
  autoHours: 4,

  /* 사전·사후 점검: 5점 척도 (10/13 결정). 문항은 '~할 수 있다 / ~를 알고 있다' 서술문.
     수준값은 (점수-1)/4 로 0~1 에 놓고 저장만 한다 */
  answerOpts: [['1', '전혀 아님'], ['2', '아님'], ['3', '보통이다'], ['4', '그렇다'], ['5', '매우 그렇다']],
  answerWeight: { 1: 0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1 },
  areas: { ai: 'AI 이해', dev: '개발 경험', rag: 'RAG·문서 검색', data: '데이터 분석', ops: 'LLM 서비스 운영', cert: '자격증' },
  qbank: {
    ai: [
      { id: 'ai1', text: 'LLM이 사실이 아닌 내용을 그럴듯하게 지어낼 수 있다(환각)는 것을 알고 있다.', skill: 'llm-basic' },
      { id: 'ai2', text: '프롬프트에 예시와 출력 형식을 넣어 답변을 조정할 수 있다.', skill: 'prompt' },
      { id: 'ai3', text: '임베딩(문장을 숫자 벡터로 바꾸는 것)이 무엇인지 알고 있다.', skill: 'embedding' }
    ],
    dev: [
      { id: 'dev1', text: 'Python으로 파일을 읽고 쓰는 코드를 직접 작성할 수 있다.', skill: 'python' },
      { id: 'dev2', text: 'pandas로 표 데이터를 불러와 가공할 수 있다.', skill: 'pandas' },
      { id: 'dev3', text: 'requests 같은 라이브러리로 외부 API를 호출할 수 있다.', skill: 'api' },
      { id: 'dev4', text: 'Git으로 코드를 버전 관리할 수 있다.', skill: 'git' }
    ],
    rag: [
      { id: 'rag1', text: 'RAG(검색 증강 생성)가 어떻게 동작하는지 알고 있다.', skill: 'rag' },
      { id: 'rag2', text: 'LangChain이나 LlamaIndex를 쓸 수 있다.', skill: 'langchain' },
      { id: 'rag3', text: 'FAISS·Chroma 같은 벡터DB를 쓸 수 있다.', skill: 'vectordb' },
      { id: 'rag4', text: '긴 문서를 청크로 나눠 검색할 수 있다.', skill: 'chunking' },
      { id: 'rag5', text: 'OpenAI 같은 LLM API를 코드에서 호출할 수 있다.', skill: 'llm-api' }
    ],
    data: [
      { id: 'da1', text: '결측값·이상값을 찾아 처리할 수 있다.', skill: 'cleaning' },
      { id: 'da2', text: 'matplotlib 같은 도구로 데이터를 시각화할 수 있다.', skill: 'viz' },
      { id: 'da3', text: 'scikit-learn으로 모델을 학습시킬 수 있다.', skill: 'sklearn' },
      { id: 'da4', text: '학습·검증 데이터를 나누는 이유를 알고 있다.', skill: 'validation' },
      { id: 'da5', text: 'SQL로 필요한 데이터를 조회할 수 있다.', skill: 'sql' }
    ],
    ops: [
      { id: 'op1', text: 'API 키를 코드에 넣지 않고 안전하게 관리하는 방법을 알고 있다.', skill: 'secrets' },
      { id: 'op2', text: '프롬프트 인젝션이 무엇인지 알고 있다.', skill: 'injection' },
      { id: 'op3', text: '개인정보를 가린 뒤 LLM에 보낼 수 있다.', skill: 'masking' },
      { id: 'op4', text: 'LLM 응답 품질을 기준을 정해 평가할 수 있다.', skill: 'eval' },
      { id: 'op5', text: '사내 시스템에 외부 API를 연동할 수 있다.', skill: 'integration' }
    ]
  },
  skills: {
    'llm-basic': 'LLM의 동작 방식과 한계', prompt: '프롬프트 설계', embedding: '임베딩과 벡터 검색 원리', python: 'Python 기초', pandas: 'pandas 데이터 처리',
    api: '외부 API 호출', git: 'Git 버전 관리', rag: 'RAG 구조 이해', langchain: 'LangChain으로 검색·답변 흐름 구성', vectordb: '벡터DB로 문서 색인 만들기',
    chunking: '문서 분할과 검색 품질 점검', 'llm-api': 'LLM API 호출과 응답 처리', cleaning: '결측값·이상값 처리', viz: '데이터 시각화', sklearn: '머신러닝 모델 학습',
    validation: '학습·검증 데이터 설계', sql: 'SQL 데이터 조회', secrets: 'API 키 관리', injection: '프롬프트 인젝션 대응', masking: '개인정보 가리기',
    eval: '답변 품질 평가', integration: '사내 시스템 연동', 'ai-basic': 'AI 기본 개념', 'data-cert': '데이터 자격 준비', 'ai-cert': 'AI 활용 자격 준비',
    'dev-cert': '개발 자격 준비', 'ops-cert': '서버·네트워크 자격 준비', 'cloud-cert': 'AI·클라우드 자격 준비'
  },
  domains: {
    rag: { label: 'RAG·문서 검색', test: /(RAG|검색|규정|질의|챗봇|문서|지식)/i, outcome: '근거 조항을 함께 보여주는 사내 규정 질의응답 시제품' },
    data: { label: '데이터 분석', test: /(데이터|분석|예측|수질|시각화|통계)/, outcome: '운영 데이터 분석 결과와 검증 기록' },
    ops: { label: 'LLM 서비스 운영', test: /(연결|연동|보안|품질|운영|사내 시스템)/, outcome: '응답 품질·보안 점검표를 갖춘 생성형 AI 연동 시제품' }
  },

  /* 등록된 외부 학습자료 (과정·도서·자격·공식 문서). real:false 는 가상. cost:null 은 '확인 필요' */
  res: {
    kohi_ai: { title: '초보자를 위한 AI 완전 정복', provider: 'KOHI', kind: '강좌', format: '영상', hours: 4, cost: 0, real: true, stage: 1, skills: ['ai-basic', 'llm-basic'],
      audience: 'AI를 처음 배우는 공공기관 직원', prereq: '없음', content: 'AI 기본 개념과 업무 활용 사례', source: '외부 학습자료 조사', checked: '2026-09-30', note: '모집 상태·교육 인정 여부는 확인 필요' },
    py_tut: { title: 'The Python Tutorial', provider: 'Python Software Foundation', kind: '공식 문서', format: '문서', hours: 2, cost: 0, real: true, stage: 1, skills: ['python'],
      audience: '프로그래밍 경험이 있고 Python을 복습하려는 개발자', prereq: '일반적인 프로그래밍 기초', content: '기본 문법, 제어 흐름, 자료구조, 함수, 모듈',
      url: 'https://docs.python.org/3/tutorial/', source: 'Python 공식 문서', checked: '2026-10-07', note: '시간은 발췌 읽기 계획값' },
    lc_search: { title: 'Build a semantic search engine with LangChain', provider: 'LangChain', kind: '공식 문서', format: '문서', hours: 3, cost: 0, real: true, stage: 2, skills: ['langchain', 'chunking', 'embedding', 'vectordb'],
      audience: '문서 검색·RAG를 처음 구현하려는 개발자', prereq: 'Python 패키지 설치·코드 실행', content: '문서 로딩, 텍스트 분할, 임베딩, 벡터 저장소·검색',
      url: 'https://docs.langchain.com/oss/python/langchain/knowledge-base', source: 'LangChain 공식 문서', checked: '2026-10-07', note: '문서 열람 0원 · 임베딩 API 실습 비용은 별도' },
    v_llm: { title: 'LLM·임베딩·RAG 핵심 개념', provider: '샘플 아카데미', kind: '강좌', format: '영상', hours: 5, cost: 0, real: false, stage: 2, skills: ['llm-basic', 'embedding', 'rag', 'prompt'],
      audience: '개발 경험이 있고 LLM은 처음인 직원', prereq: 'Python 기초', content: 'LLM 동작 원리, 임베딩, 검색 증강 생성(RAG) 구조', source: '시연 DB 등록', checked: '2026-10-08' },
    v_fast: { title: 'LLM·RAG 핵심 압축 과정', provider: '샘플 아카데미', kind: '강좌', format: '영상', hours: 6, cost: 89000, real: false, stage: 2, skills: ['llm-basic', 'rag', 'llm-api'],
      audience: '짧은 기간에 RAG 데모를 만들어 보려는 개발자', prereq: 'Python 기초', content: 'RAG 핵심 개념과 예제 코드 실습', source: '시연 DB 등록', checked: '2026-10-08', note: '가상 유료 과정 · 교육비 지원 여부는 확인 필요' },
    v_vec_doc: { title: '문서 분할·벡터 검색 학습 가이드', provider: '샘플 출판사', kind: '도서', format: '문서', hours: 3, cost: 18000, real: false, stage: 2, skills: ['chunking', 'vectordb'],
      audience: 'RAG의 검색 품질을 높이려는 개발자', prereq: '임베딩 기본 개념', content: '청크 나누기, 벡터 검색, 검색 결과 평가', source: '시연 DB 등록', checked: '2026-10-08' },
    v_vec_video: { title: '벡터 검색 입문', provider: '샘플 아카데미', kind: '강좌', format: '영상', hours: 3, cost: 0, real: false, stage: 2, skills: ['chunking', 'vectordb'],
      audience: 'RAG의 검색 단계를 처음 배우는 개발자', prereq: '임베딩 기본 개념', content: '청크 나누기, 벡터 검색 원리, 간단한 실습', source: '시연 DB 등록', checked: '2026-10-08' },
    v_eval: { title: 'LLM 답변 품질 점검 실무', provider: '샘플 아카데미', kind: '강좌', format: '영상', hours: 3, cost: 0, real: false, stage: 3, skills: ['eval', 'injection'],
      audience: 'LLM 서비스를 운영·검증하는 개발자', prereq: 'LLM API 호출 경험', content: '평가 기준 정하기, 근거 대조, 프롬프트 인젝션 점검', source: '시연 DB 등록', checked: '2026-10-08' }
    /* 자격 자료(cert_<id>)는 아래 certGroups 에서 만든다 */
  },

  /* 관점별 하위 에이전트 (A1·A2·A3) */
  perspectives: {
    A1: { name: '비용 우선안', short: '비용', focus: '비용 부담 최소화. 무료 강좌·공식 문서와 직접 실습 중심' },
    A2: { name: '시간 우선안', short: '시간', focus: '짧은 기간·적은 학습 부담. 핵심 강의와 꼭 필요한 실습만' },
    A3: { name: '업무 적용 우선안', short: '업무 적용', focus: '담당 업무에 바로 활용. 실제 업무 과제와 결과물 중심' }
  },
  /* 가데이터 모드의 후보 (RAG 시나리오). 자격증 활동은 학습 선호에 따라 붙인다 */
  templates: {
    A1: { tagline: '무료 강좌와 공식 문서로 비용 없이', reason: '등록된 무료 자료만 써서 교육 비용이 들지 않아요.',
      pros: ['교육 비용 0원', '필요한 부분을 반복해서 읽기 쉬워요'], cons: ['자료를 직접 연결하고 오류를 해결할 시간이 필요해요'], scope: '공개 샘플 문서로 질의응답 최소 기능',
      acts: [
        { stage: 1, title: '초보자를 위한 AI 완전 정복 수강', res: 'kohi_ai' },
        { stage: 1, title: 'Python 공식 튜토리얼 복습 (발췌)', res: 'py_tut' },
        { stage: 2, title: 'LLM·임베딩·RAG 핵심 개념 수강', res: 'v_llm' },
        { stage: 2, title: 'LangChain 검색 문서 읽고 정리', res: 'lc_search' },
        { stage: 2, title: '문서 분할·검색 방법을 작은 예제로 비교', hours: 4, how: '같은 문서를 두세 가지 방식으로 나눠 검색 결과를 비교해 보세요.' },
        { stage: 3, title: '공개 샘플 문서로 질의응답 최소 기능 구현', hours: 12, how: '공개된 샘플 문서로 질문을 받고 관련 문단을 찾아 답하는 기능을 만들어요.' },
        { stage: 3, title: '답변 근거를 원문과 대조하는 방법 정리', hours: 4, how: '답변마다 근거 문단을 함께 보여주고, 원문과 맞는지 확인하는 순서를 정리해요.' },
        { stage: 4, title: '결과물 정리와 시연 메모 작성', hours: 4, how: '만든 기능과 한계를 한 장으로 정리해요.' }
      ] },
    A2: { tagline: '핵심 강의와 필수 실습만 짧게', reason: '핵심 강의 하나와 꼭 필요한 실습만 담아 가장 빨리 끝나요.',
      pros: ['기간이 가장 짧아요', '주마다 할 일이 단순해요'], cons: ['유료 과정이 들어 있어요', '사내 문서 적용은 다음 계획으로 미뤄요'], scope: '강의 예제 범위의 질의응답 데모',
      acts: [
        { stage: 1, title: '초보자를 위한 AI 완전 정복 수강', res: 'kohi_ai' },
        { stage: 2, title: 'LLM·RAG 핵심 압축 과정 수강', res: 'v_fast' },
        { stage: 2, title: '강의 예제로 RAG 데모 실행', hours: 2, how: '강의에서 제공하는 예제를 그대로 실행해 동작을 확인해요.' },
        { stage: 3, title: '예제 범위의 질의응답 데모 완성', hours: 6, how: '예제 문서를 바꿔 넣고 질문·답변이 되는지 확인해요.' },
        { stage: 4, title: '데모 결과 정리', hours: 2, how: '되는 것과 안 되는 것을 짧게 정리해요.' }
      ] },
    A3: { tagline: '사내 규정 문서로 시제품 만들기', reason: '사내 규정 문서로 시제품을 만들어, 목표한 결과물을 바로 얻어요.',
      pros: ['업무에 쓸 시제품이 결과물로 남아요', 'K-water GPT·Water-Chat과 같은 분야를 직접 다뤄요'], cons: ['기간이 가장 길어요', '사내 문서를 쓸 수 있는 범위를 먼저 확인해야 해요'], scope: '공개 가능한 사내 규정 문서로 근거 조항을 보여주는 시제품',
      acts: [
        { stage: 1, title: '초보자를 위한 AI 완전 정복 수강', res: 'kohi_ai' },
        { stage: 2, title: 'LLM·임베딩·RAG 핵심 개념 수강', res: 'v_llm' },
        { stage: 2, title: '문서 분할·벡터 검색 학습 가이드 읽기', res: 'v_vec_doc' },
        { stage: 3, title: '공개 가능한 사내 규정 문서 10건 정리·색인', hours: 6, how: '공개해도 되는 규정 문서만 골라 조항 단위로 나누고 색인을 만들어요.' },
        { stage: 3, title: '질문에 근거 조항을 함께 보여주는 시제품 구현', hours: 14, how: '질문을 받으면 관련 조항을 찾아 답변과 함께 조항 번호를 보여줘요.' },
        { stage: 3, title: '답변·원문 대조 품질 점검 20문항', hours: 4, how: '질문 20개로 답변이 원문 조항과 맞는지 하나씩 확인해요.' },
        { stage: 4, title: '시제품 시연과 결과 정리', hours: 4, how: '팀에 시연하고 받은 의견과 한계를 정리해요.' }
      ] }
  },
  /* 가데이터 모드에서 '이 안만 다시 만들기'를 누르면 번갈아 쓰는 두 번째 구성 */
  templatesAlt: {
    A1: { tagline: '공식 문서 예제로 직접 만들어 보기', reason: '강의 대신 공식 문서 예제를 따라 하며 무료로 익혀요.',
      pros: ['교육 비용 0원', '실제 코드 흐름을 바로 익혀요'], cons: ['막히는 부분을 스스로 찾아 해결해야 해요'], scope: '공식 문서 예제를 바탕으로 한 문서 검색기',
      acts: [
        { stage: 1, title: 'Python 공식 튜토리얼 복습 (발췌)', res: 'py_tut' },
        { stage: 2, title: 'LangChain 검색 문서 읽고 정리', res: 'lc_search' },
        { stage: 2, title: '벡터 검색 입문 수강', res: 'v_vec_video' },
        { stage: 2, title: '공식 문서 예제대로 문서 검색기 만들기', hours: 6, how: '문서 로딩부터 벡터 검색까지 공식 예제를 그대로 따라 만들어요.' },
        { stage: 3, title: '공개 샘플 문서로 질의응답 기능 구현', hours: 14, how: '만든 검색기에 질문·답변 단계를 붙여 샘플 문서로 시험해요.' },
        { stage: 3, title: '답변에 근거 문단 표시 추가', hours: 4, how: '답변마다 어느 문단을 근거로 썼는지 함께 보여줘요.' },
        { stage: 4, title: '결과 정리와 다음 과제 메모', hours: 3, how: '만든 기능과 한계, 다음에 해 볼 것을 정리해요.' }
      ] },
    A2: { tagline: '무료 핵심 강의로 가장 짧게', reason: '무료 핵심 강의 하나와 꼭 필요한 실습만 담아 비용 없이 빨리 끝나요.',
      pros: ['기간이 짧고 비용이 없어요'], cons: ['강의 범위를 넘는 내용은 따로 찾아야 해요', '사내 문서 적용은 다음 계획으로 미뤄요'], scope: '강의 예제 범위의 질의응답 데모',
      acts: [
        { stage: 1, title: '초보자를 위한 AI 완전 정복 수강', res: 'kohi_ai' },
        { stage: 2, title: 'LLM·임베딩·RAG 핵심 개념 수강', res: 'v_llm' },
        { stage: 2, title: '강의 예제로 RAG 데모 실행', hours: 2, how: '강의 예제를 그대로 실행해 동작을 확인해요.' },
        { stage: 3, title: '예제 범위의 질의응답 데모 완성', hours: 6, how: '예제 문서를 바꿔 넣고 질문·답변이 되는지 확인해요.' },
        { stage: 4, title: '데모 결과 정리', hours: 2, how: '되는 것과 안 되는 것을 짧게 정리해요.' }
      ] },
    A3: { tagline: '규정 질의응답 시제품과 품질 점검까지', reason: '사내 규정 문서로 시제품을 만들고, 답변 품질 점검에 시간을 더 써요.',
      pros: ['업무에 쓸 시제품이 남아요', '답변 품질을 기준을 정해 확인해요'], cons: ['기간이 길어요', '사내 문서를 쓸 수 있는 범위를 먼저 확인해야 해요'], scope: '근거 조항을 보여주고 품질 점검 기록을 남긴 규정 질의응답 시제품',
      acts: [
        { stage: 1, title: '초보자를 위한 AI 완전 정복 수강', res: 'kohi_ai' },
        { stage: 2, title: 'LLM·임베딩·RAG 핵심 개념 수강', res: 'v_llm' },
        { stage: 2, title: 'LangChain 검색 문서 읽고 정리', res: 'lc_search' },
        { stage: 3, title: '공개 가능한 사내 규정 문서 10건 정리·색인', hours: 6, how: '공개해도 되는 규정 문서만 골라 조항 단위로 나누고 색인을 만들어요.' },
        { stage: 3, title: '질문에 근거 조항을 함께 보여주는 시제품 구현', hours: 12, how: '질문을 받으면 관련 조항을 찾아 답변과 함께 조항 번호를 보여줘요.' },
        { stage: 3, title: 'LLM 답변 품질 점검 실무 수강', res: 'v_eval' },
        { stage: 3, title: '답변·원문 대조 품질 점검 30문항', hours: 6, how: '질문 30개로 답변이 원문 조항과 맞는지 기준표로 확인해요.' },
        { stage: 4, title: '시제품 시연과 결과 정리', hours: 4, how: '팀에 시연하고 받은 의견과 한계를 정리해요.' }
      ] }
  },
  optionOrder: ['A1', 'A2', 'A3'],

  goalSelf: ['거의 못 이뤘어요', '조금 이뤘어요', '절반쯤 이뤘어요', '대부분 이뤘어요', '충분히 이뤘어요'],

  /* '로드맵 2개 함께 진행' 시연의 두 번째 로드맵 목표 (가데이터 A1 비용 우선안을 씀 · 4차 묶음 6) */
  scenario2Goal: '무료 공개 자료만으로 부서 FAQ 문서를 검색하는 작은 시제품을 만들어 보고 싶어요.',

  /* 시연 시나리오 (단계 바로 이동용) */
  scenario: {
    goal: '사내 규정 문서를 검색하고 근거를 제시하는 RAG 질의응답 시제품을 개발하고 싶어요.',
    details: { format: 'practice', cert: '', hours: 4, weeks: '', budget: 0, etc: '다음 달 둘째 주는 출장이 많아서 공부를 못 할 것 같아요.' },
    pre: { ai1: '4', ai2: '4', ai3: '2', dev1: '5', dev2: '4', dev3: '4', dev4: '3', rag1: '2', rag2: '1', rag3: '1', rag4: '1', rag5: '2' },
    post: { ai1: '5', ai2: '4', ai3: '4', dev1: '5', dev2: '4', dev3: '4', dev4: '4', rag1: '4', rag2: '4', rag3: '3', rag4: '4', rag5: '2' }
  },

  /* 부서장 코멘트 예시 문장 ('시연용 예시 문장'·'코멘트 받은 뒤' 단계). 소속 직원 목록은 DB 감독 그룹에서 가져온다(10/15) */
  commentSample: {
    fit: 'good', fitText: '부서 규정 질의응답 개선 과제와 방향이 맞아요.',
    level: 'adjust', levelText: '품질 점검이 짧아 보여요. 점검 문항을 늘려 1~2주 더 두면 좋겠어요.',
    free: '시제품에는 공개 가능한 규정만 쓰고, 보안 담당자와 먼저 상의해 주세요.'
  },
  commentFit: [['good', '잘 맞아요'], ['partial', '보완하면 좋아요'], ['none', '의견 없음']],
  commentLevel: [['ok', '적절해요'], ['adjust', '조정이 필요해요'], ['none', '의견 없음']]
};

/* 자격증 후보 → 이름표·찾기표·등록 자료(cert_<id>, 4단계 성과 확인) */
(function (D) {
  D.certById = {};
  D.certGroups.forEach(g => g.certs.forEach(c => {
    c.group = g.key; c.issuer = c.issuer || g.issuer || c.vendor; c.url = c.url || g.url || D.vendorUrl[c.vendor];
    c.name = c.name || (c.sub ? `${c.short}(${c.sub})` : c.short);
    D.certById[c.id] = c;
    D.res['cert_' + c.id] = { title: c.name, provider: c.issuer, kind: '자격', format: '시험', hours: c.hours, cost: null, real: true, stage: 4, skills: [g.skill],
      audience: `${g.label} 역량을 자격으로 확인하려는 직원`, prereq: '응시 자격 확인 필요', content: `${g.label} 분야 자격 시험 준비`, url: c.url,
      source: '자격 정보 (이름·시행 기관만 확인)', checked: '2026-10-13', note: '시험 일정·응시료·응시 자격은 확인 필요 · 준비 시간은 계획값' };
  }));
})(window.GPD);
