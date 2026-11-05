"""#67: 3,000자 이상 가상 기획서·확정 1~5스킬·3코스의 실제 토크나이저 검증.
모델·DB는 모의하며 실제 저장/모델 품질 검증으로 보고하지 않는다.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import unittest
from app import catalog, catalog_budget as budget
from app.agents import roadmap, runtime, doc, skill_selection, survey_generation
from app.agents.roadmap_generation import generation
from app.agents.roadmap_revision import revision
from app.services import drafts, survey_store, planning_handoff
from app.services.preassessment_flow import checked_skills
from test_catalog_candidates import resource

PROJECT = Path(__file__).with_name('fixtures').joinpath('issue67_virtual_project.md').read_text(encoding='utf-8')
SKILLS = ['RAG & 생성형 AI 에이전트','자연어 처리(NLP) & LLM 기초','ETL & 데이터 파이프라인','RESTful API 서버 아키텍처','MLOps & 모델 서빙']
TAGS = SKILLS + ['SQL 기본 문법 & 조인','SQL 쿼리 튜닝 & 인덱스 최적화','RDBMS 데이터 모델링','NoSQL & 분산 DB','데이터 웨어하우스 & OLAP','탐색적 데이터 분석(EDA) & 전처리','머신러닝 지도/비지도 학습','딥러닝 신경망 아키텍처','PyTorch/TensorFlow 딥러닝 구현','컴퓨터 비전(CV) 모델링','리눅스 환경 및 Bash 스크립팅','TCP/IP 네트워크 프로토콜','클라우드 컴퓨팅 아키텍처 (AWS/Azure)','클라우드 IAM & 네트워크 보안','Docker 컨테이너 가상화','Kubernetes 클러스터 오케스트레이션','CI/CD 배포 자동화 파이프라인','Python 프로그래밍 & 비동기 I/O','자료구조 & 알고리즘 최적화','운영체제(OS) & 동시성 제어','컴퓨터 구조 & 메모리 관리','객체지향 설계(OOP) & 디자인 패턴','대용량 트래픽 처리 & 캐싱','마이크로서비스(MSA) 설계','웹 프레임워크 (FastAPI/Django)','시스템 프로그래밍 & POSIX API','멀티스레딩 & 비동기 동시성','시스템 & OS 보안 강화','웹 애플리케이션 취약점 진단','네트워크 보안 & 침입 탐지','데이터 거버넌스 & 보안 규정 준수']
SUMMARY = {'purpose':'공개 규정의 수집·정제, RAG 검색·생성, 근거 인용 검증, FastAPI와 운영 지표를 연결한 로컬 시제품. 새 모델 학습·직원 계정 연동·외부 운영 배포·결재 연결 제외.',
           'data':'공개 이용이 허용된 PDF·직접 작성한 텍스트 규정·합성 질문. 문서명·발행 주체·개정일·이용 조건·출처·원문 위치·버전·정제 이력 보존. 표·각주는 추출 결과 대조, 불확실한 부분 검토 필요 표시.',
           'tech':'기존 LLM 기반 RAG, ETL 파이프라인, FastAPI 인터페이스와 비동기 작업, 인용 검증 및 오류·토큰·검색/생성 시간 측정. 같은 입력 중복 재사용, 입력 변경 후 늦은 결과 덮어쓰기 방지. 취소 요청과 실제 호출 중단 구분.',
           'schedule':'희망 12주·주당 6시간, 기간은 참고값. 자료 시간을 임의로 줄이지 않으며 평일 설계·읽기, 주말 실습·재현 검사.',
           'constraints':'공개·합성 자료만 사용, 개인정보·비공개 프로젝트 데이터 제출 금지. 유료 호출 사전 승인, 본 검증은 모의 응답. Free는 무료 강좌, 도서 가격 별도 표시. 성과는 실행·메모·제출 여부로 확인하며 첨부 내용 미검증·자기평가와 실제 숙련 구분. 오류·부분 실패·재시도·입력 변경 검증 및 사람 리뷰 필요.'}

class SurveyMemory:
    def __init__(self,draft):self.raw={'gp5':1,'draft':deepcopy(draft)};self.writes=[]
    def one(self,*args,**kwargs):return {'draft_choices':deepcopy(self.raw)}
    def run(self,sql,**params):
        self.writes.append((sql,deepcopy(params)))
        if 'value' in params:self.raw['v2Survey']=json.loads(params['value'])
        if 'draft' in params:self.raw['draft']=json.loads(params['draft'])
        return 1


def scenario(count=5,long_summary=False):
    summary='\n'.join(f'{label}: {SUMMARY[key]}' for key,label in doc.DOC_FIELDS)
    if long_summary:summary=PROJECT
    selected=[{'name':name,'reason':'공개 규정 검색의 근거·입출력 검증 필요','application':f'{name}을 공개 규정 검색의 입력·근거·오류 검증에 적용'} for name in SKILLS[:count]]
    project={'goal':'공개 규정을 수집·정제해 근거 인용을 검증하는 RAG 검색과 FastAPI 조회·운영 지표를 구현하고 싶어요.',
             'projectSummary':summary,'desiredCompetencies':'검색·생성·API·자료 파이프라인·운영의 오류를 재현하고 근거로 검증하는 역량',
             'selectedSkills':deepcopy(selected),'details':{'hours':6,'weeks':12,'budget':0,'etc':'공개·합성 자료만 사용, 새 모델 학습·외부 운영 배포 제외'},
             'projectFile':{'name':'virtual-regulations.md'},'projectSourceHash':hashlib.sha256(PROJECT.encode()).hexdigest()}
    profile={'department':'가상 검증 부서','job':'규정 검색 시제품 검증','education':['가상 컴퓨터공학 전공'],
             'self':{'tech':['Python'], 'certs':[], 'learning':['API 기초'], 'projects':['공개 예제 검색'], 'profile':{'workDesc':'공개 규정의 출처·오류 확인','expSummary':'시제품 검증','devYears':1}}}
    rows=[]
    per=5 if count==1 else 3
    for i,name in enumerate(SKILLS[:count]):
        surveys=[{'text':f'{name}의 공개 문서 검증 항목 {j+1}에서 입력 조건과 판정 근거를 대조할 수 있다.'} for j in range(per)]
        quizzes=[{'q':f'{name} 검증 사례 {j+1}에서 오류 원인을 확인할 방법은?', 'concept':f'{name}의 근거 대조 {j+1}', 'questionType':'오류 원인 판단','difficulty':'적용',
                  'options':['입력과 출력의 근거 위치를 대조한다','호출 수만 늘려 평균 속도를 확인한다','원문 버전 확인 없이 이전 결과를 사용한다','출처 대신 제목 길이로 결과를 평가한다','오류 응답을 성공 응답 합계에 포함한다'],
                  'answer':0,'explain':'입력 문서 버전과 출력의 근거 위치를 비교해야 원인 판단이 가능하다.'} for j in range(per)]
        rows.append({'skill':name,'title':f'공개 문서 흐름 {i+1}을 확인해 볼까요','surveys':surveys,'quizzes':quizzes})
    survey=survey_generation.generate_survey(project,{'skills':selected},profile,lambda *_:{'groups':deepcopy(rows)},require_measurement=True)
    draft=drafts.fresh_draft();draft.update(goal=project['goal'],prefs=deepcopy(project['details']),selectedSkills=deepcopy(selected),project=project['projectFile'],doc={'name':'virtual-regulations.md','status':'ok','text':PROJECT,'summary':summary})
    memory=SurveyMemory(draft)
    value=survey_store.save_generated(memory,1,'synthetic-project',project,{'skills':selected},profile,survey)
    answers={}
    for group in value['survey']['groups']:
        for j,row in enumerate(group['surveys']):answers[row['id']]=2+j%3
        for j,row in enumerate(group['quizzes']):answers[row['id']]=row['answer'] if j%2==0 else (row['answer']+1)%5
    value=survey_store.save_answers(memory,1,'synthetic-project',value['generationId'],answers,complete=True)
    loaded=survey_store.read(memory,1,'synthetic-project')
    assert value==loaded and memory.raw['draft']['doc']['text']==PROJECT
    handoff=planning_handoff.build_handoff(loaded,{'weeklyHours':6,'deadlineWeeks':12,'budgetWon':0},profile)
    return {'saved':loaded,'handoff':handoff,'draft':draft,'memory':memory,'selection':selected,'profile':profile}


def records(names,each=10):
    result={}
    for i,name in enumerate(names):
        for j in range(each):
            rid=f'mock-{i}-{j:02}'
            row=resource(rid,skills=[name],title=f'{name} 공개 규정 검색·출처 검증 실습 {j+1}',cost=0)
            row.update(hours=2+j%6,content=f'{name}: 공개 규정 문서 검색의 근거·출처 검증, 오류 원인 분석, 설계 대안 비교, 성능 측정과 개선 실습',
                       curriculum={'items':[{'title':f'{name} 공개 규정 입력·출처 검증'},{'title':'검색 오류 원인과 근거 대조 실습'},{'title':'API 검증 및 성능 측정·개선 비교'}]})
            result[rid]=row
    return result


def matrix(case):
    h=case['handoff'];before=deepcopy(h);items=records(h['skillOrder']);captured=[]
    mode=''
    def model(ctx,system,payload,**kwargs):
        total=budget.tokens(system)+budget.tokens(payload)+budget.FRAMING_RESERVE
        assert total<=budget.INPUT_TOKENS
        sent=payload['handoff'];assert sent['skillOrder']==h['skillOrder']
        assert len(sent['assessment']['skills'])==len(h['skillOrder'])
        used=[];acts=[]
        for i,name in enumerate(h['skillOrder']):
            code=next(code for code,skill in payload['catalogSkillMap'].items() if skill==name)
            row=next(row for row in payload['catalog'] if code in row['skills'])
            used.append(row['id']);acts.append({'stage':2,'title':name+' 자료 확인','res':row['id'],'hours':row['hours'],'how':'공개 규정 실습을 수행해요. 출처와 결과를 대조해요.','skill':name})
            acts.append({'stage':3,'title':name+' 검증 결과물','res':None,'hours':4,'how':'만들 것: 근거 대조 결과물\n필수 항목: 입력·출력 비교\n제출물: 검증 기록\n평가 기준: 출처 오류 재현','skill':name,'skills':[name]})
        targets=[{'name':name,'application':case['selection'][i]['application'],'targetOutcome':'근거 대조 결과물','completionCriteria':['출처 위치 대조','오류 재현 기록'],'coreOutcome':'최소 기능 결과','coreCriteria':['핵심 동작 확인']} for i,name in enumerate(h['skillOrder'])]
        captured.append({'skills':len(h['skillOrder']),'mode':mode,'course':payload.get('_testCourse'), 'systemTokens':budget.tokens(system),'payloadTokens':budget.tokens(payload), 'totalTokens':total,
                         'catalogCount':len(payload['catalog']),'catalogPerSkill':payload['catalogCounts']['perSkill'],'assessmentTokens':budget.tokens(sent['assessment']),
                         'rawAssessmentTokens':budget.tokens(h['assessment']),'projectSummaryChars':len(h['projectSummary']), 'requiredPresent':not payload.get('previous') or all(a.get('res') in {r['id'] for r in payload['catalog']} for a in payload['previous'].get('acts',[]) if a.get('res'))})
        return {'displayTitle':'공개 규정 근거 검증 시제품','tagline':'공개 자료의 입력과 출처를 검증해요','reason':'선택 스킬의 적용을 연결해요','pros':['근거 확인'],'cons':['모의 검증'], 'scope':'공개 자료 시제품, 실제 운영 배포 제외','weeklyHours':6,'acts':acts,'learningSkills':targets,'summary':'검증 보완','notes':[]}
    def sys(pid,template,*args,**kwargs):return revision(pid) if template is roadmap.REV_SYS else generation(pid)
    with patch.object(catalog,'items',return_value=items),patch.object(catalog,'skill_names',return_value=TAGS),patch.object(roadmap,'_sys',side_effect=sys),patch.object(runtime,'llm_json',side_effect=model),patch.object(runtime,'run',side_effect=lambda ctx,name,task,inp,mock,api,**kw:api(None)):
        for pid in ('A1','A2','A3'):
            ctx=SimpleNamespace(mode='openai');mode='generation'
            first=roadmap.option(ctx,{'pid':pid,'handoff':h});captured[-1]['course']=pid
            mode='regeneration';again=roadmap.option(ctx,{'pid':pid,'handoff':h,'previous':{'acts':first['acts']},'request':{'wish':'출처 검증 결과를 더 명확하게'}});captured[-1]['course']=pid
            plan=roadmap.build_plan(first,{'hours':6,'start':1},h['goal']);mode='revision'
            roadmap.revise(ctx,{'pid':pid,'handoff':h,'plan':plan,'changes':{},'request':'원래 범위를 유지하고 검증 근거 보완'});captured[-1]['course']=pid
            assert [row['name'] for row in again['learningSkills']]==h['skillOrder']
    assert h==before
    return captured


class Issue67ScenarioTests(unittest.TestCase):
    def test_eleven_k_input_and_seven_k_output_fit_twenty_k_context(self):
        self.assertEqual(budget.INPUT_TOKENS,11000)
        self.assertEqual(budget.OUTPUT_RESERVE,7000)
        self.assertLessEqual(budget.INPUT_TOKENS+budget.OUTPUT_RESERVE+budget.CONTEXT_RESERVE,budget.DEFAULT_CONTEXT)
        self.assertEqual(budget.DEFAULT_CONTEXT,20480)

    def test_synthetic_project_and_saved_answers_survive_compaction(self):
        self.assertGreaterEqual(len(PROJECT),3000)
        case=scenario(5)
        self.assertEqual(len(case['saved']['survey']['groups']),5)
        self.assertEqual(len(case['saved']['answers']),30)
        self.assertEqual(case['handoff']['assessment']['groups'],case['saved']['survey']['groups'])
        self.assertEqual(case['handoff']['assessment']['answers'],case['saved']['answers'])
        self.assertEqual(case['saved']['project']['projectSourceHash'],hashlib.sha256(PROJECT.encode()).hexdigest())

    def test_long_project_all_tracks_generation_regeneration_revision_fit(self):
        for count in range(1,6):
            with self.subTest(skills=count):
                rows=matrix(scenario(count,long_summary=True))
                self.assertEqual(len(rows),9)
                self.assertTrue(all(row['requiredPresent'] for row in rows))

    def test_six_skills_are_rejected_instead_of_silently_truncated(self):
        rows=scenario(5)['selection']+[{'name':'SQL 기본 문법 & 조인','application':'조인 검증'}]
        with self.assertRaises(skill_selection.SelectionError):checked_skills(rows,TAGS)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    rows=[]
    for long_summary in (False,True):
        for count in range(1,6):
            packet=scenario(count,long_summary)
            for row in matrix(packet):row['summaryMode']='long' if long_summary else 'structured';rows.append(row)
    out={'mockOnly':True,'inputLimit':budget.INPUT_TOKENS,'outputLimit':budget.OUTPUT_RESERVE,'defaultContext':budget.DEFAULT_CONTEXT,'contextReserve':budget.CONTEXT_RESERVE,'projectChars':len(PROJECT),'tokenizer':'fixed Qwen; runtime JSON serialization; framing reserve 128','rows':rows}
    Path(args.output).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(rows),'projectChars':len(PROJECT),'maxTokens':max(r['totalTokens'] for r in rows),'minCandidates':min(r['catalogCount'] for r in rows),'maxCandidates':max(r['catalogCount'] for r in rows)}))
