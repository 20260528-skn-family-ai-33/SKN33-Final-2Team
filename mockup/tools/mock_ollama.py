"""모의 Ollama 서버 (시험용 · 실제 모델 아님)

RunPod-Ollama 를 띄우지 않고 목업의 연결 상태·실패 화면을 확인하려고 Ollama HTTP API 일부를 흉내 낸다.
응답 내용은 정해진 문구('(모의 Ollama)' 표시)이며, 실제 모델 추론·품질 확인으로 쓰면 안 된다.

  GET  /api/version · /api/tags · /api/ps      버전, 설치된 모델, GPU에 올라간 모델
  POST /api/chat · /api/embed                   대화(JSON 응답), 임베딩(해시로 만든 가짜 벡터)
  GET/POST /_scenario                           시나리오 보기·바꾸기 {"name": "...", "reset": true}

시나리오
  ok               정상. 모델이 GPU에 없으면 첫 호출에 2초 걸리고 load_duration 을 돌려준다(첫 호출 지연)
  no-model         설치된 모델이 없음 → 404 "model ... not found, try pulling it first"
  no-roadmap-model 로드맵 모델만 없음
  oom              500 "CUDA error: out of memory"
  slow             응답이 60초 걸림 → server.py 의 OLLAMA_TIMEOUT 을 짧게 두면 시간 초과
  bad-json         JSON 이 아닌 응답
  proxy-502        모든 요청에 RunPod 프록시처럼 HTML 502 (Pod 꺼짐)
  roadmap-partial  로드맵 3안 중 시간 우선안은 메모리 부족, 업무 적용 우선안은 시간 초과, 나머지는 정상

실행: python tools/mock_ollama.py [--port 11436] [--models qwen3.5:9b,growpath-roadmap:9b,bge-m3,qwen2.5vl:7b] [--scenario ok]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

STATE = {'scenario': 'ok', 'models': [], 'loaded': set()}
LOCK = threading.Lock()
SCENARIOS = ('ok', 'no-model', 'no-roadmap-model', 'oom', 'slow', 'bad-json', 'proxy-502', 'roadmap-partial')


def installed() -> list[str]:
    s, ms = STATE['scenario'], STATE['models']
    if s == 'no-model':
        return [m for m in ms if 'embed' in m or m.startswith('bge') or m.startswith('nomic')]
    if s == 'no-roadmap-model':
        return [m for m in ms if 'roadmap' not in m]
    return list(ms)


def ns(sec: float) -> int:
    return int(sec * 1e9)


# ── 과제별 정해진 응답 (입력 JSON 을 조금 반영) ──
def answer(system: str, user: dict) -> dict:
    if '사전 점검 문항을 만든다' in system:
        qs = [('AI 이해', 'LLM의 환각 현상을 알고 있다.', 'LLM 한계 이해'), ('AI 이해', '프롬프트에 예시를 넣어 답변을 조정할 수 있다.', '프롬프트 설계'),
              ('AI 이해', '임베딩이 무엇인지 알고 있다.', '임베딩 이해'), ('개발 경험', 'Python으로 파일을 읽고 쓸 수 있다.', 'Python 기초'),
              ('개발 경험', 'requests로 외부 API를 호출할 수 있다.', '외부 API 호출'), ('개발 경험', 'Git으로 코드를 관리할 수 있다.', 'Git 사용'),
              ('목표 분야', 'RAG가 어떻게 동작하는지 알고 있다.', 'RAG 구조 이해'), ('목표 분야', '벡터DB를 쓸 수 있다.', '벡터DB 사용'),
              ('목표 분야', '문서를 청크로 나눠 검색할 수 있다.', '문서 분할'), ('목표 분야', 'LLM API를 코드에서 호출할 수 있다.', 'LLM API 호출')]
        return {'domain': '(모의) RAG·문서 검색', 'questions': [{'id': f'q{i + 1}', 'area': a, 'text': f'(모의) {t}', 'skill': s} for i, (a, t, s) in enumerate(qs)]}
    cat = [c for c in (user.get('catalog') or []) if c.get('kind') != '자격']
    if '현재 수준을 진단' in system:
        ids = [c['id'] for c in cat if (c.get('stage') or 1) >= 2][:3]
        return {'level': {}, 'startStage': 2, 'startReason': '(모의 Ollama) 개발 기초 경험이 있다고 답해 핵심 이해부터 시작해요.', 'known': ['Python 기초'],
                'gaps': ['RAG 구조 이해', '벡터DB 사용'], 'competencies': ['RAG 구조 이해', '벡터DB로 문서 색인 만들기', '답변 품질 점검'], 'resourceIds': ids,
                'outcome': '(모의 Ollama) 근거를 함께 보여주는 질의응답 시제품', 'handoffNotes': ['(모의) 직접 실습 비중을 높여 주세요']}
    if '로드맵 후보(plans)마다' in system:
        # 안별 지원 조건: 등록 조항만 근거로 쓴다는 규칙을 흉내 내 '관련 자료 미확보'로만 답한다
        return {'plans': [{'pid': x.get('pid'), 'level': 'missing', 'summary': f"(모의 Ollama) {x.get('name')}: 교육비 지원은 「인재개발규정」 원문이 없어 확인할 수 없어요.",
                           'basis': ['a35'], 'missing': ['인재개발규정']} for x in user.get('plans') or []]}
    if '기획서에 들어 있는 이미지' in system:
        # 비전 모델 흉내: 받은 이미지 수만큼 정해진 설명 (이미지 내용은 보지 않음)
        n = int(user.get('imageCount') or 1)
        return {'images': [{'n': i + 1, 'desc': f'(모의 비전) {i + 1}번 이미지: 시스템 구성도로 보이며 문서 → 검색 → 답변 흐름을 그렸어요.'} for i in range(n)]}
    if '기획서를 읽고' in system:
        text = str(user.get('text') or '')
        return {'purpose': '(모의 Ollama) ' + (text.splitlines()[0][:60] if text else '기획서 목적'), 'data': '(모의) 사내 규정 문서',
                'tech': '(모의) RAG·벡터DB' + (' · 이미지 설명 반영' if user.get('imageNotes') else ''), 'schedule': '기획서에 없음', 'constraints': '(모의) 공개 가능한 문서만 사용'}
    if '수정 요청에 맞게 고친' in system:
        # 수정안: 지금 활동에서 뺄 것은 빼고, 추가할 자료·과제를 넣는다(문장 해석은 하지 않음)
        cur, ch = user.get('current') or {}, user.get('changes') or {}
        rm = {x.get('key') for x in ch.get('removeActs') or []}
        acts = [{k: a.get(k) for k in ('stage', 'title', 'res', 'hours', 'how')} for a in cur.get('acts') or [] if a.get('key') not in rm]
        by_id = {c['id']: c for c in (user.get('catalog') or [])}
        for rid in ch.get('addResources') or []:
            c = by_id.get(rid)
            if c:
                acts.append({'stage': c.get('stage') or 2, 'title': f"{c['title']} 학습", 'res': rid, 'hours': c.get('hours') or 3})
        for t in ch.get('addTasks') or []:
            acts.append({'stage': 3, 'title': f'(모의) {t}', 'res': None, 'hours': 4, 'how': '추가한 과제'})
        wh = ((user.get('handoff') or {}).get('prefs') or {}).get('weeklyHours') or cur.get('weeklyHours') or 4
        return {'summary': '(모의 Ollama) 고른 항목을 반영했어요.', 'notes': ['(모의) 요청 문장은 해석하지 않았어요.'] if user.get('request') else [],
                'tagline': '(모의 Ollama) 수정안', 'reason': '(모의 Ollama) 수정 요청을 반영했어요.', 'pros': ['(모의) 장점'], 'cons': ['(모의) 아쉬운 점'], 'weeklyHours': wh, 'acts': acts}
    if '관점별 하위 에이전트' in system and user.get('request'):
        # 요청을 받아 다시 쓰기: 지금 안에서 뺄 활동만 빼고 나머지는 그대로 (문장 해석은 하지 않음)
        rq, prev = user.get('request') or {}, user.get('previous') or {}
        rm = {x.get('key') for x in rq.get('removeActs') or []}
        acts = [{k: a.get(k) for k in ('stage', 'title', 'res', 'hours')} for a in prev.get('acts') or [] if a.get('key') not in rm]
        return {'summary': '(모의 Ollama) 요청을 반영해 다시 썼어요.', 'notes': ['(모의) 바라는 점 문장은 해석하지 않았어요.'] if rq.get('wish') else [],
                'tagline': prev.get('tagline') or '(모의) 다시 쓴 안', 'reason': '(모의 Ollama) 요청을 반영했어요.', 'pros': ['(모의) 장점'], 'cons': ['(모의) 아쉬운 점'], 'weeklyHours': 5, 'acts': acts}
    if '관점별 하위 에이전트' in system:
        ho = user.get('handoff') or {}
        start = int(ho.get('startStage') or 2)
        pick = [c for c in cat if (c.get('stage') or 1) >= start][:2]
        name = next((n for n in ('비용 우선안', '시간 우선안', '업무 적용 우선안') if n in system), '후보')
        acts = [{'stage': max(start, c.get('stage') or 2), 'title': f"{c['title']} 학습", 'res': c['id'], 'hours': c.get('hours') or 3} for c in pick]
        acts.append({'stage': 3, 'title': '(모의) 작은 예제로 실습 과제 만들기', 'res': None, 'hours': 6, 'how': '배운 내용으로 작은 예제를 직접 만들어요.'})
        # 사용자가 고른 자격(catalog 에 하나만 들어옴)은 4단계에 넣는다
        cert = next((c for c in (user.get('catalog') or []) if c.get('kind') == '자격'), None)
        if cert:
            acts.append({'stage': 4, 'title': f"(모의) {cert['title']} 준비", 'res': cert['id'], 'hours': cert.get('hours') or 20})
        # 주당 학습 시간이 '알아서'(null)면 에이전트가 정한 값(모의: 관점마다 다르게)
        wh = (ho.get('prefs') or {}).get('weeklyHours') or {'비용 우선안': 4, '시간 우선안': 6, '업무 적용 우선안': 5}.get(name, 4)
        return {'tagline': f'(모의 Ollama) {name} 후보', 'reason': f'(모의 Ollama) {name} 관점으로 등록 자료를 골랐어요.', 'pros': ['(모의) 장점'], 'cons': ['(모의) 아쉬운 점'],
                'scope': '(모의) 실행 범위', 'weeklyHours': wh, 'acts': acts}
    if '목표 후보 3개' in system:
        # 목표 후보(4차 묶음 7 · FR-05): 프로필의 담당 업무로 후보를 만든다. 평정이 넘어오면 일부러 이유에 평정을 써서
        # 화면 쪽 장치(평정·점수가 들어간 문장 버리기)를 확인한다
        prof = user.get('profile') or {}
        task = prof.get('task') or '담당 업무'
        c = [{'goal': f'(모의 Ollama) {task}에 생성형 AI를 붙이는 방법을 익히고 싶어요.', 'why': '(모의) 담당 업무를 보고 골랐어요.', 'basis': ['담당 업무']},
             {'goal': f'(모의 Ollama) {task} 자료를 RAG로 검색하는 도구를 만들고 싶어요.', 'why': '(모의) 업무 설명을 보고 골랐어요.', 'basis': ['업무 설명', '없는 항목']},
             {'goal': '(모의 Ollama) 업무 데이터를 AI로 점검하는 역량을 기르고 싶어요.', 'why': '(모의) 기술 스택을 보고 골랐어요.', 'basis': ['기술 스택']}]
        if prof.get('evaluations'):
            c[2]['why'] = '(모의) 평정 결과가 좋아서 어려운 목표를 골랐어요.'
            c.append({'goal': '(모의 Ollama) 평정 점수를 올리는 목표를 세우고 싶어요.', 'why': '(모의) 평정', 'basis': []})
        return {'candidates': c, 'note': '(모의 Ollama) 근거 메모'}
    if '규정 에이전트' in system and '먼저 질문을' in system:
        # 사내 생활 도우미 분류(4차 묶음 7 · NFR-01): 분류와 화면 쪽 장치를 확인하려고 일부러 지어낸 문장을 함께 돌려준다
        q = str(user.get('question') or '')
        arts = [a.get('id') for a in (user.get('articles') or [])]
        if any(k in q for k in ('날씨', '주식', '야구')):
            return {'kind': 'out_of_scope', 'summary': '(모의) 내일은 맑아요', 'basis': []}
        if any(k in q for k in ('통근', '식단', '복지몰')):
            ids = ['shuttle'] if '통근' in q else ['cafeteria'] if '식단' in q else ['welfare']
            return {'kind': 'general', 'source': 'intranet', 'intranet': ids + ['없는메뉴'], 'summary': '(모의) 통근버스는 7시 30분에 출발해요'}
        if '승진' in q:
            return {'kind': 'regulation', 'level': 'ok', 'summary': '(모의) 승진은 평정 90점 이상이면 돼요', 'basis': arts[:1]}
        if '점수' in q:
            return {'kind': 'clarify', 'question': '(모의) 어떤 점수를 물어보신 건가요?', 'options': ['근무성적평정 점수 구성이 궁금해요', '사전 점검 결과를 보고 싶어요']}
    if '규정 에이전트' in system:
        # 사내 생활 도우미(4차 묶음 5): 앞 대화가 몇 턴 넘어왔는지와 받은 조항 id 를 그대로 알려 준다(이어 묻기 확인용)
        hist = user.get('_history') or []
        arts = [a.get('id') for a in (user.get('articles') or [])]
        prev = hist[-1] if hist else ''
        if hist:
            return {'kind': 'regulation', 'level': 'unclear', 'summary': f"(모의 Ollama) 앞 대화 {len(hist)}턴을 받았어요. 직전 질문: {prev}",
                    'apply': f"이번 질문: {user.get('question', '')} · 받은 조항: {', '.join(arts) or '없음'}", 'more': [], 'basis': arts[:1], 'missing': []}
        return {'kind': 'general', 'level': 'general', 'summary': '(모의 Ollama) 시험용 답변이에요.', 'apply': f"앞 대화 없음 · 받은 조항: {', '.join(arts) or '없음'}", 'more': [], 'basis': [], 'missing': []}
    if '결과 보고서' in system:
        return {'good': ['(모의 Ollama) 잘된 점'], 'improve': ['(모의 Ollama) 보완할 점'], 'next': {'goal': '(모의) 다음 로드맵 목표', 'why': '(모의) 이유'}}
    return {'reply': '(모의 Ollama) 알 수 없는 과제예요.'}


class Handler(BaseHTTPRequestHandler):
    server_version = 'MockOllama/0.1'

    def log_message(self, fmt, *args):
        print('  [mock-ollama] ' + (fmt % args))

    def send(self, status: int, data, html: bool = False):
        body = (data if html else json.dumps(data, ensure_ascii=False)).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def proxy_down(self) -> bool:
        if STATE['scenario'] == 'proxy-502' and not self.path.startswith('/_scenario'):
            self.send(502, '<!doctype html><html><body><h1>502 Bad Gateway</h1><p>RunPod proxy: the pod is not running (mock)</p></body></html>', html=True)
            return True
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        if self.proxy_down():
            return
        if path == '/_scenario':
            return self.send(200, {'scenario': STATE['scenario'], 'models': STATE['models'], 'loaded': sorted(STATE['loaded']), 'choices': SCENARIOS})
        if path == '/api/version':
            return self.send(200, {'version': '0.0.0-mock'})
        if path == '/api/tags':
            return self.send(200, {'models': [{'name': m, 'model': m} for m in installed()]})
        if path == '/api/ps':
            return self.send(200, {'models': [{'name': m, 'model': m} for m in sorted(STATE['loaded'])]})
        if path == '/':
            return self.send(200, {'message': 'mock ollama (시험용)', 'scenario': STATE['scenario']})
        return self.send(404, {'error': 'not found'})

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get('Content-Length') or 0)
        data = json.loads(self.rfile.read(n).decode('utf-8') or '{}')
        if path == '/_scenario':
            name = data.get('name', 'ok')
            if name not in SCENARIOS:
                return self.send(400, {'error': f'unknown scenario: {name}', 'choices': SCENARIOS})
            with LOCK:
                STATE['scenario'] = name
                if data.get('reset'):
                    STATE['loaded'].clear()
            return self.send(200, {'scenario': name, 'loaded': sorted(STATE['loaded'])})
        if self.proxy_down():
            return
        model = data.get('model', '')
        if path == '/api/embed':
            if model not in installed():
                return self.send(404, {'error': f'model "{model}" not found, try pulling it first'})
            vec = lambda t: [b / 255 for b in hashlib.sha256(str(t).encode('utf-8')).digest()]  # noqa: E731
            inp = data.get('input')
            return self.send(200, {'model': model, 'embeddings': [vec(t) for t in (inp if isinstance(inp, list) else [inp])]})
        if path != '/api/chat':
            return self.send(404, {'error': 'not found'})
        msgs = data.get('messages') or []
        system = next((m.get('content', '') for m in msgs if m.get('role') == 'system'), '')
        # 여러 턴 대화(사내 생활 도우미)면 마지막 user 메시지가 이번 입력이고, 그 앞 user 메시지는 앞 대화의 질문이다
        users = [m.get('content', '') for m in msgs if m.get('role') == 'user']
        try:
            user = json.loads(users[-1] if users else '{}')
        except ValueError:
            user = {}
        if isinstance(user, dict):
            user['_history'] = users[:-1]
        s = STATE['scenario']
        if model not in installed():
            return self.send(404, {'error': f'model "{model}" not found, try pulling it first'})
        if s == 'oom' or (s == 'roadmap-partial' and '시간 우선안' in system):
            time.sleep(0.8)
            return self.send(500, {'error': 'llama runner process has terminated: CUDA error: out of memory'})
        if s == 'slow' or (s == 'roadmap-partial' and '업무 적용 우선안' in system):
            time.sleep(60)
        t0 = time.perf_counter()
        load = 0.0
        with LOCK:
            cold = model not in STATE['loaded']
        if cold:
            time.sleep(2)
            load = 2.0
            with LOCK:
                STATE['loaded'].add(model)
        time.sleep(0.4)
        content = '로드맵 후보를 정리하면 다음과 같아요: {"tagline": "끝나지 않은' if s == 'bad-json' else json.dumps(answer(system, user), ensure_ascii=False)
        return self.send(200, {'model': model, 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'message': {'role': 'assistant', 'content': content},
                               'done': True, 'total_duration': ns(time.perf_counter() - t0), 'load_duration': ns(load), 'prompt_eval_count': 512, 'eval_count': 256})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=11436)
    ap.add_argument('--models', default='qwen3.5:9b,growpath-roadmap:9b,bge-m3,qwen2.5vl:7b')
    ap.add_argument('--scenario', default='ok', choices=SCENARIOS)
    a = ap.parse_args()
    STATE['models'] = [m.strip() for m in a.models.split(',') if m.strip()]
    STATE['scenario'] = a.scenario
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'모의 Ollama (시험용) · http://127.0.0.1:{a.port}/ · 모델 {", ".join(STATE["models"])} · 시나리오 {a.scenario}')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
