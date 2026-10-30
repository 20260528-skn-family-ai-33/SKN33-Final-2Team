"""Explicit existing-name aliases and evidence-based skill matching. YAML remains authoritative."""
import re
from src.shared.config_loader import get_rules_config

ALIASES = {'SQL 기본 문법 & 조인': 'SQL 기본 문법 & 조인', 'SQL 쿼리 튜닝 & 인덱스 최적화': 'SQL 쿼리 튜닝 & 인덱스 최적화', 'RDBMS 데이터 모델링 & 정규화': 'RDBMS 데이터 모델링', 'NoSQL & 분산 데이터베이스': 'NoSQL & 분산 DB', 'ETL & 데이터 파이프라인 구축': 'ETL & 데이터 파이프라인', '데이터 웨어하우스 & OLAP': '데이터 웨어하우스 & OLAP', '탐색적 데이터 분석(EDA) & 특성공학': '탐색적 데이터 분석(EDA) & 전처리', '머신러닝 지도/비지도 모델링': '머신러닝 지도/비지도 학습', 'MLOps & 모델 서빙 인프라': 'MLOps & 모델 서빙', '딥러닝 심층신경망(CNN/RNN) 아키텍처': '딥러닝 신경망 아키텍처', 'PyTorch/TensorFlow 딥러닝 구현': 'PyTorch/TensorFlow 딥러닝 구현', '자연어처리(NLP) & 거대언어모델(LLM)': '자연어 처리(NLP) & LLM 기초', 'RAG & 프롬프트 엔지니어링': 'RAG & 생성형 AI 에이전트', '컴퓨터 비전 & 이미지 처리': '컴퓨터 비전(CV) 모델링', '리눅스 시스템 & 쉘 스크립트': '리눅스 환경 및 Bash 스크립팅', 'TCP/IP & 컴퓨터 네트워크 기초': 'TCP/IP 네트워크 프로토콜', '클라우드 인프라 아키텍처 (AWS/GCP)': '클라우드 컴퓨팅 아키텍처 (AWS/Azure)', '클라우드 인프라 보안 & IAM': '클라우드 IAM & 네트워크 보안', 'Docker 컨테이너 가상화': 'Docker 컨테이너 가상화', 'Kubernetes 오케스트레이션': 'Kubernetes 클러스터 오케스트레이션', 'CI/CD 자동화 배포 파이프라인': 'CI/CD 배포 자동화 파이프라인', 'Python 심화 & 비동기 프로그래밍': 'Python 프로그래밍 & 비동기 I/O', '자료구조 & 코딩테스트 알고리즘': '자료구조 & 알고리즘 최적화', '운영체제 커널 & 프로세스 동기화': '운영체제(OS) & 동시성 제어', '컴퓨터 구조 & 메모리 계층 최적화': '컴퓨터 구조 & 메모리 관리', '객체지향 설계(OOP) & 디자인 패턴': '객체지향 설계(OOP) & 디자인 패턴', 'RESTful API 아키텍처 설계': 'RESTful API 서버 아키텍처', '대용량 트래픽 처리 & 캐싱(Redis)': '대용량 트래픽 처리 & 캐싱', '마이크로서비스 아키텍처(MSA)': '마이크로서비스(MSA) 설계', '웹 프레임워크 실무 (FastAPI/Django)': '웹 프레임워크 (FastAPI/Django)', '시스템 프로그래밍 & 저수준 I/O': '시스템 프로그래밍 & POSIX API', '동시성 제어 & 멀티스레딩': '멀티스레딩 & 비동기 동시성', '시스템 & 리눅스 커널 보안': '시스템 & OS 보안 강화', '웹 애플리케이션 취약점 진단': '웹 애플리케이션 취약점 진단', '네트워크 보안 & 침입탐지(IDS/IPS)': '네트워크 보안 & 침입 탐지', '암호학 기초 & 데이터 거버넌스': '데이터 거버넌스 & 보안 규정 준수'}

# Literal domain terms supplement existing YAML patterns; never attach a default skill.
TERMS = {
 'CI/CD 배포 자동화 파이프라인': [r'(?<![A-Za-z0-9_])CI\s*&\s*CD(?![A-Za-z0-9_])'],
 'SQL 기본 문법 & 조인': [r'\bsql\b', r'postgresql', r'mysql'],
 'ETL & 데이터 파이프라인': [r'아파치\s*스파크', r'스파크\s*(?:SQL|애플리케이션|프로그램|데이터)',
                        r'\b(?:flume|sqoop)\b'],
 '데이터 웨어하우스 & OLAP': [
     r'(?:\bhive\b|하이브)[^\n.!?。]{0,45}(?:실습|쿼리|테이블|데이터\s*처리|분석|설치|학습)',
     r'(?:실습|쿼리|테이블|데이터\s*처리|분석|설치)[^\n.!?。]{0,45}(?:\bhive\b|하이브)'],
 '탐색적 데이터 분석(EDA) & 전처리': [r'데이터[^\n.!?。]{0,24}전처리', r'결측\s*(?:값|치)', r'이상\s*치'],
 'RDBMS 데이터 모델링': [r'데이터베이스\s*(설계|모델링|관리)', r'relational database', r'database design'],
 'TCP/IP 네트워크 프로토콜': [r'네트워크\s*(엔지니어|설계|운영|프로토콜|계층|구성|모니터링)', r'컴퓨터\s*네트워크',
                           r'\b(?:tcp|udp|ipv[46])\b', r'\bIP\s*주소', r'서브넷', r'\bnetwork\s+(?:layer|protocol)',
                           r'전송\s*제어\s*프로토콜'],
 '시스템 & OS 보안 강화': [r'시스템\s*보안', r'리눅스\s*보안', r'Windows\s*보안',
                       r'공격\s*표면\s*(?:감소|축소)', r'IIS\s*서버\s*강화'],
 '네트워크 보안 & 침입 탐지': [r'네트워크\s*보안', r'침입\s*탐지'],
 'SQL 쿼리 튜닝 & 인덱스 최적화': [r'query\s*(optimization|tuning)', r'index\s*optimization', r'실행\s*계획',
                               r'쿼리\s*(?:성능\s*)?(?:최적화|튜닝)', r'쿼리\s*성능\s*(?:평가|분석)',
                               r'인덱스\s*(?:조정|최적화|유형|형식)'],

 '머신러닝 지도/비지도 학습': [r'machine learning', r'머신\s*러닝', r'기계\s*학습', r'신경\s*회로망',
                           r'(?:선형|로지스틱|소프트맥스)\s*회귀'],
 '딥러닝 신경망 아키텍처': [r'deep learning', r'딥\s*러닝', r'합성곱\s*신경망', r'순환\s*신경망', r'convolutional neural',
                       r'다층\s*(?:퍼셉트론|신경망)', r'multi.layer\s*perceptron'],
 '자연어 처리(NLP) & LLM 기초': [r'자연어\s*처리', r'natural language', r'large language model',
                            r'텍스트\s*(?:데이터\s*)?분석', r'감성\s*분석', r'\bdialogflow\b', r'음성\s*대화',
                            r'conversational\s*ai', r'automatic\s*speech\s*recognition', r'language\s*agent'],
 'RAG & 생성형 AI 에이전트': [r'retrieval.augmented', r'검색\s*증강', r'generative ai',
                         r'\bai\s*에이전트', r'\bai\s+agents?\b',
                         r'에이전틱\s*ai\b', r'\bagentic\s+ai\b',
                         r'\bcopilot\s+studio\b[^\n.!?。]{0,40}?에이전트',
                         r'(?:\bsecurity|보안)\s+copilot\b[^\n.!?。]{0,40}?에이전트',
                         r'\bmicrosoft\s+365\s+copilot\b[^\n.!?。]{0,40}?에이전트[^\n.!?。]{0,120}?(?:구성|관리|보안)'],
 '컴퓨터 비전(CV) 모델링': [r'컴퓨터\s*비전', r'computer vision', r'이미지\s*(분류|인식|처리)', r'object detection', r'opencv'],
 '리눅스 환경 및 Bash 스크립팅': [r'\blinux\b', r'\bbash\b', r'리눅스'],
 '클라우드 컴퓨팅 아키텍처 (AWS/Azure)': [r'클라우드\s*(컴퓨팅|아키텍처)', r'cloud architecture', r'클라우드\s*(시스템|인프라|엔지니어)', r'cloud infrastructure'],
 '클라우드 IAM & 네트워크 보안': [r'\b(?:microsoft\s+)?entra\s+id\b'],
 'Python 프로그래밍 & 비동기 I/O': [r'\bpython\b', r'파이썬', r'\b(?:numpy|pandas|asyncio)\b'],
 '운영체제(OS) & 동시성 제어': [r'operating system', r'오퍼레이팅\s*시스템', r'시스템\s*소프트웨어', r'\b(?:FreeRTOS|RTOS)\b'],
 '객체지향 설계(OOP) & 디자인 패턴': [r'object.oriented', r'design patterns', r'클래스와\s*객체', r'클래스\s*상속',
                              r'객체\s+지향'],
 '마이크로서비스(MSA) 설계': [r'microservices?', r'마이크로\s*서비스'],
 'RESTful API 서버 아키텍처': [r'\bREST(?:ful)?\s*API\b', r'RESTful\s*서비스'],
 '멀티스레딩 & 비동기 동시성': [r'멀티\s*(?:쓰레드|스레드|thread)', r'(?:쓰레드|스레드)\s*동기화',
                           r'동시성\s*제어', r'ThreadPool', r'비동기\s*프로그래밍',
                           r'\basync\s*[,/]\s*await\b|\basync\s*/\s*await\b', r'\basyncio\b', r'비동기'],
 '웹 프레임워크 (FastAPI/Django)': [r'파이썬\s*장고', r'장고\s*(?:앱|라우팅)'],
 '컴퓨터 구조 & 메모리 관리': [r'컴퓨터\s*구조', r'computer architecture', r'마이크로프로세서', r'컴퓨터\s*하드웨어',
                         r'\bCPU\s*데이터\s*경로', r'\b(?:SRAM|DRAM)\b', r'제어\s*유닛'],
}

class SkillMatcher:
    def __init__(self, skills, rules=None):
        self.skills = {s['skill_id']:s for s in skills}
        names = {s['name']:s['skill_id'] for s in skills}
        self.patterns = {}
        self.unresolved_rules = []
        for name, patterns in (rules or get_rules_config().get('skill_rules', {})).items():
            canonical = ALIASES.get(name, name)
            sid = names.get(canonical)
            if sid is None:
                self.unresolved_rules.append(name)
                continue
            for pattern in patterns:
                # Full descriptions must not connect unrelated sentences via greedy wildcards.
                pattern = pattern.replace('.*', r'[^\n.!?。]{0,40}?')
                if canonical == 'RDBMS 데이터 모델링' and pattern.startswith('데이터['):
                    pattern = r'데이터\s*모델링'
                # Avoid RAG matching stoRAGe and DAP matching aDAPter.
                if re.fullmatch(r'[A-Za-z]+', pattern):
                    pattern = r'\b' + pattern + r'\b'
                self.patterns.setdefault(sid, []).append(re.compile(pattern, re.IGNORECASE | re.ASCII))
        for name, patterns in TERMS.items():
            if name in names:
                self.patterns.setdefault(names[name], []).extend(re.compile(p,re.IGNORECASE | re.ASCII) for p in patterns)

    def match(self, text):
        text = str(text or '')
        found = {sid: sorted({m.group(0) for p in patterns for m in p.finditer(text)})
                 for sid, patterns in self.patterns.items() if any(p.search(text) for p in patterns)}
        # Ambiguous "design pattern/object" and "normalization" need their IT domain.
        for sid in list(found):
            name = self.skills[sid]['name']
            if name == '객체지향 설계(OOP) & 디자인 패턴' and not re.search(
                    r'\boop\b|프로그래밍|programming|소프트웨어|software|상속|polymorphism|클래스|\bclass\b', text, re.I|re.ASCII):
                del found[sid]
            elif name == 'Python 프로그래밍 & 비동기 I/O' and not re.search(
                    r'\b(?:python|numpy|pandas|asyncio|fastapi|django|flask|pytorch)\b|파이썬|파이토치|장고', text, re.I|re.ASCII):
                del found[sid]
            elif name == '멀티스레딩 & 비동기 동시성' and not re.search(
                    r'(?:멀티|다중)\s*(?:스레드|쓰레드|thread)|(?:스레드|쓰레드)\s*(?:동기화|프로그래밍)|'
                    r'\b(?:threadpool|threading|pthread|asyncio|async|await|mutex)\b|뮤텍스|세마포어|비동기|동시성\s*프로그래밍', text, re.I|re.ASCII):
                del found[sid]
            elif name == '웹 프레임워크 (FastAPI/Django)' and not re.search(
                    r'\b(?:fastapi|django)\b|장고', text, re.I|re.ASCII):
                del found[sid]
            elif name == 'MLOps & 모델 서빙' and not re.search(
                    r'\b(?:mlops|mlflow|kserve|bentoml|tensorflow|pytorch|llm)\b|'
                    r'machine\s*learning|머신\s*러닝|기계\s*학습|딥\s*러닝|학습된\s*모델', text, re.I|re.ASCII):
                del found[sid]
            elif name == 'RDBMS 데이터 모델링' and not re.search(
                    r'데이터\s*모델링|데이터베이스|관계형|정규형|\b(?:rdbms|sql|dasp|dap)\b|database|relational', text, re.I|re.ASCII):
                del found[sid]
            elif name == 'SQL 쿼리 튜닝 & 인덱스 최적화' and not re.search(
                    r'\bsql\b|postgresql|mysql|sql\s*server|관계형\s*데이터베이스|\brdbms\b|\bsqlp\b', text, re.I | re.ASCII):
                del found[sid]
        return found

    def select(self, rows, limit, *, include_unmatched=False):
        # Deterministic coverage across DB skills before filling by source order.
        rows = [r for r in rows if include_unmatched or r.get('matches')]
        if limit == 0:
            limit = len(rows)
        if not rows:
            return []
        chosen, seen = [], set()
        for sid in sorted(self.skills):
            for row in rows:
                key = (row['source'], row['external_key'])
                if sid in row['matches'] and key not in seen:
                    chosen.append(row); seen.add(key); break
            if len(chosen) >= limit: return chosen
        for row in rows:
            key = (row['source'], row['external_key'])
            if key not in seen:
                chosen.append(row); seen.add(key)
                if len(chosen) >= limit: break
        return chosen
