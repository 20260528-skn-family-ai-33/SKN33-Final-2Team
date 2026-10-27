-- GrowPath · 팀 DB 추가 요청안: 스킬 선수 관계 표 public.skill_prerequisites
-- 초안(33행) · 아직 팀 DB에 없음 · tools/gen_skill_prereq_sql.py 가 skill_prerequisites.csv 에서 만든 파일(직접 고치지 말고 CSV를 고친 뒤 다시 만든다)
-- 관계는 Claude가 일반적인 학습 순서로 만든 가정이다. 팀 검토(추가·삭제) 뒤에 넣는다.
-- 뜻: prerequisite_skill_id 를 먼저 배우면 skill_id 를 배우기 쉽다(먼저 배울 스킬 → 다음 스킬). 순환(A→B→A)은 넣지 않는다(제약으로 막지는 않음).
-- 쓰는 곳: 5차 목업 검토·확정·내 로드맵 화면의 스킬 지도(GET /api/v1/skills/map). 표가 생기면 app/skillmap.py 가 CSV 대신 이 표를 읽게 바꾼다.
-- 번호는 DB 판마다 달라질 수 있어 스킬 이름으로 맞춰 넣는다. 여러 번 실행해도 된다(ON CONFLICT DO NOTHING).
BEGIN;

CREATE TABLE IF NOT EXISTS public.skill_prerequisites (
  skill_id integer NOT NULL REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE,
  prerequisite_skill_id integer NOT NULL REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT skill_prerequisites_pkey PRIMARY KEY (skill_id, prerequisite_skill_id),
  CONSTRAINT skill_prerequisites_not_self CHECK (skill_id <> prerequisite_skill_id)
);
CREATE INDEX IF NOT EXISTS skill_prerequisites_prereq_idx ON public.skill_prerequisites (prerequisite_skill_id);
COMMENT ON TABLE public.skill_prerequisites IS '스킬 선수 관계: prerequisite_skill_id 를 먼저 배우면 좋은 skill_id';

CREATE TEMP TABLE _skill_prereq_draft (skill_name text NOT NULL, prerequisite_skill_name text NOT NULL) ON COMMIT DROP;
INSERT INTO _skill_prereq_draft (skill_name, prerequisite_skill_name) VALUES
  ('SQL 쿼리 튜닝 & 인덱스 최적화', 'SQL 기본 문법 & 조인'),
  ('RDBMS 데이터 모델링', 'SQL 기본 문법 & 조인'),
  ('NoSQL & 분산 DB', 'RDBMS 데이터 모델링'),
  ('ETL & 데이터 파이프라인', 'SQL 기본 문법 & 조인'),
  ('ETL & 데이터 파이프라인', 'Python 프로그래밍 & 비동기 I/O'),
  ('데이터 웨어하우스 & OLAP', 'ETL & 데이터 파이프라인'),
  ('데이터 거버넌스 & 보안 규정 준수', 'RDBMS 데이터 모델링'),
  ('탐색적 데이터 분석(EDA) & 전처리', 'Python 프로그래밍 & 비동기 I/O'),
  ('머신러닝 지도/비지도 학습', '탐색적 데이터 분석(EDA) & 전처리'),
  ('MLOps & 모델 서빙', '머신러닝 지도/비지도 학습'),
  ('MLOps & 모델 서빙', 'Docker 컨테이너 가상화'),
  ('딥러닝 신경망 아키텍처', '머신러닝 지도/비지도 학습'),
  ('PyTorch/TensorFlow 딥러닝 구현', '딥러닝 신경망 아키텍처'),
  ('자연어 처리(NLP) & LLM 기초', '딥러닝 신경망 아키텍처'),
  ('RAG & 생성형 AI 에이전트', '자연어 처리(NLP) & LLM 기초'),
  ('컴퓨터 비전(CV) 모델링', '딥러닝 신경망 아키텍처'),
  ('자료구조 & 알고리즘 최적화', 'Python 프로그래밍 & 비동기 I/O'),
  ('객체지향 설계(OOP) & 디자인 패턴', 'Python 프로그래밍 & 비동기 I/O'),
  ('웹 프레임워크 (FastAPI/Django)', 'Python 프로그래밍 & 비동기 I/O'),
  ('RESTful API 서버 아키텍처', '웹 프레임워크 (FastAPI/Django)'),
  ('대용량 트래픽 처리 & 캐싱', 'RESTful API 서버 아키텍처'),
  ('마이크로서비스(MSA) 설계', 'RESTful API 서버 아키텍처'),
  ('웹 애플리케이션 취약점 진단', '웹 프레임워크 (FastAPI/Django)'),
  ('Docker 컨테이너 가상화', '리눅스 환경 및 Bash 스크립팅'),
  ('Kubernetes 클러스터 오케스트레이션', 'Docker 컨테이너 가상화'),
  ('CI/CD 배포 자동화 파이프라인', 'Docker 컨테이너 가상화'),
  ('클라우드 컴퓨팅 아키텍처 (AWS/Azure)', 'TCP/IP 네트워크 프로토콜'),
  ('클라우드 IAM & 네트워크 보안', '클라우드 컴퓨팅 아키텍처 (AWS/Azure)'),
  ('네트워크 보안 & 침입 탐지', 'TCP/IP 네트워크 프로토콜'),
  ('운영체제(OS) & 동시성 제어', '컴퓨터 구조 & 메모리 관리'),
  ('시스템 프로그래밍 & POSIX API', '운영체제(OS) & 동시성 제어'),
  ('멀티스레딩 & 비동기 동시성', '운영체제(OS) & 동시성 제어'),
  ('시스템 & OS 보안 강화', '운영체제(OS) & 동시성 제어');

INSERT INTO public.skill_prerequisites (skill_id, prerequisite_skill_id)
SELECT s.skill_id, p.skill_id
FROM _skill_prereq_draft v
JOIN public.skill_tags s ON s.name = v.skill_name
JOIN public.skill_tags p ON p.name = v.prerequisite_skill_name
ON CONFLICT DO NOTHING;

-- 확인 1: 지금 skill_tags 이름과 맞지 않아 빠진 행(0행이어야 한다)
SELECT v.skill_name, v.prerequisite_skill_name
FROM _skill_prereq_draft v
LEFT JOIN public.skill_tags s ON s.name = v.skill_name
LEFT JOIN public.skill_tags p ON p.name = v.prerequisite_skill_name
WHERE s.skill_id IS NULL OR p.skill_id IS NULL;
-- 확인 2: 표의 행 수
SELECT count(*) AS skill_prerequisites_rows FROM public.skill_prerequisites;

COMMIT;
