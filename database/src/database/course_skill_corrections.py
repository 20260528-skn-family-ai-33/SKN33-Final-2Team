"""Apply explicitly reviewed link deltas and real vectors in one transaction.

No source text or original AI verdict is rewritten. The local reviewed plan records
curriculum evidence and the exact before/after relations, separate from AI admission.
"""
from __future__ import annotations

import hashlib
import json

from src.database.catalog_verification import fingerprints
from src.database.vectors import resource_vectors as rv


def syllabus_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def validate_plan(plan: dict) -> list[dict]:
    rows = plan['corrections']
    ids = [r['course_id'] for r in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError('Empty or duplicate correction targets')
    for row in rows:
        before, after = row['before_skill_ids'], row['after_skill_ids']
        if (before == after or not after or len(after) != len(set(after))
                or len(before) != len(set(before)) or not row.get('reason')
                or not row.get('evidence') or len(row['syllabus_sha256']) != 64):
            raise ValueError('Incomplete reviewed correction: ' + row['course_id'])
    return rows


def apply_corrections(conn, plan: dict, *, client=None) -> dict:
    """Caller authorizes the paid scope; any mismatch/failure rolls back links too."""
    targets = validate_plan(plan)
    expected = {('courses', r['course_id']) for r in targets}
    with conn.transaction():
        conn.execute('SET LOCAL lock_timeout = \'5s\'')
        conn.execute('''LOCK TABLE public.courses, public.course_skills,
            public.learning_resource_embeddings, growpath_meta.catalog_api_sources
            IN SHARE ROW EXCLUSIVE MODE''')
        before = fingerprints(conn)
        original_sources = rv.sources(conn)
        previous = rv.stored(conn)
        if any(not rv.is_current(v, previous.get(k)) for k, v in original_sources.items()):
            raise ValueError('Existing stale vectors: resolve them before this bounded correction')
        states = []
        for row in targets:
            cid = row['course_id']
            course = conn.execute('''SELECT title,syllabus_summary FROM public.courses
                                    WHERE course_id=%s''', (cid,)).fetchone()
            if (not course or course['title'] != row['title']
                    or syllabus_hash(course['syllabus_summary']) != row['syllabus_sha256']):
                raise ValueError('Reviewed source changed: ' + cid)
            links = sorted(r['skill_id'] for r in conn.execute(
                'SELECT skill_id FROM public.course_skills WHERE course_id=%s', (cid,)).fetchall())
            if links == sorted(row['before_skill_ids']):
                states.append('before')
            elif links == sorted(row['after_skill_ids']):
                states.append('after')
            else:
                raise ValueError('Unexpected skill links: ' + cid)
        if set(states) == {'after'}:
            return {'status': 'already_applied', 'courses_changed': 0, 'embedded_count': 0}
        if set(states) != {'before'}:
            raise ValueError('Partially applied plan; review before retrying')
        for row in targets:
            cid = row['course_id']
            for sid in set(row['before_skill_ids']) - set(row['after_skill_ids']):
                conn.execute('DELETE FROM public.course_skills WHERE course_id=%s AND skill_id=%s', (cid, sid))
            for sid in set(row['after_skill_ids']) - set(row['before_skill_ids']):
                conn.execute('INSERT INTO public.course_skills (course_id,skill_id) VALUES (%s,%s)', (cid, sid))
        rows = rv.sources(conn)
        pending = {k for k, v in rows.items() if not rv.is_current(v, previous.get(k))}
        if pending != expected:
            raise ValueError('Embedding targets differ from the reviewed correction scope')
        keys = sorted(expected)
        texts = [rows[k]['text'] for k in keys]
        vectors = rv.embed_texts(texts, client=client)
        for key, vector in zip(keys, vectors):
            changed = conn.execute(f'''UPDATE {rv.TABLE} SET input_sha256=%s,
                input_version=%s,dimensions=%s,embedding=%s::vector,updated_at=now()
                WHERE resource_type=%s AND resource_id=%s AND embedding_model=%s''',
                (rows[key]['hash'], rv.INPUT_VERSION, rv.DIMENSIONS, json.dumps(vector), *key, rv.MODEL))
            if changed.rowcount != 1:
                raise ValueError('Expected an existing canonical vector')
        final_rows, final_vectors = rv.sources(conn), rv.stored(conn)
        if ({k: v['hash'] for k, v in rows.items()} != {k: v['hash'] for k, v in final_rows.items()}
                or any(not rv.is_current(v, final_vectors.get(k)) for k, v in final_rows.items())):
            raise ValueError('Source drift or stale vectors after correction')
        after = fingerprints(conn)
        changed_tables = {t for t in before if before[t] != after[t]}
        if changed_tables != {'public.course_skills', 'public.learning_resource_embeddings'}:
            raise ValueError('Unexpected table changes')
        return {'status': 'applied', 'courses_changed': len(targets), 'embedded_count': len(keys),
                'changed_tables': sorted(changed_tables), 'source_records_unchanged': True,
                'all_eligible_vectors_current': True, 'original_ai_verdicts_unchanged': True}
