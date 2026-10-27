"""Review a fixed correction plan; --apply refreshes only its approved vectors."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database.catalog_verification import fingerprints
from src.database.course_skill_corrections import apply_corrections, validate_plan
from src.database.deployment import connect
from src.database.vectors.regulation_vectors import MODEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--max-courses', type=int, default=0)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    rows = validate_plan(plan)
    plan_hash = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    if not args.apply:
        print(json.dumps({'status': 'review_only', 'courses': len(rows), 'plan_sha256': plan_hash,
                          'paid_api_calls': 0, 'database_changes': False}))
        return
    if args.approved_plan_sha256 != plan_hash or not 0 < len(rows) <= args.max_courses:
        raise ValueError('Explicit approved plan hash and bounded course count are required')
    folder = args.plan.parent
    destination = folder / 'application_verification.json'
    if destination.exists():
        raise ValueError('Application report exists; preserved. Inspect it before another run.')
    clone = json.loads((folder / 'clone_verification.json').read_text(encoding='utf-8'))
    if not all(clone['checks'].values()):
        raise ValueError('Clone verification has not passed')
    if any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected
           for name, expected in clone['code_sha256'].items()):
        raise ValueError('Code changed after clone verification')
    baseline = json.loads((folder / 'before_fingerprints.json').read_text(encoding='utf-8'))
    requests = []
    with connect('SUPABASE_DB_URL') as conn:
        if (conn.info.host, conn.info.port, conn.info.dbname) != ('127.0.0.1', 55435, 'growpath'):
            raise ValueError('Only the final local database is authorized')
        if fingerprints(conn) != baseline:
            raise ValueError('Live database changed since the review; compare before applying')
        unaffected = fingerprints(conn, [row['course_id'] for row in rows])
        import os
        from openai import OpenAI
        api = OpenAI(api_key=os.environ['OPENAI_API_KEY'], base_url='https://api.openai.com/v1',
                     timeout=45, max_retries=0)
        def create(**kwargs):
            if kwargs['model'] != MODEL or len(kwargs['input']) > args.max_courses:
                raise ValueError('Paid scope exceeded')
            response = api.embeddings.create(**kwargs)
            requests.append({'model': response.model, 'input_count': len(kwargs['input']),
                             'usage': response.usage.model_dump() if response.usage else None})
            return response
        result = apply_corrections(conn, plan, client=SimpleNamespace(embeddings=SimpleNamespace(create=create)))
        after = fingerprints(conn)
        if fingerprints(conn, [row['course_id'] for row in rows]) != unaffected:
            raise ValueError('Unrelated rows changed; correction rolled back')
        changed = [r for r in rows if r['before_skill_ids'] != r['after_skill_ids']]
        readback = []
        for row in rows:
            found = sorted(r['skill_id'] for r in conn.execute(
                'SELECT skill_id FROM public.course_skills WHERE course_id=%s', (row['course_id'],)).fetchall())
            if found != row['after_skill_ids']:
                raise ValueError('Readback mismatch')
            readback.append({'course_id': row['course_id'], 'skill_ids': found})
        result.update(checked_at_utc=datetime.now(timezone.utc).isoformat(), plan_sha256=plan_hash,
                      approval='User explicitly approved refreshing 17 vectors and applying the DB correction',
                      unrelated_links_and_vectors_unchanged=True,
                      readback=readback, api_requests=requests,
                      removed_links=sum(len(set(r['before_skill_ids']) - set(r['after_skill_ids'])) for r in changed),
                      added_links=sum(len(set(r['after_skill_ids']) - set(r['before_skill_ids'])) for r in changed))
    # Reports are written only after the connection context successfully commits.
    (folder / 'after_fingerprints.json').write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding='utf-8')
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'readback'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
