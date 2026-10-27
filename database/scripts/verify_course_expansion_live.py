"""Verify additive writes and reuse existing skill vectors for recommendation smoke checks."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.database.deployment import connect
from src.database.catalog_verification import fingerprints
from src.database.vectors import resource_vectors
from src.shared.catalog_eligibility import eligible_keys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    state=json.loads(args.state.read_text(encoding='utf-8'))
    if state['status']!='completed' or state['processed']!=state['total']:
        raise ValueError('전체 배치 완료 뒤 실행하세요.')
    baseline=json.loads((args.state.parent/'baseline.json').read_text(encoding='utf-8'))
    ids=state['course_ids']
    with connect('SUPABASE_DB_URL') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        assert (conn.info.host,conn.info.port,conn.info.dbname)==('127.0.0.1',55435,'growpath')
        assert len(ids)==len(set(ids))==state['inserted']
        assert fingerprints(conn,ids)==state['before_fingerprints']
        allowed,eligibility=eligible_keys(conn)
        assert all(('courses',rid) in allowed for rid in ids)
        status=resource_vectors.status(conn)
        assert all(v['missing_or_stale_vectors']==0 for v in status['resources'].values())
        counts=conn.execute('''SELECT record_source,count(*) AS n FROM public.courses
                               WHERE course_id=ANY(%s) GROUP BY record_source ORDER BY record_source''',(ids,)).fetchall()
        totals=conn.execute('SELECT count(*) AS n FROM public.courses').fetchone()['n']
        all_sources=conn.execute('SELECT record_source,count(*) AS n FROM public.courses GROUP BY record_source ORDER BY record_source').fetchall()
        vector_count=conn.execute('SELECT count(*) AS n FROM public.learning_resource_embeddings').fetchone()['n']
        new_links=conn.execute('SELECT count(*) AS n FROM public.course_skills WHERE course_id=ANY(%s)',(ids,)).fetchone()['n']
        assert totals==len(baseline['courses'])+len(ids)
        source_count=conn.execute("SELECT count(*) AS n FROM growpath_meta.catalog_api_sources WHERE resource_type='courses' AND entity_key=ANY(%s)",(ids,)).fetchone()['n']
        assert source_count==len(ids)
        schema=conn.execute("SELECT count(*) AS n FROM growpath_meta.schema_migrations").fetchone()['n']
        course_rows=conn.execute('SELECT course_id,title,platform,record_source FROM public.courses WHERE course_id=ANY(%s)',(ids,)).fetchall()
        courses={r['course_id']:r for r in course_rows}
        rows=conn.execute('''SELECT s.skill_id,s.name,c.course_id,c.record_source FROM public.skill_tags s
                            LEFT JOIN public.course_skills cs USING(skill_id)
                            LEFT JOIN public.courses c USING(course_id) ORDER BY s.skill_id,c.course_id''').fetchall()
        coverage=[];searches=[]
        for skill in baseline['skills']:
            sid=skill['skill_id']
            linked={r['course_id'] for r in rows if r['skill_id']==sid and r['course_id'] and ('courses',r['course_id']) in allowed}
            new=linked&set(ids)
            providers={source['record_source']:sum(courses[rid]['record_source']==source['record_source'] for rid in new) for source in counts}
            coverage.append(dict(skill_id=sid,name=skill['name'],recommendable_total=len(linked),new_recommendable=len(new),by_new_source=providers))
            assert linked, 'No recommendable course for skill '+str(sid)
            # The query is an already stored skill vector; no extra question embedding/API call.
            result=conn.execute('''SELECT e.resource_id,1-(e.embedding <=> q.embedding) AS score
                FROM public.learning_resource_embeddings e
                CROSS JOIN (SELECT embedding FROM public.learning_resource_embeddings
                    WHERE resource_type='skills' AND resource_id=%s AND embedding_model=%s) q
                WHERE e.resource_type='courses' AND e.resource_id=ANY(%s) AND e.embedding_model=%s
                ORDER BY e.embedding <=> q.embedding,e.resource_id LIMIT 3''',
                (str(sid),resource_vectors.MODEL,list(new or linked),resource_vectors.MODEL)).fetchall()
            assert result and all(math.isfinite(float(r['score'])) and -1.00001<=float(r['score'])<=1.00001 for r in result)
            searches.append(dict(skill_id=sid,name=skill['name'],query='existing_skill_vector_no_paid_call',
                candidates='new_courses' if new else 'existing_courses',
                top=[dict(course_id=r['resource_id'],title=(courses.get(r['resource_id']) or {}).get('title'),score=float(r['score'])) for r in result]))
        old_actual=sorted(r['course_id'] for r in baseline['courses'] if ('courses',r['course_id']) in allowed)
        assert old_actual==baseline['eligible_course_ids'], 'Existing recommendation eligibility changed'
        audit=conn.execute("SELECT count(*) AS n FROM public.courses WHERE course_id=ANY(%s) AND recruitment_status='CLOSED'",(ids,)).fetchone()['n']
        snapshot=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),reviewed=state['processed'],
            inserted=len(ids),not_inserted_after_review=state['processed']-len(ids),by_new_source=counts,
            previous_courses=len(baseline['courses']),total_courses_and_modules=totals,
            all_course_sources=all_sources,total_resource_vectors=vector_count,new_course_skill_links=new_links,
            previous_recommendable=len(baseline['eligible_course_ids']),recommendable_courses_and_modules=eligibility['courses']['usable'],
            new_auditable_closed_courses=audit,new_source_records=source_count,
            existing_53_table_fingerprints_unchanged=True,existing_recommendation_eligibility_unchanged=True,
            schema_tables=len(state['before_fingerprints']),migration_count=schema,
            vector_status=status,skill_coverage=coverage,recommendation_vector_checks=searches,
            checked_skills=len(searches),query_embedding_api_calls=0,
            ai_usage=state['ai_usage'],ai_judgments_or_reasons_saved=False,
            real_chatbot_ui_test='not_performed',human_review='not_performed')
    args.output.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in snapshot.items() if k not in ('skill_coverage','recommendation_vector_checks','vector_status')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
