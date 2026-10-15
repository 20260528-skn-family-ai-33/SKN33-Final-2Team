/* 가상 사내 DB 직원 데이터 (tools/import_employees.py 로 엑셀에서 변환 · 실제 인사 자료 아님) */
window.GPEMP = {
 "source": "사내DB_직원가상데이터_구성초안_2.7.0.xlsx",
 "note": "GrowPath 사내 DB · 현재 직원 데이터 (직원당 한 행) · 원본: DB설계/사내DB_가데이터 · 스키마 2.7.0 · 기준일 2026-10-12 · 내보낸 시각: 2026-10-14 13:18 · 직원 16명 · 열 47개",
 "employees": [
  {
   "id": "emp-0001",
   "code": "20200001",
   "name": "김서찬",
   "role": "employee",
   "hireDate": "2020-10-01",
   "dept": "업무시스템팀",
   "parentDept": "디지털관리처",
   "grade": "4급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "응용SW엔지니어링",
   "task": "사내 서비스 API 개발 담당",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2023-01-01",
   "changeReason": "승진",
   "gradeSince": "2023-01-01",
   "historyRows": 2,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "업무시스템팀",
    "id": "grp-0001"
   },
   "mySupervisor": {
    "name": "임서현",
    "code": "20070001"
   },
   "profile": {
    "workDesc": "사내 업무 시스템의 API와 데이터 조회 기능을 유지보수한다. 규정 문서 검색에 시간이 걸려 근거 위치를 확인할 수 있는 검색 도구를 만들고 싶다.",
    "expStatus": "reported",
    "expSummary": "백엔드 개발 경험은 있지만 임베딩 검색과 RAG를 직접 구현한 경험은 없다.",
    "devYears": 3.0,
    "inputStatus": {
     "certs": "reported",
     "learning": "unprovided",
     "projects": "reported",
     "tech": "reported"
    }
   },
   "certs": [
    "SQLD (2019-09-06 취득, 만료 여부 미확인)"
   ],
   "learning": [],
   "evals": [
    {
     "period": "2024-11-01~2025-10-31",
     "title": "한국수자원공사 일반직 근무성적평정 결과(기준 2025-11-10판)",
     "grade": "우",
     "score": "42/50점",
     "consent": true
    },
    {
     "period": "2023-11-01~2024-10-31",
     "title": "한국수자원공사 일반직 근무성적평정 결과(기준 2025-11-10판)",
     "grade": "미",
     "score": "36/50점",
     "consent": true
    }
   ],
   "tech": [
    "Python 2년",
    "FastAPI 1.5년",
    "PostgreSQL 2.5년",
    "Git 3년"
   ],
   "projects": [
    "업무 조회 API 개선 (백엔드 기능 구현 담당)"
   ]
  },
  {
   "id": "emp-0002",
   "code": "20140001",
   "name": "이시현",
   "role": "employee",
   "hireDate": "2014-07-01",
   "dept": "인프라운영팀",
   "parentDept": "디지털관리처",
   "grade": "3급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "IT시스템관리",
   "task": "서비스 운영·장애 점검 담당",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2023-03-01",
   "changeReason": "전보",
   "gradeSince": "2021-01-01",
   "historyRows": 4,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "인프라운영팀",
    "id": "grp-0002"
   },
   "mySupervisor": {
    "name": "윤재호",
    "code": "20100001"
   },
   "profile": {
    "workDesc": "서비스의 배포 상태와 운영 로그를 확인하고 반복 점검 결과를 정리한다. 로그 요약을 검토한 뒤 직접 점검 기록에 반영한다.",
    "expStatus": "reported",
    "expSummary": "시스템 운영 경험은 있지만 애플리케이션 개발 경험은 적다. Python 스크립트는 기초 작업에만 사용했다.",
    "devYears": 0.5,
    "inputStatus": {
     "certs": "reported",
     "learning": "reported",
     "projects": "unprovided",
     "tech": "reported"
    }
   },
   "certs": [
    "정보처리기사 (2013-05-31 취득, 만료 없음)"
   ],
   "learning": [
    "리눅스 로그 점검 실습 교육 (사내, 8h, completed)"
   ],
   "evals": [
    {
     "period": "2024-11-01~2025-10-31",
     "title": "한국수자원공사 일반직 근무성적평정 결과(기준 2025-11-10판)",
     "grade": "우",
     "score": "점수 없음",
     "consent": false
    }
   ],
   "tech": [
    "Linux 12년",
    "Bash 12년",
    "Docker 1년",
    "Python 0.3년"
   ],
   "projects": []
  },
  {
   "id": "emp-0003",
   "code": "20190001",
   "name": "박서윤",
   "role": "employee",
   "hireDate": "2019-04-01",
   "dept": "업무시스템팀",
   "parentDept": "디지털관리처",
   "grade": "4급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "UI/UX엔지니어링",
   "task": "사내 웹 화면 개발 담당",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2023-04-01",
   "changeReason": "전보",
   "gradeSince": "2021-05-01",
   "historyRows": 3,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "업무시스템팀",
    "id": "grp-0001"
   },
   "mySupervisor": {
    "name": "임서현",
    "code": "20070001"
   },
   "profile": {
    "workDesc": "업무 포털의 입력 화면과 대시보드를 유지보수한다. 업무에 AI를 활용하고 싶지만 우선 학습할 분야와 구체적인 결과물은 아직 정하지 않았다.",
    "expStatus": "reported",
    "expSummary": "웹 화면과 API 연동 경험은 있지만 모델 학습·RAG 구현 경험은 없다.",
    "devYears": 3.0,
    "inputStatus": {
     "certs": "none_confirmed",
     "learning": "unprovided",
     "projects": "reported",
     "tech": "reported"
    }
   },
   "certs": [],
   "learning": [],
   "evals": [],
   "tech": [
    "TypeScript 2.5년",
    "React 2년",
    "CSS 3년",
    "Git 3년"
   ],
   "projects": [
    "업무 포털 화면 개선 (화면 입력 흐름 구현 담당)",
    "업무 화면 접근성 개선 (화면 구현 담당)"
   ]
  },
  {
   "id": "emp-0004",
   "code": "20230001",
   "name": "최나은",
   "role": "employee",
   "hireDate": "2023-09-01",
   "dept": "데이터운영팀",
   "parentDept": "AI데이터센터",
   "grade": "5급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "빅데이터분석",
   "task": "운영 데이터 정리 담당",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2023-09-01",
   "changeReason": "신규 임용",
   "gradeSince": "2023-09-01",
   "historyRows": 1,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "데이터운영팀",
    "id": "grp-0003"
   },
   "mySupervisor": {
    "name": "강민서",
    "code": "20080001"
   },
   "profile": {
    "workDesc": "시스템에서 생성한 운영 지표를 정리하고 일별 추이를 확인한다. 누락과 중복을 처리하는 작업을 수행하지만 예측 모델을 직접 학습한 경험은 없다.",
    "expStatus": "reported",
    "expSummary": "데이터 조회·정제 경험은 있으나 모델 학습과 예측 결과 평가 경험은 없다.",
    "devYears": 2.0,
    "inputStatus": {
     "certs": "reported",
     "learning": "unprovided",
     "projects": "unprovided",
     "tech": "reported"
    }
   },
   "certs": [
    "ADsP (2024-11-29 취득, 만료 여부 미확인)"
   ],
   "learning": [],
   "evals": [],
   "tech": [
    "Python 2년",
    "pandas 1.5년",
    "PostgreSQL 1년",
    "Git 2년"
   ],
   "projects": []
  },
  {
   "id": "emp-0005",
   "code": "20260001",
   "name": "정유찬",
   "role": "employee",
   "hireDate": "2026-04-01",
   "dept": "업무시스템팀",
   "parentDept": "디지털관리처",
   "grade": "5급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "응용SW엔지니어링",
   "task": "소규모 업무 스크립트 작성 담당",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2026-04-01",
   "changeReason": "신규 임용",
   "gradeSince": "2026-04-01",
   "historyRows": 1,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "업무시스템팀",
    "id": "grp-0001"
   },
   "mySupervisor": {
    "name": "임서현",
    "code": "20070001"
   },
   "profile": {
    "workDesc": "부서에서 반복 파일 정리 작업을 보조한다. 간단한 코드는 따라 작성해 봤으며 독립적인 API 설계·배포 경험은 없다.",
    "expStatus": "reported",
    "expSummary": "안내에 따라 Python 코드를 작성해 봤고 생성형 AI는 코드 설명을 질문하는 용도로만 사용했다.",
    "devYears": 0.5,
    "inputStatus": {
     "certs": "unprovided",
     "learning": "unprovided",
     "projects": "unprovided",
     "tech": "reported"
    }
   },
   "certs": [],
   "learning": [],
   "evals": [],
   "tech": [
    "Python 0.5년",
    "Git 0.5년",
    "SQLite 0.2년"
   ],
   "projects": []
  },
  {
   "id": "emp-0006",
   "code": "19980001",
   "name": "한정민",
   "role": "employee",
   "hireDate": "1998-03-01",
   "dept": "디지털관리처",
   "parentDept": "AI본부",
   "grade": "1급",
   "jobFamily": null,
   "position": "처장",
   "job": "정보기술기획",
   "task": "디지털관리처 업무 총괄",
   "supervisor": true,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2022-03-01",
   "changeReason": "승진",
   "gradeSince": "2022-03-01",
   "historyRows": 9,
   "supGroup": {
    "name": "디지털관리처 팀장",
    "id": "grp-0004"
   },
   "members": [
    {
     "name": "임서현",
     "code": "20070001"
    },
    {
     "name": "윤재호",
     "code": "20100001"
    }
   ],
   "planGroup": null,
   "mySupervisor": null,
   "profile": null,
   "certs": [
    "정보처리기사 (1999-12-10 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": []
  },
  {
   "id": "emp-0007",
   "code": "20010001",
   "name": "오태준",
   "role": "employee",
   "hireDate": "2001-03-01",
   "dept": "AI데이터센터",
   "parentDept": "AI본부",
   "grade": "2급(갑)",
   "jobFamily": null,
   "position": "센터장",
   "job": "정보기술기획",
   "task": "AI데이터센터 업무 총괄",
   "supervisor": true,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2023-03-01",
   "changeReason": "승진",
   "gradeSince": "2023-03-01",
   "historyRows": 8,
   "supGroup": {
    "name": "AI데이터센터 팀장",
    "id": "grp-0005"
   },
   "members": [
    {
     "name": "강민서",
     "code": "20080001"
    }
   ],
   "planGroup": null,
   "mySupervisor": null,
   "profile": null,
   "certs": [
    "정보처리기사 (2002-06-14 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)",
    "AI 활용 관리자 과정 (위탁, 시간 미기록, not_completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": []
  },
  {
   "id": "emp-0008",
   "code": "20070001",
   "name": "임서현",
   "role": "employee",
   "hireDate": "2007-03-01",
   "dept": "업무시스템팀",
   "parentDept": "디지털관리처",
   "grade": "2급(을)",
   "jobFamily": "기술",
   "position": "팀장",
   "job": "정보기술기획",
   "task": "업무시스템 개발·자동화 업무 관리",
   "supervisor": true,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2021-07-01",
   "changeReason": "전보",
   "gradeSince": "2020-03-01",
   "historyRows": 7,
   "supGroup": {
    "name": "업무시스템팀",
    "id": "grp-0001"
   },
   "members": [
    {
     "name": "김서찬",
     "code": "20200001"
    },
    {
     "name": "박서윤",
     "code": "20190001"
    },
    {
     "name": "정유찬",
     "code": "20260001"
    },
    {
     "name": "조은호",
     "code": "20220001"
    }
   ],
   "planGroup": {
    "name": "디지털관리처 팀장",
    "id": "grp-0004"
   },
   "mySupervisor": {
    "name": "한정민",
    "code": "19980001"
   },
   "profile": null,
   "certs": [
    "정보처리기사 (2006-09-15 취득, 만료 없음)",
    "AWS Certified Solutions Architect – Associate (2024-09-10 취득, 유효, 만료일 2027-09-10)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": []
  },
  {
   "id": "emp-0009",
   "code": "20100001",
   "name": "윤재호",
   "role": "employee",
   "hireDate": "2010-03-01",
   "dept": "인프라운영팀",
   "parentDept": "디지털관리처",
   "grade": "3급",
   "jobFamily": "특수기술/전산",
   "position": "팀장",
   "job": "정보기술기획",
   "task": "인프라 운영 업무 관리",
   "supervisor": true,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2021-03-01",
   "changeReason": "전보",
   "gradeSince": "2018-03-01",
   "historyRows": 5,
   "supGroup": {
    "name": "인프라운영팀",
    "id": "grp-0002"
   },
   "members": [
    {
     "name": "이시현",
     "code": "20140001"
    },
    {
     "name": "신유진",
     "code": "20210001"
    },
    {
     "name": "문시우",
     "code": "20240001"
    }
   ],
   "planGroup": {
    "name": "디지털관리처 팀장",
    "id": "grp-0004"
   },
   "mySupervisor": {
    "name": "한정민",
    "code": "19980001"
   },
   "profile": null,
   "certs": [
    "정보처리기사 (2012-12-07 취득, 만료 없음)",
    "AWS Certified Solutions Architect – Associate (2021-06-15 취득, 만료됨, 만료일 2024-06-15)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": []
  },
  {
   "id": "emp-0010",
   "code": "20080001",
   "name": "강민서",
   "role": "employee",
   "hireDate": "2008-03-01",
   "dept": "데이터운영팀",
   "parentDept": "AI데이터센터",
   "grade": "2급(을)",
   "jobFamily": "기술",
   "position": "팀장",
   "job": "정보기술기획",
   "task": "데이터 수집·품질·분석 업무 관리",
   "supervisor": true,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2022-03-01",
   "changeReason": "전보",
   "gradeSince": "2021-03-01",
   "historyRows": 7,
   "supGroup": {
    "name": "데이터운영팀",
    "id": "grp-0003"
   },
   "members": [
    {
     "name": "최나은",
     "code": "20230001"
    },
    {
     "name": "배지안",
     "code": "20210002"
    },
    {
     "name": "권우진",
     "code": "20240002"
    }
   ],
   "planGroup": {
    "name": "AI데이터센터 팀장",
    "id": "grp-0005"
   },
   "mySupervisor": {
    "name": "오태준",
    "code": "20010001"
   },
   "profile": {
    "workDesc": "데이터 수집·품질·분석 업무를 관리한다.",
    "expStatus": "reported",
    "expSummary": "데이터 품질 점검 업무를 수행했다.",
    "devYears": 0.0,
    "inputStatus": {
     "certs": "reported",
     "learning": "reported",
     "projects": "unprovided",
     "tech": "unprovided"
    }
   },
   "certs": [
    "정보처리기사 (2009-05-29 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [
    {
     "period": "2024-11-01~2025-10-31",
     "title": "한국수자원공사 일반직 근무성적평정 결과(기준 2025-11-10판)",
     "grade": "우",
     "score": "점수 없음",
     "consent": false
    }
   ],
   "tech": [],
   "projects": []
  },
  {
   "id": "emp-0011",
   "code": "20220001",
   "name": "조은호",
   "role": "employee",
   "hireDate": "2022-03-01",
   "dept": "업무시스템팀",
   "parentDept": "디지털관리처",
   "grade": "4급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "응용SW엔지니어링",
   "task": "업무포털 기능 유지보수",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2025-03-01",
   "changeReason": "승진",
   "gradeSince": "2025-03-01",
   "historyRows": 2,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "업무시스템팀",
    "id": "grp-0001"
   },
   "mySupervisor": {
    "name": "임서현",
    "code": "20070001"
   },
   "profile": {
    "workDesc": "업무포털의 기능을 유지보수하는 업무를 맡고 있다.",
    "expStatus": "reported",
    "expSummary": "온라인 실습을 따라 FAQ 문서 검색 데모를 만들어 봤다. 혼자 처음부터 만든 적은 없다.",
    "devYears": null,
    "inputStatus": {
     "certs": "reported",
     "learning": "reported",
     "projects": "reported",
     "tech": "unprovided"
    }
   },
   "certs": [
    "정보처리기사 (2021-06-18 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)",
    "FAQ 문서 검색 데모 온라인 실습 (온라인, 시간 미기록, completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": [
    "FAQ 문서 검색 데모 (온라인 실습 수행)"
   ]
  },
  {
   "id": "emp-0012",
   "code": "20210001",
   "name": "신유진",
   "role": "employee",
   "hireDate": "2021-03-01",
   "dept": "인프라운영팀",
   "parentDept": "디지털관리처",
   "grade": "4급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "IT시스템관리",
   "task": "서버 상태와 배포 점검",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2024-03-01",
   "changeReason": "승진",
   "gradeSince": "2024-03-01",
   "historyRows": 2,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "인프라운영팀",
    "id": "grp-0002"
   },
   "mySupervisor": {
    "name": "윤재호",
    "code": "20100001"
   },
   "profile": null,
   "certs": [
    "정보처리기사 (2022-09-16 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": []
  },
  {
   "id": "emp-0013",
   "code": "20240001",
   "name": "문시우",
   "role": "employee",
   "hireDate": "2024-03-01",
   "dept": "인프라운영팀",
   "parentDept": "디지털관리처",
   "grade": "5급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "IT시스템관리",
   "task": "운영 로그 수집과 장애 기록 정리",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2024-03-01",
   "changeReason": "신규 임용",
   "gradeSince": "2024-03-01",
   "historyRows": 1,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "인프라운영팀",
    "id": "grp-0002"
   },
   "mySupervisor": {
    "name": "윤재호",
    "code": "20100001"
   },
   "profile": {
    "workDesc": "운영 로그를 수집하고 장애 기록을 정리하는 업무를 맡고 있다.",
    "expStatus": "reported",
    "expSummary": "Python・Bash로 로그 수집·정리 운영 스크립트를 작성했다. 생성형 AI·RAG 경험과 관련 학습 기록은 없다.",
    "devYears": null,
    "inputStatus": {
     "certs": "reported",
     "learning": "reported",
     "projects": "unprovided",
     "tech": "reported"
    }
   },
   "certs": [
    "정보처리기사 (2023-11-24 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [],
   "tech": [
    "Python",
    "Bash"
   ],
   "projects": []
  },
  {
   "id": "emp-0014",
   "code": "20210002",
   "name": "배지안",
   "role": "employee",
   "hireDate": "2021-03-01",
   "dept": "데이터운영팀",
   "parentDept": "AI데이터센터",
   "grade": "4급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "DB엔지니어링",
   "task": "데이터 적재와 누락값 점검",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2024-03-01",
   "changeReason": "승진",
   "gradeSince": "2024-03-01",
   "historyRows": 2,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "데이터운영팀",
    "id": "grp-0003"
   },
   "mySupervisor": {
    "name": "강민서",
    "code": "20080001"
   },
   "profile": {
    "workDesc": "데이터를 적재하고 누락값을 점검하는 업무를 맡고 있다.",
    "expStatus": "reported",
    "expSummary": "팀 운영 매뉴얼의 임베딩 검색과 원문 위치 표시를 혼자 구현했다.",
    "devYears": null,
    "inputStatus": {
     "certs": "reported",
     "learning": "reported",
     "projects": "reported",
     "tech": "unprovided"
    }
   },
   "certs": [
    "정보처리기사 (2020-12-11 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": [
    "팀 운영 매뉴얼 검색 (직접 구현)"
   ]
  },
  {
   "id": "emp-0015",
   "code": "20240002",
   "name": "권우진",
   "role": "employee",
   "hireDate": "2024-03-01",
   "dept": "데이터운영팀",
   "parentDept": "AI데이터센터",
   "grade": "5급",
   "jobFamily": "특수기술/전산",
   "position": null,
   "job": "빅데이터분석",
   "task": "운영 지표 집계와 품질 점검",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2024-03-01",
   "changeReason": "신규 임용",
   "gradeSince": "2024-03-01",
   "historyRows": 1,
   "supGroup": null,
   "members": [],
   "planGroup": {
    "name": "데이터운영팀",
    "id": "grp-0003"
   },
   "mySupervisor": {
    "name": "강민서",
    "code": "20080001"
   },
   "profile": null,
   "certs": [
    "정보처리기사 (2025-03-07 취득, 만료 없음)"
   ],
   "learning": [
    "정보보안 기본 교육 (사내, 2h, completed)",
    "데이터 분석 자격 대비 과정 (온라인, 시간 미기록, not_completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": []
  },
  {
   "id": "emp-0016",
   "code": "20180001",
   "name": "서하린",
   "role": "hr_admin",
   "hireDate": "2018-03-01",
   "dept": "인재경영실",
   "parentDept": "경영부문",
   "grade": "4급",
   "jobFamily": "행정/행정",
   "position": null,
   "job": "인사",
   "task": "인사 기본 정보와 서비스 계정 관리",
   "supervisor": false,
   "empGroup": "일반직",
   "status": "재직",
   "membershipStatus": "active",
   "accountStatus": "active",
   "validFrom": "2021-03-01",
   "changeReason": "승진",
   "gradeSince": "2021-03-01",
   "historyRows": 2,
   "supGroup": null,
   "members": [],
   "planGroup": null,
   "mySupervisor": null,
   "profile": {
    "workDesc": "인사 기본 정보와 계정을 관리하고 엑셀로 인사 현황 표를 정리한다.",
    "expStatus": "reported",
    "expSummary": "인사 정보와 계정 관리, 엑셀 현황 표 정리 업무를 맡고 있으며 개발 경험은 없다.",
    "devYears": 0.0,
    "inputStatus": {
     "certs": "reported",
     "learning": "reported",
     "projects": "unprovided",
     "tech": "unprovided"
    }
   },
   "certs": [
    "SQLD (2017-09-08 취득, 만료 여부 미확인)"
   ],
   "learning": [
    "개인정보보호 기본 교육 (사내, 2h, completed)"
   ],
   "evals": [],
   "tech": [],
   "projects": []
  }
 ]
};
