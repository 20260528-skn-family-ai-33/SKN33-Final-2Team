"""Transactional replacement of five IT catalogs from saved official API evidence."""
from collections import Counter
from pathlib import Path
import csv, json
from psycopg import sql
from psycopg.types.json import Jsonb
from src.shared.catalog_scope import POLICY_VERSION, scoped_matches
from src.shared.catalog_eligibility import exclusion_reason
from src.shared.skill_matching import SkillMatcher

TABLES = {"books":("isbn","book_skills"),"courses":("course_id","course_skills"),
          "certifications":("cert_id","certification_skills"),"jobs":("job_id","job_skills"),"majors":("major_id","major_skills")}


def protected_catalog_ids(conn):
    """Keep identities referenced by employee data throughout a catalog reset."""
    protected = {kind: set() for kind in TABLES}
    for kind, table, column in (
            ('jobs', 'employees', 'job_id'),
            ('certifications', 'employee_certifications', 'certification_id'),
            ('majors', 'employee_education_records', 'major_id')):
        rows = conn.execute(f'SELECT DISTINCT {column}::text AS id FROM public.{table} '
                            f'WHERE {column} IS NOT NULL').fetchall()
        protected[kind] = {row['id'] for row in rows}
    return protected


def replace_catalogs(conn, batch, *, embed=False):
    from src.database.vectors import resource_vectors
    if set(batch["rows"]) != set(TABLES) or any(not batch["rows"][kind] for kind in TABLES):
        raise ValueError("All five reviewed catalogs must be nonempty before replacement")
    # The reset path cannot bypass the standard AI admission gate.
    from src.database.ingestion.ai_catalog_filter import AICatalogFilter
    from src.shared.skill_matching import SkillMatcher
    matcher=SkillMatcher(batch['skill_identity'])
    reviewer=AICatalogFilter(batch['skill_identity'])
    reviewed={kind:reviewer.filter(kind,[{**r,'matches':scoped_matches(matcher,r['fields'])} for r in rows])
              for kind,rows in batch['rows'].items()}
    if any(not rows for rows in reviewed.values()):
        raise ValueError('AI 심사 후 비어 있는 분류가 있습니다. 초기화를 중단했습니다.')
    batch={**batch,'rows':reviewed}
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(763250131)")
        conn.execute("SET LOCAL lock_timeout='10s'")
        conn.execute("LOCK TABLE public.skill_tags IN SHARE ROW EXCLUSIVE MODE")
        current=conn.execute("SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id").fetchall()
        if current != batch["skill_identity"]:raise ValueError("Skill identity changed; rebuild reviewed batch")
        matcher=SkillMatcher(current)
        # Preflight every record before touching any catalog row.
        for kind, rows in batch["rows"].items():
            seen=set();pk,_=TABLES[kind]
            for row in rows:
                f=row["fields"];key=str(f[pk])
                if key in seen:raise ValueError("Duplicate catalog ID")
                seen.add(key)
                reason=exclusion_reason(kind,f,row["source"],row["raw"],row["fetched_at"])
                matches=scoped_matches(matcher,f)
                if reason or not matches:raise ValueError("Scope preflight failed: "+(reason or "no_skill_evidence"))
                if not set(row["matches"]) <= set(matches):raise ValueError("Invalid AI skill subset")
        conn.execute("LOCK TABLE "+",".join("public."+t for t in TABLES)+" IN SHARE ROW EXCLUSIVE MODE")
        delete_catalog_rows(conn)
        protected=protected_catalog_ids(conn)
        report={}
        for kind,(pk,mapping) in TABLES.items():
            columns={r["column_name"] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",(kind,)).fetchall()}
            admitted=set()
            for row in batch["rows"][kind]:
                f=dict(row["fields"]);f["content_status"]="ready"
                if not set(f)<=columns:raise ValueError("Unknown catalog fields")
                names=list(f);values=[Jsonb(f[n]) if isinstance(f[n],(dict,list)) else f[n] for n in names]
                query=sql.SQL("INSERT INTO public.{} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
                    sql.Identifier(kind),sql.SQL(',').join(map(sql.Identifier,names)),sql.SQL(',').join(sql.Placeholder() for _ in names),sql.Identifier(pk),
                    sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(n),sql.Identifier(n)) for n in names if n!=pk))
                conn.execute(query,values);key=f[pk];admitted.add(str(key))
                for sid in row["matches"]:
                    conn.execute(sql.SQL("INSERT INTO public.{} ({},skill_id) VALUES (%s,%s)").format(sql.Identifier(mapping),sql.Identifier(pk)),(key,sid))
                conn.execute("""INSERT INTO growpath_meta.catalog_api_sources
                    (resource_type,source,external_key,entity_key,payload,mapping_evidence,fetched_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (resource_type,source,external_key) DO UPDATE SET
                    entity_key=EXCLUDED.entity_key,payload=EXCLUDED.payload,
                    mapping_evidence=EXCLUDED.mapping_evidence,fetched_at=EXCLUDED.fetched_at""",(kind,row["source"],row["external_key"],str(key),Jsonb(row["raw"]),Jsonb(row["matches"]),row["fetched_at"]))
            report[kind]={"ready":len(admitted),"historical_reference_only":len(protected[kind]-admitted)}
        vectors=resource_vectors.embed(conn) if embed else resource_vectors.status(conn)
        from src.shared.catalog_eligibility import eligible_keys
        allowed,_=eligible_keys(conn)
        expected={(kind,str(r['fields'][TABLES[kind][0]])) for kind,rows in batch['rows'].items() for r in rows}
        if allowed!=expected:raise ValueError("Post-reload eligibility mismatch; rollback")
        return {"status":"PASS","policy":POLICY_VERSION,"catalogs":report,"vectors":vectors,
                "skill_ids_preserved":True,"parent_roadmaps_preserved":True,
                "input_provenance":"saved official API payloads; original fetched_at retained"}


def delete_catalog_rows(conn, *, excluded_only=False):
    """Explicit reset clears learning links but retains employee-referenced identities."""
    predicate="content_status IS DISTINCT FROM 'ready'" if excluded_only else 'TRUE'
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(763250131)')
        conn.execute("SET LOCAL lock_timeout='10s'")
        conn.execute('LOCK TABLE '+','.join('public.'+t for t in TABLES)+' IN SHARE ROW EXCLUSIVE MODE')
        # Freeze referencing writes until deletion ends; a newly assigned job
        # must not slip between the protected-ID snapshot and ON DELETE SET NULL.
        conn.execute('''LOCK TABLE public.employees, public.employee_certifications,
            public.employee_education_records, public.roadmap_step_resources IN SHARE MODE''')
        protected = protected_catalog_ids(conn)
        counts={};detached=0
        for kind,(pk,mapping) in TABLES.items():
            kept = list(protected[kind])
            deletable = f'({predicate}) AND NOT ({pk}::text=ANY(%s::text[]))'
            if kind in ('books','courses','certifications'):
                column={'books':'isbn','courses':'course_id','certifications':'certification_id'}[kind]
                detached+=conn.execute(f'DELETE FROM public.roadmap_step_resources WHERE {column} IN (SELECT {pk} FROM public.{kind} WHERE {predicate})').rowcount
            conn.execute(f'DELETE FROM public.{mapping} WHERE {pk} IN (SELECT {pk} FROM public.{kind} WHERE {predicate})')
            conn.execute(f'DELETE FROM public.learning_resource_embeddings WHERE resource_type=%s AND resource_id IN (SELECT {pk}::text FROM public.{kind} WHERE {predicate})',(kind,))
            # Keep the old external-key/ID binding for retained rows so a later
            # collection upserts the same identity rather than allocating a new one.
            conn.execute(f'DELETE FROM growpath_meta.catalog_api_sources WHERE resource_type=%s AND entity_key IN (SELECT {pk}::text FROM public.{kind} WHERE {deletable})',(kind,kept))
            counts[kind]=conn.execute(f'DELETE FROM public.{kind} WHERE {deletable}',(kept,)).rowcount
            conn.execute(f"UPDATE public.{kind} SET content_status='scope_excluded' WHERE ({predicate}) AND {pk}::text=ANY(%s::text[])",(kept,))
        if not excluded_only:conn.execute("DELETE FROM public.learning_resource_embeddings WHERE resource_type='skills'")
        return {'deleted':counts,'removed_resource_associations':detached,'skill_ids_preserved':True,
                'parent_roadmaps_preserved':True,'employee_references_preserved':True,
                'retained_employee_catalog_rows':{kind:len(ids) for kind,ids in protected.items()}}


def reset_skill_catalogs(conn):
    """Explicitly reset learning catalogs; keep rows needed by employee records."""
    return delete_catalog_rows(conn)
