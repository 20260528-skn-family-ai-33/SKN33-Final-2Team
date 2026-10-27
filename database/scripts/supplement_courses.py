"""Default: validate a reviewed supplementary batch without paid calls or DB writes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.deployment import connect
from src.database.ingestion.course_supplement import prepare, insert_catalog_approved
from src.database.ingestion.ai_catalog_filter import AICatalogFilter
from src.database.local_runtime import server_data_directory, DATA


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='유료 AI 심사/임베딩 후 신규 강좌만 원자적으로 추가')
    parser.add_argument('--max-courses', type=int, default=50, help='사용자가 승인한 이번 배치의 최대 강좌 수(최대 2500)')
    parser.add_argument('--result', type=Path, help='건수·사용량·백업 경로만 보존. AI 판정/응답은 기록하지 않음')
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding='utf-8'))
    with connect('SUPABASE_DB_URL') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if (conn.info.host, conn.info.port, conn.info.dbname) != ('127.0.0.1', 55435, 'growpath'):
            raise ValueError('최종 로컬 DB만 지원합니다.')
        if server_data_directory(conn).resolve() != DATA.resolve():
            raise ValueError('다른 DB 클러스터입니다.')
        skills, checked = prepare(conn, rows, max_courses=args.max_courses)
    if not args.apply:
        print(json.dumps({'status': 'prepared', 'courses': len(checked), 'skill_links': sum(len(r['matches']) for r in checked),
                          'database_changes': False, 'paid_api_calls': 0}, ensure_ascii=False, indent=2))
        return 0
    # Run --apply only after the user authorizes this finite paid batch.
    from src.database.portable import backup
    name = 'before_course_supplement_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8] + '.dump'
    path = ROOT / 'data/exports' / name
    backup(path)
    gate = AICatalogFilter(skills)
    approved = gate.filter('courses', checked)
    if not approved:
        raise ValueError('AI 심사를 통과한 신규 강좌가 없습니다. DB는 변경하지 않았습니다.')
    with connect('SUPABASE_DB_URL') as conn:
        result = insert_catalog_approved(conn, approved, skills, max_courses=args.max_courses)
    output = {'status': 'applied', 'backup': str(path.relative_to(ROOT)),
              'reviewed_courses': len(checked), 'admitted_courses': len(approved),
              'ai_usage': gate.usage, **result}
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='course_ids'}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
