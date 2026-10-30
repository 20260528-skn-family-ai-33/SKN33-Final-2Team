"""목표 후보를 DB 공유 전에 준비한다. 기본은 읽기 전용 점검, 실행은 --apply/--provider가 필요하다."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db, jobs
from app.agents import goals as agent
from app.services import goals, profile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--employee-id', action='append', type=int, required=True)
    parser.add_argument('--max-employees', type=int, default=4)
    parser.add_argument('--provider', choices=('ollama', 'openai', 'mock'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    ids = args.employee_id
    if len(set(ids)) != len(ids) or any(e <= 0 for e in ids) or args.max_employees <= 0 or len(ids) > args.max_employees:
        parser.error('Use distinct positive employee IDs within --max-employees')
    if args.apply and not args.provider:
        parser.error('--apply requires an explicit --provider; check the model/API budget first')
    snapshots = []
    for eid in ids:
        me = profile.view(eid)
        if not me:
            parser.error('An employee ID does not exist; no jobs started')
        run = db.one('SELECT status,profile_hash,source FROM app_ext.goal_suggestion_runs WHERE employee_id=:e', e=eid) or {}
        snapshots.append({'employee_id': eid, 'status': run.get('status') or 'none',
                          'profile_matches': run.get('profile_hash') == goals._hash(agent.goal_input(me)),
                          'stored_candidates': db.val('SELECT count(*) FROM public.employee_recommended_prompts WHERE employee_id=:e', e=eid)})
    if not args.apply:
        print(json.dumps({'mode': 'preview', 'paid_api_calls': 0, 'database_writes': 0, 'employees': snapshots}))
        return 0
    results = []
    for eid in ids:
        jid = goals.request(eid, 'admin-preload', mode=args.provider, only_if_stale=True)
        seen = set()
        while jid and jid not in seen:
            seen.add(jid)
            jobs.wait_result(jid, eid)
            state = goals.get(eid)
            jid = state['jobId'] if state['status'] == 'running' else None
        state = goals.get(eid)
        results.append({'employee_id': eid, 'status': state['status'], 'source': state['source'],
                        'candidates': len(state['candidates']), 'stale': state['stale']})
    print(json.dumps({'mode': 'apply', 'employees': results}))
    return 0 if all(x['status'] in ('ready', 'default') and not x['stale'] for x in results) else 2


if __name__ == '__main__':
    raise SystemExit(main())
