"""Finite catalog import in recoverable atomic blocks; paid execution requires --apply."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.deployment import connect
from src.database.local_runtime import DATA, server_data_directory
from src.database.catalog_verification import fingerprints
from src.database.ingestion.course_supplement import prepare, insert_approved
from src.database.ingestion.ai_catalog_filter import AICatalogFilter, AIReviewError
from src.database.portable import backup


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.writing')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    temporary.replace(path)


def checked_connection():
    conn = connect('SUPABASE_DB_URL')
    if (conn.info.host, conn.info.port, conn.info.dbname) != ('127.0.0.1', 55435, 'growpath'):
        conn.close(); raise ValueError('최종 로컬 DB만 지원합니다.')
    if server_data_directory(conn).resolve() != DATA.resolve():
        conn.close(); raise ValueError('다른 DB 클러스터입니다.')
    conn.commit()
    return conn


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--max-courses',type=int,default=50)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    rows=json.loads(args.input.read_text(encoding='utf-8'))
    if not 1 <= len(rows) <= args.max_courses <= 2500:
        raise ValueError('후보 수가 사용자가 승인한 범위를 벗어났습니다.')
    sha=hashlib.sha256(args.input.read_bytes()).hexdigest()
    state=json.loads(args.state.read_text(encoding='utf-8')) if args.state.exists() else dict(
        status='not_started',input_sha256=sha,total=len(rows),processed=0,inserted=0,
        course_ids=[],batches=[],ai_usage=dict(completed_requests=0,prompt_tokens=0,completion_tokens=0))
    if state['input_sha256']!=sha or state['total']!=len(rows):
        raise ValueError('진행 기록과 입력이 다릅니다. 자동으로 다시 심사하지 않습니다.')
    with checked_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        remaining=rows[state['processed']:]
        if remaining:
            skills,_=prepare(conn,remaining,max_courses=args.max_courses)
        if state['processed']:
            if fingerprints(conn,state['course_ids']) != state['before_fingerprints']:
                raise ValueError('기존 DB 데이터가 변경되었습니다. 진행 기록을 점검하세요.')
        elif not state.get('before_fingerprints'):
            state['before_fingerprints']=fingerprints(conn)
    if not args.apply:
        print(json.dumps(dict(status='prepared',total=len(rows),remaining=len(remaining),paid_api_calls=0,database_changes=False)))
        return 0
    if not remaining:
        print(json.dumps(dict(status='already_completed',processed=state['processed'],inserted=state['inserted'],paid_api_calls=0)))
        return 0
    if not state.get('backup'):
        name='before_site_expansion_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:8]+'.dump'
        path=ROOT/'data/exports'/name
        backup(path)
        state['backup']=path.relative_to(ROOT).as_posix()
    state['status']='running'
    save(args.state,state)
    for start in range(state['processed'],len(rows),50):
        stop=min(start+50,len(rows))
        with checked_connection() as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            current_skills,checked=prepare(conn,rows[start:stop])
        gate=AICatalogFilter(current_skills)
        stage='ai_review'
        try:
            admitted=gate.filter('courses',checked)
            stage='atomic_insert_and_embedding'
            result=dict(course_ids=[],inserted_courses=0)
            if admitted:
                with checked_connection() as conn:
                    result=insert_approved(conn,admitted,current_skills)
            state['processed']=stop
            state['inserted']+=result['inserted_courses']
            state['course_ids'].extend(result['course_ids'])
            for key,value in gate.usage.items():state['ai_usage'][key]+=value
            # Execution ranges/counts only: no per-candidate AI verdicts/reasons/responses.
            state['batches'].append(dict(start=start,stop=stop,input_count=stop-start,
                inserted=result['inserted_courses'],ai_usage=gate.usage,committed_at_utc=datetime.now(timezone.utc).isoformat()))
            state['status']='completed' if stop==len(rows) else 'running'
            save(args.state,state)
            print(json.dumps(dict(stage='batch_committed',processed=stop,total=len(rows),
                inserted_in_batch=result['inserted_courses'],inserted_total=state['inserted'])),flush=True)
        except Exception as exc:
            state['status']='failed';state['failed_stage']=stage;state['failed_batch_start']=start
            state['failed_error_type']=type(exc).__name__;state['failed_batch_usage']=gate.usage
            save(args.state,state)
            raise
    with checked_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if fingerprints(conn,state['course_ids'])!=state['before_fingerprints']:
            raise ValueError('기존 데이터 보존 검사 실패. 자동 삭제/되돌리기를 하지 않습니다.')
    state['existing_53_tables_unchanged']=True
    save(args.state,state)
    print(json.dumps(dict(status=state['status'],processed=state['processed'],inserted=state['inserted'],
                         ai_usage=state['ai_usage'],existing_53_tables_unchanged=True)),flush=True)
    return 0


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(status='failed',error_type=type(exc).__name__,
              message=str(exc) if isinstance(exc,AIReviewError) else '실행 단계와 진행 기록을 확인하세요. 실패 배치는 롤백되고 완료 배치는 보존됩니다.'),ensure_ascii=False),flush=True)
        raise SystemExit(1)
