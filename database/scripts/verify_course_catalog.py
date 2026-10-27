"""Exercise a complete proposed catalog with fake APIs in a disposable DB clone."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from src.database.deployment import connect
from src.database.catalog_verification import fingerprints
from src.database.ingestion.course_supplement import prepare, review, insert_catalog_approved
from src.database.vectors import resource_vectors
from src.shared.catalog_eligibility import eligible_keys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    args=parser.parse_args()
    rows=json.loads(args.input.read_text(encoding='utf-8'))
    clone='growpath_site_expansion_test_'+uuid4().hex[:10]
    with connect('SUPABASE_DB_URL') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        assert (conn.info.host,conn.info.port,conn.info.dbname)==('127.0.0.1',55435,'growpath')
        original=fingerprints(conn)
        params=dict(host=conn.info.host,port=conn.info.port,user=conn.info.user,password=conn.info.password,row_factory=dict_row)
    with psycopg.connect(**params,dbname='postgres',autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE growpath').format(sql.Identifier(clone)))
    passed=[]
    try:
        with psycopg.connect(**params,dbname=clone) as conn:
            before=fingerprints(conn)
            skills,checked=prepare(conn,rows,max_courses=2182)
            fake_ai=MagicMock();fake_embed=MagicMock()
            def answer(**kwargs):
                payload=json.loads(kwargs['messages'][1]['content'])
                value=dict(decision='APPROVE',skill_ids=[payload['candidate_skills'][0]['skill_id']])
                return NS(choices=[NS(finish_reason='stop',message=NS(refusal=None,content=json.dumps(value)))])
            fake_ai.chat.completions.create.side_effect=answer
            approved=review(checked,skills,ai_client=fake_ai)
            assert len(approved)==len(rows)
            passed.append('전체 입력 출처/기간/가격/스킬/중복 검사와 모의 AI의 스킬 축소')
            fake_embed.embeddings.create.side_effect=RuntimeError('injected_embedding_failure')
            try:
                with conn.transaction():
                    insert_catalog_approved(conn,approved,skills,max_courses=2182,embedding_client=fake_embed)
            except RuntimeError as exc:
                assert str(exc)=='injected_embedding_failure'
            else:
                raise AssertionError('Expected vector failure')
            assert fingerprints(conn)==before
            passed.append('전체 입력의 벡터 실패에서 강좌/연결/원문 출처 롤백 및 53표 지문 일치')
            def vector(**kwargs):
                return NS(model=kwargs['model'],data=[NS(index=i,embedding=[1.0]+[0.0]*1535) for i in range(len(kwargs['input']))])
            fake_embed.embeddings.create.side_effect=vector
            with conn.transaction():
                result=insert_catalog_approved(conn,approved,skills,max_courses=2182,embedding_client=fake_embed)
            assert result['inserted_courses']==result['vectors']['embedded_count']==len(rows)
            ids=result['course_ids']
            assert fingerprints(conn,ids)==before
            passed.append('전체 입력 저장/벡터 생성 후 기존 직원/문서/생활안내/벡터 등 53표 보존')
            allowed,_=eligible_keys(conn)
            assert all(('courses',rid) in allowed for rid in ids)
            status=resource_vectors.status(conn)
            assert status['resources']['courses']['missing_or_stale_vectors']==0
            passed.append('신규 전 건 추천 대상 포함 및 현재 벡터 확인')
            for row in approved:
                actual=conn.execute('SELECT skill_id FROM public.course_skills WHERE course_id=%s', (row['fields']['course_id'],)).fetchall()
                assert {r['skill_id'] for r in actual}==set(row['matches'])
            passed.append('AI가 제거한 스킬을 적재 단계에서 복구하지 않음')
            audit_ids=[r['fields']['course_id'] for r in rows if r['fields'].get('recruitment_status')=='CLOSED']
            if audit_ids:
                actual=conn.execute('SELECT count(*) AS n FROM public.courses WHERE course_id=ANY(%s) AND recruitment_status=\'CLOSED\' AND enrollment_end<now()', (audit_ids,)).fetchone()['n']
                assert actual==len(audit_ids)
            passed.append('종료 청강의 CLOSED 상태와 원래 종료일 유지')
            try:prepare(conn,rows,max_courses=2182)
            except ValueError as exc:assert '중복' in str(exc)
            else:raise AssertionError('Duplicate accepted')
            passed.append('동일 배치 재실행은 API 전 중복 차단')
            with conn.transaction():
                conn.execute("DELETE FROM public.learning_resource_embeddings WHERE resource_type='courses' AND resource_id=ANY(%s)",(ids,))
                conn.execute('DELETE FROM public.course_skills WHERE course_id=ANY(%s)',(ids,))
                conn.execute("DELETE FROM growpath_meta.catalog_api_sources WHERE resource_type='courses' AND entity_key=ANY(%s)",(ids,))
                conn.execute('DELETE FROM public.courses WHERE course_id=ANY(%s)',(ids,))
            assert fingerprints(conn)==before
            passed.append('별도 테스트 DB에서 신규 배치만 제거 후 원래 53표 복구')
    finally:
        assert clone.startswith('growpath_site_expansion_test_')
        with psycopg.connect(**params,dbname='postgres',autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(clone)))
    with connect('SUPABASE_DB_URL') as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        assert fingerprints(conn)==original
    output=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),input_count=len(rows),
        passed_count=len(passed),checks=passed,production_db_unchanged=True,clone_removed=True,fake_apis_only=True,paid_api_calls=0)
    args.result.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
