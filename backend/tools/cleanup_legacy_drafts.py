"""구형 미확정 초안만 조회·백업·삭제한다. 기본은 조회이며 자동 실행하지 않는다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db

TABLES = ('projects', 'diagnostic_rounds', 'assessment_questions', 'assessment_responses')
ALLOWED_CHILDREN = set(TABLES) | {'roadmaps', 'growth_reports'}
FORMAT = 'legacy-unconfirmed-drafts/v1'


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def legacy(row: dict) -> bool:
    """새 입력 중인 빈 초안과 새 점검 키가 있는 초안은 정리 대상으로 추정하지 않는다."""
    state = row.get('draft_choices')
    if row.get('status') != 'DRAFTING' or not isinstance(state, dict) or state.get('gp5') != 1:
        return False
    if 'v2Survey' in state:
        return False
    draft = state.get('draft')
    if not isinstance(draft, dict):
        return False
    handoff = draft.get('handoff') or {}
    if not isinstance(handoff, dict) or handoff.get('assessmentGenerationId'):
        return False
    quiz = draft.get('quiz') or {}
    return bool(isinstance(quiz, dict) and quiz.get('questions'))


def identity(t) -> dict:
    return t.one("SELECT current_database() AS name, oid::text AS oid FROM pg_database WHERE datname=current_database()")


def protected(t, key: str) -> bool:
    return bool(t.val("""SELECT EXISTS(SELECT 1 FROM public.roadmaps WHERE project_id=CAST(:p AS uuid)
            OR diagnostic_round_id IN (SELECT diagnostic_round_id FROM public.diagnostic_rounds WHERE project_id=CAST(:p AS uuid)))
        OR EXISTS(SELECT 1 FROM public.growth_reports WHERE project_id=CAST(:p AS uuid))
        OR EXISTS(SELECT 1 FROM public.diagnostic_rounds WHERE project_id=CAST(:p AS uuid) AND post_completed_at IS NOT NULL)
        OR EXISTS(SELECT 1 FROM public.assessment_responses WHERE project_id=CAST(:p AS uuid) AND assessment_type='POST')""", p=key))


def rows(t, ids=None, *, lock=False) -> list[dict]:
    where = "project_id=ANY(CAST(:ids AS uuid[]))" if ids is not None else "status='DRAFTING'"
    return [r['data'] for r in t.all(f"SELECT to_jsonb(p) AS data FROM public.projects p WHERE {where} ORDER BY project_id" + (' FOR UPDATE' if lock else ''), ids=ids)]


def inspect(t) -> dict:
    drafts = rows(t)
    candidates = [r for r in drafts if legacy(r) and not protected(t, r['project_id'])]
    return {'database': identity(t), 'drafts': len(drafts), 'candidates': [
        {'project_id': r['project_id'], 'employee_id': r['employee_id'],
         'title': r.get('project_name'), 'sha256': digest(r)} for r in candidates],
        'skipped': len(drafts)-len(candidates)}


def schema_guard(t) -> None:
    # 알 수 없는 cascade 대상을 추정하지 않고 백업 범위 밖 참조가 늘면 중단한다.
    linked = t.all("""SELECT n.nspname AS schema, c.relname AS child FROM pg_constraint k
        JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE k.contype='f' AND k.confrelid IN ('public.projects'::regclass,
            'public.diagnostic_rounds'::regclass,'public.assessment_questions'::regclass,'public.assessment_responses'::regclass)""")
    if any(r['schema'] != 'public' or r['child'] not in ALLOWED_CHILDREN for r in linked):
        raise ValueError('지원하지 않는 관련 테이블이 있습니다. 삭제 전에 백업 범위를 검토하세요.')


def save_backup(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # DB 삭제에 앞서 기존 파일을 덮어쓰지 않고 디스크에 보존한다.
    with path.open('x', encoding='utf-8') as out:
        json.dump(payload, out, ensure_ascii=False, indent=2)
        out.flush()
        os.fsync(out.fileno())


def apply(ids: list[str], backup: Path, expected: dict[str, str]) -> dict:
    keys = list(dict.fromkeys(str(UUID(key)) for key in ids))
    if not keys or set(keys) != set(expected):
        raise ValueError('조회 결과의 정확한 프로젝트 ID와 해시가 필요합니다.')
    with db.tx() as t:
        schema_guard(t)
        current = rows(t, keys, lock=True)
        if {r['project_id'] for r in current} != set(keys):
            raise ValueError('대상 초안이 변경되거나 사라졌습니다. 다시 조회하세요.')
        if any(not legacy(r) or protected(t, r['project_id']) or digest(r) != expected[r['project_id']] for r in current):
            raise ValueError('조회 후 입력·상태가 바뀌었거나 확정 이력·보고서가 있습니다. 삭제하지 않았습니다.')
        snapshot = {'projects': current}
        for table in TABLES[1:]:
            snapshot[table] = [r['data'] for r in t.all(f'SELECT to_jsonb(x) AS data FROM public.{table} x WHERE project_id=ANY(CAST(:ids AS uuid[])) ORDER BY to_jsonb(x)::text', ids=keys)]
        body = {'format': FORMAT, 'database': identity(t), 'created_at': datetime.now(timezone.utc).isoformat(), 'tables': snapshot}
        body['sha256'] = digest(body['tables'])
        save_backup(backup, body)
        deleted = t.all('DELETE FROM public.projects WHERE project_id=ANY(CAST(:ids AS uuid[])) AND status=\'DRAFTING\' RETURNING project_id::text AS id', ids=keys)
        if {r['id'] for r in deleted} != set(keys):
            raise ValueError('삭제 건수가 달라 트랜잭션을 되돌립니다.')
    return {'deleted': len(keys), 'project_ids': keys, 'backup': str(backup), 'backup_sha256': body['sha256']}


def restore(path: Path) -> dict:
    backup = json.loads(path.read_text(encoding='utf-8'))
    if backup.get('format') != FORMAT or set(backup.get('tables') or {}) != set(TABLES) or digest(backup['tables']) != backup.get('sha256'):
        raise ValueError('백업 형식·테이블·해시가 맞지 않습니다.')
    if any(not legacy(row) for row in backup['tables']['projects']):
        raise ValueError('구형 미확정 초안 백업만 복원할 수 있습니다.')
    keys = {row['project_id'] for row in backup['tables']['projects']}
    if any(row.get('project_id') not in keys for table in TABLES[1:] for row in backup['tables'][table]):
        raise ValueError('다른 프로젝트의 관련 기록은 복원하지 않습니다.')
    with db.tx() as t:
        if identity(t) != backup['database']:
            raise ValueError('백업을 만든 DB와 다릅니다. 복원 대상을 확인하세요.')
        for table in TABLES:
            if backup['tables'][table]:
                # 한 행이라도 이미 있거나 FK가 맞지 않으면 전체 복원을 롤백한다.
                t.run(f'INSERT INTO public.{table} SELECT * FROM jsonb_populate_recordset(NULL::public.{table}, :rows)', rows=db.J(backup['tables'][table]))
    return {'restored': len(backup['tables']['projects']), 'backup': str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', type=Path, metavar='REVIEW_JSON', help='먼저 저장한 조회 결과의 ID·행 해시만 정리')
    action.add_argument('--restore', type=Path, metavar='BACKUP_JSON')
    parser.add_argument('--backup', type=Path, help='삭제 전에 새로 작성할 백업 파일')
    parser.add_argument('--output', type=Path, help='조회 결과 저장 경로; 실제 직원 정보가 있으므로 Git 제외')
    args = parser.parse_args()
    if args.restore:
        result = restore(args.restore)
    elif args.apply:
        if not args.backup:
            parser.error('--apply에는 --backup이 필요합니다.')
        review = json.loads(args.apply.read_text(encoding='utf-8'))
        with db.tx() as t:
            if identity(t) != review['database']:
                raise ValueError('조회한 DB와 다릅니다.')
        expected = {r['project_id']: r['sha256'] for r in review['candidates']}
        result = apply(list(expected), args.backup, expected) if expected else {'deleted': 0, 'reason': '조회된 구형 미확정 초안 없음'}
    else:
        with db.tx() as t:
            t.run('SET TRANSACTION READ ONLY')
            result = inspect(t)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
