/* 화면 고정 값 (5차 gp-data.js 의 window.GPD 그대로 · 2026-10-26 옮김)
   학습 자료·자격증·직원·규정 같은 데이터는 서버(팀 DB)에서 읽는다. 여기에는 화면 문구·5점 척도·관점 이름·가상 사내 홈페이지 메뉴처럼 고정된 값만 둔다 */

export interface IntranetMenu {
  id: string;
  title: string;
  menu: string;
  covers: string;
  dept: string;
  keys: string[];
}
export interface Stage {
  n: number;
  name: string;
  desc: string;
}
export interface Perspective {
  name: string;
  short: string;
  focus: string;
}
/** [값, 보이는 이름] */
export type Pair = [string, string];

export interface GpData {
  intranet: IntranetMenu[];
  stages: Stage[];
  detailFields: Pair[];
  formatOpts: Pair[];
  autoHours: number;
  answerOpts: Pair[];
  answerWeight: Record<string, number>;
  areas: Record<string, string>;
  skills: Record<string, string>;
  perspectives: Record<string, Perspective>;
  optionOrder: string[];
  goalSelf: string[];
  commentSample: { fit: string; fitText: string; level: string; levelText: string; free: string };
  commentFit: Pair[];
  commentLevel: Pair[];
}

export const D: GpData = {
  "intranet": [
    {
      "id": "notice",
      "title": "공지사항",
      "menu": "홈 › 공지사항",
      "covers": "전사 공지, 행사·설명회 안내, 시스템 점검 일정",
      "dept": "각 공지 작성 부서",
      "keys": [
        "공지",
        "행사",
        "설명회",
        "점검 일정",
        "안내문"
      ]
    },
    {
      "id": "cafeteria",
      "title": "사내 식당 식단표",
      "menu": "생활 › 사내 식당",
      "covers": "주간 식단, 식당 운영 시간, 식권 사용 안내",
      "dept": "총무팀(가상)",
      "keys": [
        "식단",
        "점심",
        "저녁",
        "메뉴",
        "식당",
        "밥",
        "식권",
        "구내식당"
      ]
    },
    {
      "id": "shuttle",
      "title": "통근버스",
      "menu": "생활 › 통근버스",
      "covers": "노선·정류장, 시간표, 탑승 신청",
      "dept": "총무팀(가상)",
      "keys": [
        "통근",
        "셔틀",
        "버스",
        "출퇴근 버스",
        "정류장"
      ]
    },
    {
      "id": "parking",
      "title": "주차 등록",
      "menu": "생활 › 주차",
      "covers": "직원 차량 등록, 방문 차량 사전 등록, 주차장 위치",
      "dept": "총무팀(가상)",
      "keys": [
        "주차",
        "차량 등록",
        "방문 차량"
      ]
    },
    {
      "id": "meeting",
      "title": "회의실 예약",
      "menu": "업무 지원 › 회의실 예약",
      "covers": "회의실 현황, 예약·취소, 화상회의 장비 대여",
      "dept": "총무팀(가상)",
      "keys": [
        "회의실",
        "예약",
        "화상회의"
      ]
    },
    {
      "id": "welfare",
      "title": "복지포인트·복지몰",
      "menu": "복지 › 복지몰",
      "covers": "복지포인트 잔액·사용처, 복지몰 구매",
      "dept": "인재경영실 복지 담당(가상)",
      "keys": [
        "복지포인트",
        "복지몰",
        "포인트"
      ]
    },
    {
      "id": "health",
      "title": "건강검진",
      "menu": "복지 › 건강검진",
      "covers": "검진 기관, 신청 기간, 결과 확인",
      "dept": "인재경영실 복지 담당(가상)",
      "keys": [
        "건강검진",
        "검진"
      ]
    },
    {
      "id": "club",
      "title": "사내 동호회",
      "menu": "소통 › 동호회",
      "covers": "동호회 목록, 가입 신청, 활동 공지",
      "dept": "각 동호회 운영진",
      "keys": [
        "동호회",
        "모임",
        "클럽"
      ]
    },
    {
      "id": "family",
      "title": "경조사 알림",
      "menu": "소통 › 경조사",
      "covers": "경조사 소식 게시, 경조 화환 신청 안내",
      "dept": "총무팀(가상)",
      "keys": [
        "경조사",
        "결혼",
        "부고",
        "화환"
      ]
    },
    {
      "id": "cert",
      "title": "증명서 발급",
      "menu": "인사 › 증명서 발급",
      "covers": "재직·경력증명서 온라인 발급",
      "dept": "인재경영실(가상)",
      "keys": [
        "증명서",
        "재직증명",
        "경력증명"
      ]
    },
    {
      "id": "attendance",
      "title": "근태·휴가 신청",
      "menu": "인사 › 근태",
      "covers": "휴가·출장 신청 화면, 근태 기록 조회 (휴가 일수·요건은 규정 질문)",
      "dept": "인재경영실(가상)",
      "keys": [
        "휴가 신청",
        "연차 신청",
        "근태",
        "출장 신청",
        "출근 기록"
      ]
    },
    {
      "id": "payslip",
      "title": "급여 명세서",
      "menu": "인사 › 급여 명세서",
      "covers": "월별 급여 명세서 조회 (보수 기준은 규정 질문)",
      "dept": "인재경영실 급여 담당(가상)",
      "keys": [
        "급여 명세서",
        "명세서",
        "월급 명세"
      ]
    },
    {
      "id": "org",
      "title": "조직도·직원 찾기",
      "menu": "홈 › 조직도",
      "covers": "부서 조직도, 직원 연락처 검색",
      "dept": "인재경영실(가상)",
      "keys": [
        "조직도",
        "연락처",
        "내선",
        "직원 찾기",
        "담당자 찾기"
      ]
    },
    {
      "id": "helpdesk",
      "title": "IT 헬프데스크",
      "menu": "업무 지원 › IT 헬프데스크",
      "covers": "계정 잠금·비밀번호 초기화, VPN, PC·프린터 장애 신고",
      "dept": "인프라운영팀(가상)",
      "keys": [
        "비밀번호",
        "계정",
        "잠금",
        "vpn",
        "VPN",
        "프린터",
        "PC 고장",
        "헬프데스크",
        "장애 신고"
      ]
    },
    {
      "id": "software",
      "title": "소프트웨어 사용 신청",
      "menu": "업무 지원 › 소프트웨어 신청",
      "covers": "사내 허용 소프트웨어 목록, 설치 신청",
      "dept": "인프라운영팀(가상)",
      "keys": [
        "소프트웨어",
        "프로그램 설치",
        "설치 신청",
        "라이선스"
      ]
    },
    {
      "id": "genai",
      "title": "생성형 AI 이용 안내",
      "menu": "업무 지원 › 생성형 AI 이용 안내",
      "covers": "사내에서 쓸 수 있는 AI 서비스 목록, 이용 신청, 보안 유의사항",
      "dept": "디지털관리처(가상)",
      "keys": [
        "생성형 AI 이용",
        "AI 서비스",
        "챗GPT",
        "ChatGPT",
        "AI 사용 신청"
      ]
    },
    {
      "id": "edu",
      "title": "교육 신청(인재개발 포털)",
      "menu": "교육 › 교육 신청",
      "covers": "사내·위탁 교육 과정 목록, 신청 현황 (교육비 지원 기준은 규정 질문)",
      "dept": "인재경영실 교육 담당(가상)",
      "keys": [
        "교육 신청",
        "과정 신청",
        "교육 과정",
        "수강 신청"
      ]
    },
    {
      "id": "library",
      "title": "전자도서관",
      "menu": "교육 › 전자도서관",
      "covers": "전자책, 학술 데이터베이스 이용",
      "dept": "인재경영실 교육 담당(가상)",
      "keys": [
        "전자도서관",
        "전자책",
        "도서관",
        "논문"
      ]
    },
    {
      "id": "voice",
      "title": "제안·고충 접수",
      "menu": "소통 › 제안·고충",
      "covers": "업무 개선 제안, 고충 상담 신청 창구",
      "dept": "인재경영실(가상)",
      "keys": [
        "제안",
        "고충 접수",
        "건의"
      ]
    },
    {
      "id": "safety",
      "title": "안전보건",
      "menu": "안전 › 안전보건",
      "covers": "안전교육 이수 현황, 사고·위험 신고",
      "dept": "안전관리팀(가상)",
      "keys": [
        "안전교육",
        "사고 신고",
        "위험 신고"
      ]
    },
    {
      "id": "expense",
      "title": "출장비 정산",
      "menu": "업무 지원 › 출장 정산",
      "covers": "출장비 정산 신청 화면 (지급 기준은 여비 규정 질문)",
      "dept": "재무팀(가상)",
      "keys": [
        "출장비 정산",
        "정산",
        "영수증"
      ]
    }
  ],
  "stages": [
    {
      "n": 1,
      "name": "기초 다지기",
      "desc": "AI·데이터 기본 개념과 도구를 익혀요"
    },
    {
      "n": 2,
      "name": "핵심 이해",
      "desc": "목표 분야의 핵심 방법을 익혀요"
    },
    {
      "n": 3,
      "name": "업무 적용",
      "desc": "업무와 연결한 과제로 결과물을 만들어요"
    },
    {
      "n": 4,
      "name": "성과 확인",
      "desc": "결과물이나 자격으로 학습 결과를 확인해요"
    }
  ],
  "detailFields": [
    [
      "format",
      "학습 방식"
    ],
    [
      "cert",
      "자격증 계획"
    ],
    [
      "hours",
      "주당 학습 시간"
    ],
    [
      "weeks",
      "정해진 기간"
    ],
    [
      "budget",
      "교육 예산"
    ],
    [
      "etc",
      "기타 고려 사항"
    ]
  ],
  "formatOpts": [
    [
      "video",
      "영상 강의"
    ],
    [
      "doc",
      "문서·도서 읽기"
    ],
    [
      "practice",
      "직접 구현하며 학습"
    ],
    [
      "mixed",
      "여러 방식 함께"
    ]
  ],
  "autoHours": 4,
  "answerOpts": [
    [
      "1",
      "전혀 아님"
    ],
    [
      "2",
      "아님"
    ],
    [
      "3",
      "보통이다"
    ],
    [
      "4",
      "그렇다"
    ],
    [
      "5",
      "매우 그렇다"
    ]
  ],
  "answerWeight": {
    "1": 0,
    "2": 0.25,
    "3": 0.5,
    "4": 0.75,
    "5": 1
  },
  "areas": {
    "ai": "AI 이해",
    "dev": "개발 경험",
    "rag": "RAG·문서 검색",
    "data": "데이터 분석",
    "ops": "LLM 서비스 운영",
    "cert": "자격증"
  },
  "skills": {
    "llm-basic": "LLM의 동작 방식과 한계",
    "prompt": "프롬프트 설계",
    "embedding": "임베딩과 벡터 검색 원리",
    "python": "Python 기초",
    "pandas": "pandas 데이터 처리",
    "api": "외부 API 호출",
    "git": "Git 버전 관리",
    "rag": "RAG 구조 이해",
    "langchain": "LangChain으로 검색·답변 흐름 구성",
    "vectordb": "벡터DB로 문서 색인 만들기",
    "chunking": "문서 분할과 검색 품질 점검",
    "llm-api": "LLM API 호출과 응답 처리",
    "cleaning": "결측값·이상값 처리",
    "viz": "데이터 시각화",
    "sklearn": "머신러닝 모델 학습",
    "validation": "학습·검증 데이터 설계",
    "sql": "SQL 데이터 조회",
    "secrets": "API 키 관리",
    "injection": "프롬프트 인젝션 대응",
    "masking": "개인정보 가리기",
    "eval": "답변 품질 평가",
    "integration": "사내 시스템 연동",
    "ai-basic": "AI 기본 개념",
    "data-cert": "데이터 자격 준비",
    "ai-cert": "AI 활용 자격 준비",
    "dev-cert": "개발 자격 준비",
    "ops-cert": "서버·네트워크 자격 준비",
    "cloud-cert": "AI·클라우드 자격 준비"
  },
  "perspectives": {
    "A1": {
      "name": "Free Track",
      "short": "Free",
      "focus": "비용 부담 최소화. 무료 강좌·공식 문서와 직접 실습 중심"
    },
    "A2": {
      "name": "Fast Track",
      "short": "Fast",
      "focus": "짧은 기간·적은 학습 부담. 핵심 강의와 꼭 필요한 실습만"
    },
    "A3": {
      "name": "Challenge Track",
      "short": "Challenge",
      "focus": "담당 업무에 바로 활용. 실제 업무 과제와 결과물 중심"
    }
  },
  "optionOrder": [
    "A1",
    "A2",
    "A3"
  ],
  "goalSelf": [
    "거의 못 이뤘어요",
    "조금 이뤘어요",
    "절반쯤 이뤘어요",
    "대부분 이뤘어요",
    "충분히 이뤘어요"
  ],
  "commentSample": {
    "fit": "good",
    "fitText": "부서 규정 질의응답 개선 과제와 방향이 맞아요.",
    "level": "adjust",
    "levelText": "품질 점검이 짧아 보여요. 점검 문항을 늘려 1~2주 더 두면 좋겠어요.",
    "free": "시제품에는 공개 가능한 규정만 쓰고, 보안 담당자와 먼저 상의해 주세요."
  },
  "commentFit": [
    [
      "good",
      "잘 맞아요"
    ],
    [
      "partial",
      "보완하면 좋아요"
    ],
    [
      "none",
      "의견 없음"
    ]
  ],
  "commentLevel": [
    [
      "ok",
      "적절해요"
    ],
    [
      "adjust",
      "조정이 필요해요"
    ],
    [
      "none",
      "의견 없음"
    ]
  ]
};

/** 내부 관점 ID를 사용자 표시 이름으로 변환한다. 기존 저장 데이터에도 적용. */
export const trackName = (id: string, fallback = ""): string => D.perspectives[id]?.name || fallback;
