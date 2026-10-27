"""Hash table contents without exporting row contents, including protected HR data."""
from psycopg import sql
from src.database.portable import inventory


def fingerprints(conn, added_course_ids=()):
    result = {}
    for name in inventory(conn)['tables']:
        schema, table = name.split('.')
        where, params = '', ()
        if added_course_ids and schema == 'public' and table in ('courses', 'course_skills'):
            where, params = ' WHERE NOT (t.course_id::text=ANY(%s::text[]))', (list(added_course_ids),)
        elif added_course_ids and schema == 'public' and table == 'learning_resource_embeddings':
            where, params = " WHERE NOT (t.resource_type='courses' AND t.resource_id=ANY(%s::text[]))", (list(added_course_ids),)
        elif added_course_ids and schema == 'growpath_meta' and table == 'catalog_api_sources':
            where, params = " WHERE NOT (t.resource_type='courses' AND t.entity_key=ANY(%s::text[]))", (list(added_course_ids),)
        query = sql.SQL("SELECT count(*) AS rows,md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS digest "
                        "FROM (SELECT md5(row_to_json(t)::text) AS h FROM {}.{} t" + where + ') q').format(
                            sql.Identifier(schema), sql.Identifier(table))
        result[name] = dict(conn.execute(query, params).fetchone())
    return result
