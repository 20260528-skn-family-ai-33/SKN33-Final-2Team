"""동시에 준비되는 코스가 같은 점검 세대의 스킬별 도서 검색 결과를 사용한다."""
from hashlib import sha256
import json

from app import db
from app.errors import ApiError
from app.services import resource_rag


def search(employee_id: int, project_id: str, generation_id: str, skill: str, query: str,
           ids: list[str], vector, limit: int) -> list[dict]:
    signature = sha256(json.dumps([resource_rag.VERSION, query, sorted(ids), limit],
                                  ensure_ascii=False).encode()).hexdigest()
    owner = dict(e=employee_id, p=project_id, g=generation_id)
    with db.tx() as t:
        # 임베딩을 받은 뒤에만 초안 행을 잠근다. 두 번째 코스는 첫 코스가 저장한 결과를 읽는다.
        draft = t.one("""SELECT draft_choices #> ARRAY['v2Survey','bookSearch',CAST(:skill AS text)] AS entry
            FROM public.projects WHERE project_id=CAST(:p AS uuid) AND employee_id=:e AND status='DRAFTING'
            AND draft_choices #>> '{v2Survey,generationId}'=:g FOR UPDATE""", skill=skill, **owner)
        if draft is None:
            raise ApiError(409, 'RECOMMENDATIONS_CHANGED', '사전 점검이 변경됐어요. 다시 준비해 주세요.')
        entry = draft['entry'] or {}
        if entry.get('signature') == signature:
            return entry['matches']

        rows = resource_rag.search_vectors('books', ids, vector, limit, False, read=t.all)
        if rows:
            # 가격과 표시 정보는 각 요청의 현재 카탈로그에서 읽고, 순위와 유사도만 공유한다.
            rows = [{k: row[k] for k in ('resource_id', 'similarity')} for row in rows]
            t.run("""UPDATE public.projects SET draft_choices=jsonb_set(draft_choices,'{v2Survey,bookSearch}',
                coalesce(draft_choices #> '{v2Survey,bookSearch}','{}'::jsonb) || CAST(:entry AS jsonb))
                WHERE project_id=CAST(:p AS uuid)""", p=project_id,
                  entry=db.J({skill: {'signature': signature, 'matches': rows}}))
        return rows
