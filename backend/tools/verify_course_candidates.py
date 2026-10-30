"""실행 DB를 읽기 전용으로 사용해 후보·근거·토큰·처리 시간을 검증한다. LLM 호출 없음."""
import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import event
from app import catalog, catalog_budget as budget, db, llm
from app.agents import roadmap as rm


def stats(values):
    values = sorted(values)
    return {'median': round(statistics.median(values), 2), 'p95': round(values[math.ceil(len(values) * .95) - 1], 2),
            'max': round(max(values), 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    @event.listens_for(db.engine, 'begin')
    def readonly(conn):
        conn.exec_driver_sql('SET TRANSACTION READ ONLY')

    started = time.perf_counter()
    records = catalog.items(refresh=True)
    load_ms = (time.perf_counter() - started) * 1000
    goals = ['사내 규정 문서로 RAG 챗봇 만들기', '파이썬으로 업무 데이터 분석 자동화',
             'Docker로 모델 서빙 배포하기', 'SQL로 업무 시스템 데이터 조회 개선',
             '클라우드 API 서버 개발과 모델 배포', 'SQL 정규화와 트랜잭션 격리 수준 적용']
    cases, elapsed = [], []
    for goal in goals:
        for pid in ('A1', 'A2', 'A3'):
            selection = catalog.roadmap_selection([goal], pid)
            assert all(n <= 20 for n in selection.per_skill.values())
            assert len(selection.skills) <= (3 if pid == 'A2' else 5)
            handoff = {'goal': goal, 'prefs': {'weeklyHours': 6, 'deadlineWeeks': 12},
                       'startStage': 1, 'gaps': selection.skills, 'skillNames': selection.skills}
            # 전달부는 goal뿐 아니라 gaps도 검색한다. 집계·발췌 검사도 같은 입력을 사용한다.
            selection = catalog.roadmap_selection([goal] + handoff['gaps'], pid, skill_names=handoff['skillNames'])
            system = rm._sys(pid, rm.R_SYS)
            base = {'handoff': handoff, 'skillTags': catalog.skill_names(), 'previous': None, 'request': None}
            for _ in range(8):
                started = time.perf_counter()
                payload = rm._catalog_payload(pid, base, system)
                elapsed.append((time.perf_counter() - started) * 1000)
            rows = payload['catalog']
            assert payload['skillTags'] == base['skillTags']
            assert len(rows) <= 40
            assert all(row['id'] in records for row in rows)
            assert len({row['id'] for row in rows}) == len(rows)
            if pid == 'A1':
                assert all(row['cost'] == 0 for row in rows)
            if pid == 'A2':
                assert payload['trackGuidance']['maxWeeks'] == 6
                assert len(payload['trackGuidance']['coreSkills']) <= 3
                assert payload['handoff']['prefs']['deadlineWeeks'] == 6
                assert handoff['prefs']['deadlineWeeks'] == 12
            input_tokens = budget.tokens(system) + budget.tokens(payload) + budget.FRAMING_RESERVE
            assert input_tokens <= budget.INPUT_TOKENS
            for row in rows:
                assert all(s in payload['catalogSkillMap'] for s in row['skills'])
                stored = selection.index[row['id']]
                for fragment in row['curriculum']:
                    assert any(fragment[0] == n and fragment[1] in text for n, text, _ in stored['rows'])
                if row.get('content'):
                    assert any(row['content'] in line for line in stored['lines'])
            if rows:
                chosen = rows[-1]['id']
                selected_handoff = dict(handoff, selectedResourceIds=[chosen])
                selected = rm._catalog_payload(pid, dict(base, handoff=selected_handoff), system)
                assert chosen in {r['id'] for r in selected['catalog']}
            cases.append({'goal': goal, 'track': pid, 'skills': len(selection.skills),
                          'per_skill_reviewed': selection.per_skill, 'server_candidates': len(selection.records),
                          'sent': len(rows), 'with_evidence': sum(bool(r.get('content') or r['curriculum']) for r in rows),
                          'catalog_tokens': budget.tokens(rows), 'input_tokens': input_tokens})
    try:
        rm._catalog_payload('A2', {'handoff': {'goal': goals[0], 'prefs': {}}, 'request': '검증요청키 q7z_ ' * 12000}, 'system')
    except llm.LlmError:
        pass
    else:
        raise AssertionError('긴 요청이 차단되지 않음')
    report = {'database_readonly': True, 'model_calls': 0, 'courses': sum(r['type'] == 'course' for r in records.values()),
              'prompt_source': 'database_active_unchanged',
              'cases_passed': len(cases), 'cold_catalog_load_ms': round(load_ms, 2),
              'selection_and_budget_ms': stats(elapsed), 'timing_samples': len(elapsed),
              'tokenizer_revision': budget.TOKENIZER_REVISION, 'tokenizer_sha256': budget.TOKENIZER_SHA256,
              'code_sha256': {name: hashlib.sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
                             for name in ['app/catalog.py', 'app/catalog_candidates.py', 'app/catalog_budget.py', 'app/track_policy.py', 'app/agents/roadmap.py', 'app/services/drafts.py', 'tools/install_track_prompts.py']},
              'long_input_rejected': True, 'cases': cases,
              'limitations': ['실제 LLM 지연·품질 미측정', '동시 접속 부하 검사 아님', '신규 합성 handoff 사용; 프롬프트 출처는 prompt_source 참조']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, ensure_ascii=False, indent=2))
    for row in cases:
        print(json.dumps({k: v for k, v in row.items() if k != 'per_skill_reviewed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
