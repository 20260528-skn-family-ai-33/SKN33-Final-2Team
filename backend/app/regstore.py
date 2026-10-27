"""규정 묶음·조항·검색 (팀 DB regulations 스키마 + 보조 스키마 regulation_meta).

- 직원 구분마다 규정 묶음이 있다(regulation_meta.employee_group). 일반직 = 4차 일반직 16건 + 채용 세칙·내부임용시험지침, 실무직 = 실무직 3건.
  국외근무 전용 규정은 국외근무를 묻는 질문에만 넣는다. 맞는 묶음이 없으면 '적용 대상 아님'.
- 검색 단위는 팀 DB 검색 청크(rag_chunks · search_status='active')다. 화면의 '규정 근거'는 청크 하나를 조항처럼 보여 준다
  (조항 청크 = 「규정」 제7조(제목), 별표 행 청크 = 「규정」 별표 1(구분)).
- 검색: 실제 모델 모드(RunPod-Ollama·OpenAI)는 모두 OpenAI 임베딩(text-embedding-3-small) 벡터로 pgvector 코사인 거리를 쓴다
  (팀 합의 2026-10-26 · 팀 DB 벡터가 그 모델로 만들어짐). OpenAI 키가 없으면 키워드로 바꾸지 않고 오류로 알린다(사용자 결정).
  가데이터 모드만 키워드(4차 규칙). 1536차원이면 ERD rag_chunk_embeddings, 아니면 app_ext.rag_chunk_vectors 에 저장한다.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time

from . import db, llm

OVERSEAS = re.compile(r'(국외|해외|외국|주재국|국외사무소)\s*(근무|파견|사무소|주재|발령)|국외근무')
_lock = threading.Lock()
_cache: dict = {'at': 0.0}
TTL_S = 300
EMBED_TEXT_MAX = 6000
INPUT_VERSION = 'gp5-chunk-text-v1'


def _strip_path(text: str, path: str) -> str:
    t = text or ''
    return t[len(path):].lstrip() if path and t.startswith(path) else t


def _load() -> dict:
    regs = db.all_("""SELECT r.regulation_id, r.name, r.category, m.short_key, m.employee_group, m.overseas_only, coalesce(m.org, '한국수자원공사') AS org,
            v.regulation_version_id, v.version_label, v.amendment_date, v.effective_from,
            (SELECT f.file_name FROM regulations.regulation_files f WHERE f.regulation_version_id = v.regulation_version_id ORDER BY f.is_extraction_source DESC LIMIT 1) AS file_name
        FROM regulations.regulations r
        JOIN app_ext.regulation_meta m ON m.regulation_id = r.regulation_id AND m.search_enabled
        JOIN LATERAL (SELECT * FROM regulations.regulation_versions v WHERE v.regulation_id = r.regulation_id AND v.availability_status = 'available'
                      ORDER BY v.effective_from DESC NULLS LAST, v.version_label DESC LIMIT 1) v ON true
        ORDER BY r.name""")
    by_version = {r['regulation_version_id']: r for r in regs}
    chunks = db.all_(CHUNK_SQL + """
        WHERE c.search_status = 'active' AND c.regulation_version_id = ANY(:v)""", v=list(by_version))
    arts = {c['rag_chunk_id']: art_of(c, by_version[c['regulation_version_id']]) for c in chunks}
    sets: dict[str, dict] = {}
    for r in regs:
        g = sets.setdefault(r['employee_group'], {'group': r['employee_group'], 'org': r['org'], 'regs': []})
        g['regs'].append({'key': r['short_key'], 'id': r['regulation_id'], 'name': r['name'], 'category': r['category'],
                          'rev': f"{r['version_label']}" + (f" 개정 {r['amendment_date']}" if r['amendment_date'] else ''),
                          'effective': str(r['effective_from']) if r['effective_from'] else '', 'file': r['file_name'] or '', 'overseas': r['overseas_only']})
    for g in sets.values():
        g['label'] = f"{g['group']} 규정 {len(g['regs'])}건"
    return {'regs': {r['short_key']: r for r in regs}, 'arts': arts, 'sets': sets}


CHUNK_SQL = """SELECT c.rag_chunk_id, c.regulation_version_id, c.chunk_type, c.context_path, c.chunk_text, c.search_status,
            n.regulation_node_id, n.node_type, n.label, n.title, n.body_text, n.path, n.source_locator, n.display_order,
            p.node_type AS p_type, p.label AS p_label, p.title AS p_title
        FROM regulations.rag_chunks c
        JOIN regulations.rag_chunk_sources s ON s.rag_chunk_id = c.rag_chunk_id AND s.source_role = 'primary'
        JOIN regulations.regulation_nodes n ON n.regulation_node_id = s.regulation_node_id
        LEFT JOIN regulations.regulation_nodes p ON p.regulation_node_id = n.parent_node_id"""


def art_of(c: dict, reg: dict) -> dict:
    """청크 한 행 → 화면·에이전트가 쓰는 조항 {번호·제목·장·쪽·본문}. 긴 조항은 항마다 청크가 나뉘어 있다: 「규정」 제7조 제1항(조 제목)"""
    loc = c['source_locator'] or {}
    pages = loc.get('pdf_pages') or [ln.get('page') for ln in loc.get('lines', [])[:1] if ln.get('page')]
    segs = [x.strip() for x in (c['context_path'] or '').split('>')]
    if c['node_type'] in ('article', 'supplement_article'):
        no, title = c['label'], c['title'] or ''
        text = c['body_text'] or _strip_path(c['chunk_text'], c['context_path'])
    elif c['node_type'] == 'paragraph':
        art_no = c['p_label'] if c['p_type'] == 'article' else next((x for x in segs if re.match(r'^제\d+조', x)), '')
        no, title = f"{art_no} {c['label']}".strip(), (c['p_title'] or '') if c['p_type'] == 'article' else ''
        text = _strip_path(c['chunk_text'], c['context_path'])
    else:
        no = segs[1] if len(segs) > 1 else c['label']
        title = segs[-1] if len(segs) > 2 else (c['title'] or '')
        text = _strip_path(c['chunk_text'], c['context_path'])
    chapter = f"{c['p_label']} {c['p_title'] or ''}".strip() if c['p_type'] == 'chapter' else next((x for x in segs[1:2] if re.match(r'^제\d+장', x)), '')
    return {'id': c['rag_chunk_id'], 'reg': reg['short_key'], 'no': no, 'title': title, 'chapter': chapter,
            'page': pages[0] if pages else None, 'text': text, 'type': c['chunk_type'], 'node': c['regulation_node_id'],
            'path': c['context_path'], 'group': reg['employee_group'], 'overseas': reg['overseas_only']}


def data() -> dict:
    with _lock:
        if time.time() - _cache['at'] > TTL_S:
            _cache.update(_load(), at=time.time())
        return _cache


def invalidate() -> None:
    with _lock:
        _cache['at'] = 0.0


def set_for(group: str | None) -> dict | None:
    return data()['sets'].get(group or '')


def groups() -> list[str]:
    return list(data()['sets'])


def article(aid: str) -> dict | None:
    return data()['arts'].get(aid)


def reg_public(key: str) -> dict | None:
    r = data()['regs'].get(key)
    if not r:
        return None
    return {'key': key, 'name': r['name'], 'rev': f"{r['version_label']}" + (f" 개정 {r['amendment_date']}" if r['amendment_date'] else ''),
            'effective': str(r['effective_from']) if r['effective_from'] else '', 'overseas': r['overseas_only'], 'group': r['employee_group']}


def _old(ids: list[str]) -> tuple[dict, dict]:
    """지금 버전에 없는 조항(운영팀이 규정을 새 버전으로 바꾸기 전에 확정한 로드맵의 근거 등)을 DB에서 찾아 '이전 버전'으로 보여 준다"""
    rows = db.all_(CHUNK_SQL + """
        WHERE c.rag_chunk_id = ANY(:i)""", i=ids)
    if not rows:
        return {}, {}
    regs = {r['regulation_version_id']: r for r in db.all_("""SELECT v.regulation_version_id, v.version_label, v.amendment_date, v.effective_from, r.regulation_id, r.name, r.category,
            coalesce(m.short_key, 'old-' || left(r.regulation_id, 8)) AS short_key, coalesce(m.employee_group, '') AS employee_group, coalesce(m.overseas_only, false) AS overseas_only
        FROM regulations.regulation_versions v JOIN regulations.regulations r ON r.regulation_id = v.regulation_id
        LEFT JOIN app_ext.regulation_meta m ON m.regulation_id = r.regulation_id WHERE v.regulation_version_id = ANY(:v)""", v=list({x['regulation_version_id'] for x in rows}))}
    arts, out_regs = {}, {}
    for c in rows:
        reg = regs.get(c['regulation_version_id'])
        if not reg:
            continue
        a = art_of(c, reg)
        a['old'] = True
        arts[a['id']] = a
        cur = reg_public(reg['short_key'])
        out_regs[reg['short_key']] = dict(cur or {'key': reg['short_key'], 'id': reg['regulation_id'], 'name': reg['name'], 'category': reg['category']},
                                          rev=f"{reg['version_label']}(이전 버전)", effective=str(reg['effective_from'] or ''))
    return arts, out_regs


def bundle(ids) -> dict:
    """화면에 함께 보낼 조항·규정 정보 {articles: {id: …}, regs: {key: …}}. 지금 버전에 없는 조항은 이전 버전으로 찾아 붙인다"""
    ids = [i for i in dict.fromkeys(ids) if i]
    arts = {i: article(i) for i in ids if article(i)}
    regs = {k: reg_public(k) for k in {a['reg'] for a in arts.values()}}
    miss = [i for i in ids if i not in arts]
    if miss:
        old_arts, old_regs = _old(miss)
        arts.update(old_arts)
        for k, v in old_regs.items():
            regs.setdefault(k, v)
    return {'articles': arts, 'regs': regs}


def pool(group: str | None, query: str) -> list[dict]:
    """검색 대상: 내 직원 구분의 규정 청크(국외근무 규정은 국외근무 질문에만). 묶음이 없으면 빈 목록"""
    os_ = bool(OVERSEAS.search(query or ''))
    return [a for a in data()['arts'].values() if a['group'] == group and (os_ or not a['overseas'])]


# ── 키워드 검색 (4차 AI.retrieve) ──
SYN = [
    (r'(출장|여비|교통비|숙박|일비)', ['여비', '출장'], 1), (r'(교육|강의|수강|공부|학습|연수|훈련)', ['교육훈련', '인재개발', '교육', '학습'], 1),
    (r'(근무\s*시간|근무 형태|근무형태|교대|통상|야간|출퇴근)', ['근로자의 종류', '통상근무자', '교대근무자', '근무시간', '통상근무', '복무'], 1),
    (r'(유연|재택|원격|시차)', ['유연근무', '원격근무', '근무시간선택'], 1), (r'(휴직|복직)', ['휴직', '복직'], 1), (r'(휴가|연차|병가|경조)', ['휴가', '연차'], 1),
    (r'(평가|평정|등급)', ['근무성적평정', '평정'], 1), (r'(승진|승급)', ['승진'], 1), (r'(월급|보수|연봉|임금|급여|성과급|수당)', ['보수', '연봉', '수당', '성과급'], 1),
    (r'(전보|부서 이동|파견)', ['전보'], 1), (r'(채용|입사|수습)', ['채용', '수습'], 1), (r'(징계|상벌|경고)', ['상벌', '징계', '경고'], 1),
    (r'(복지|학자금|의료비|경조금)', ['복지후생', '복지'], 1), (r'(퇴직|정년)', ['정년퇴직', '퇴직금', '퇴직'], 1),
    (r'(겸직|부업|외부강의|외부 강의)', ['부업', '겸직', '외부강의'], 1), (r'(전결|결재|승인권)', ['전결', '결재'], 1), (r'(직제|조직|정원)', ['직제', '기구', '정원'], 1),
    (r'(상담|고충|불합리)', ['인사상담', '고충'], 1), (r'(안전|보건)', ['안전보건', '안전'], 1), (r'(재해|보상)', ['재해보상'], 1), (r'(복무|의무)', ['복무', '의무'], 1),
    (r'(괴롭힘)', ['괴롭힘'], 1), (r'(언제|시기|기준일)', ['시기', '기준일'], 2), (r'(점수|배점|등급)', ['점수', '배점', '등급'], 2),
    (r'(누가|평정자|담당)', ['평정자', '담당'], 2), (r'(신청|절차)', ['신청', '절차'], 2),
]


def keyword_search(query: str, k: int, group: str | None) -> list[dict]:
    terms = [(t, w) for pat, ts, w in SYN if re.search(pat, query) for t in ts]
    if not terms or not any(w == 1 for _, w in terms):
        return []

    def hit(a: dict, t: str) -> int:
        return (3 if t in (a['title'] or '') or t in (a['no'] or '') else 0) + (1 if t in a['text'] else 0)

    scored = []
    for a in pool(group, query):
        if not any(w == 1 and hit(a, t) for t, w in terms):
            continue
        scored.append((sum(w * hit(a, t) for t, w in terms), a['type'] == 'article', a['id']))
    scored.sort(key=lambda x: (-x[0], not x[1]))
    return [{'id': i, 'score': s} for s, _, i in scored[:k]]


# ── 임베딩 검색 ──
def _vec(v: list[float]) -> str:
    return '[' + ','.join(f'{x:.7f}' for x in v) + ']'


def _table(dims: int) -> str:
    return 'regulations.rag_chunk_embeddings' if dims == 1536 else 'app_ext.rag_chunk_vectors'


def ensure_vectors(ids: list[str], dims: int) -> int:
    """이 모델의 벡터가 없는 청크만 계산해 저장한다(처음 검색할 때 · 운영팀이 벡터 없이 넣은 조항의 안전망)"""
    model = llm.embed_model()
    table = _table(dims)
    have = {r['rag_chunk_id'] for r in db.all_(f'SELECT rag_chunk_id FROM {table} WHERE embedding_model = :m AND rag_chunk_id = ANY(:i)', m=model, i=ids)}
    miss = [i for i in ids if i not in have]
    done = 0
    for n in range(0, len(miss), 64):
        part = miss[n:n + 64]
        texts = [_embed_text(article(i)) for i in part]
        vecs = llm.embed(texts)
        with db.tx() as t:
            for i, txt, v in zip(part, texts, vecs):
                sha = hashlib.sha256(txt.encode('utf-8')).hexdigest()
                if table == 'regulations.rag_chunk_embeddings':
                    t.run("""INSERT INTO regulations.rag_chunk_embeddings(rag_chunk_id, embedding_model, dimensions, input_version, input_sha256, embedding, created_at, updated_at)
                             VALUES(:i, :m, :d, :iv, :s, CAST(:v AS vector), now(), now()) ON CONFLICT (rag_chunk_id, embedding_model) DO NOTHING""",
                          i=i, m=model, d=len(v), iv=INPUT_VERSION, s=sha, v=_vec(v))
                else:
                    t.run("""INSERT INTO app_ext.rag_chunk_vectors(rag_chunk_id, embedding_model, dimensions, embedding, input_sha256)
                             VALUES(:i, :m, :d, CAST(:v AS vector), :s) ON CONFLICT (rag_chunk_id, embedding_model) DO NOTHING""",
                          i=i, m=model, d=len(v), v=_vec(v), s=sha)
        done += len(part)
    return done


def _embed_text(a: dict) -> str:
    reg = data()['regs'].get(a['reg']) or {}
    return f"「{reg.get('name', '')}」 {a['no']}({a['title']}) {a['chapter']}\n{a['text'][:EMBED_TEXT_MAX]}"


def vector_search(query: str, k: int, group: str | None) -> list[dict]:
    model = llm.embed_model()
    ids = [a['id'] for a in pool(group, query)]
    if not ids:
        return []
    qv = llm.embed([query])[0]   # 키가 없으면 여기서 LlmError (빈 결과로 넘기지 않음)
    ensure_vectors(ids, len(qv))
    table = _table(len(qv))
    rows = db.all_(f"""SELECT rag_chunk_id, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM {table}
                       WHERE embedding_model = :m AND dimensions = :d AND rag_chunk_id = ANY(:i)
                       ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k""", q=_vec(qv), m=model, d=len(qv), i=ids, k=k)
    return [{'id': r['rag_chunk_id'], 'score': round(float(r['score']), 4)} for r in rows]


def search(query: str, k: int, group: str | None, mode: str) -> list[dict]:
    """실제 모델 모드는 벡터(어느 모드든 같은 OpenAI 임베딩), 가데이터는 키워드"""
    if mode in ('ollama', 'openai'):
        return vector_search(query, k, group)
    return keyword_search(query, k, group)


def find_article(reg_name: str, label: str, paragraph: str = '') -> list[str]:
    """(규정 이름, 조 번호[, 항]) → 청크 id 목록. 조항 청크가 있으면 그것, 항으로 나뉜 조항이면 그 항 청크들.
    가데이터 고정 답의 근거를 팀 DB 청크에 잇는 데 쓴다"""
    keyn = re.sub(r'\s', '', reg_name)
    mine = [a for a in data()['arts'].values() if re.sub(r'\s', '', (data()['regs'].get(a['reg']) or {}).get('name', '')) == keyn]
    whole = [a['id'] for a in mine if a['no'] == label and a['type'] in ('article', 'supplement_article')]
    if whole:
        return whole[:1]
    parts = sorted((a for a in mine if a['type'] == 'paragraph' and a['no'].startswith(label + ' ')), key=lambda a: a['path'])
    if paragraph:
        parts = [a for a in parts if a['no'].endswith(' ' + paragraph)]
    return [a['id'] for a in parts]


CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
REF_ART = re.compile(r'제?\s*(\d+)\s*조(?:\s*의\s*(\d+))?')
REF_PARA = re.compile(r'(?:제\s*)?(\d+)\s*항')
REF_ITEM = re.compile(r'(?:제\s*)?(\d+)\s*호')


def _norm(s: str | None) -> str:
    return re.sub(r'[\s「」『』]', '', s or '')


def _circled(text: str, n: int) -> str | None:
    """조 본문에서 n항(①②…) 부분"""
    if not 1 <= n <= len(CIRCLED):
        return None
    i = text.find(CIRCLED[n - 1])
    if i < 0:
        return None
    nxt = [j for j in (text.find(c, i + 1) for c in CIRCLED[n:]) if j > 0]
    return text[i:min(nxt) if nxt else len(text)].strip()


def _item(text: str, n: int) -> str | None:
    """조·항 본문에서 n호(줄 앞의 'n.') 부분"""
    m = re.search(rf'(?m)^\s*{n}\.\s', text)
    if not m:
        return None
    e = re.compile(rf'(?m)^\s*{n + 1}\.\s|[{CIRCLED}]').search(text, m.end())
    return text[m.start():e.start() if e else len(text)].strip()


def explicit_ref(query: str, group: str | None, default_reg: str | None = None) -> dict | None:
    """질문에 규정 이름과 조(항·호) 번호가 있으면 그 조항을 바로 찾는다.
    벡터·키워드 검색은 '제2조 3항' 같은 번호를 뜻으로 찾지 못해, 직접 물은 조항이 답변 근거에 들어가지 않던 문제를 막는다(10/21).
    규정 이름이 없으면 앞 답변의 규정(default_reg · 이어 묻기)으로 찾는다. 내 직원 구분의 규정 묶음 안에서만 찾는다"""
    m = REF_ART.search(query or '')
    if not m:
        return None
    label = f'제{m[1]}조' + (f'의{m[2]}' if m[2] else '')
    after = query[m.end():]
    pm, im = REF_PARA.search(after), REF_ITEM.search(after)
    para, item = (int(pm[1]) if pm else None), (int(im[1]) if im else None)
    regs = (set_for(group) or {}).get('regs') or []
    qn = _norm(query)
    named = sorted((r for r in regs if _norm(r['name']) and _norm(r['name']) in qn), key=lambda r: -len(_norm(r['name'])))
    reg = named[0] if named else next((r for r in regs if r['key'] == default_reg), None) if default_reg else None
    if not reg:
        return None
    ids = find_article(reg['name'], label, f'제{para}항' if para else '')
    if para and not ids:
        ids = find_article(reg['name'], label)
    out = {'reg': reg, 'label': label, 'para': para, 'item': item, 'ids': ids[:6], 'where': label, 'focus': None, 'note': ''}
    if not ids:
        out['note'] = f"「{reg['name']}」에서 {label}를 찾지 못했어요"
        return out
    first = article(ids[0])
    full = '\n'.join(article(i)['text'] for i in ids)
    if para:
        if first['type'] == 'paragraph' and first['no'].endswith(f' 제{para}항'):
            out['focus'], out['where'] = first['text'], f'{label} 제{para}항'
        elif (seg := _circled(full, para)):
            out['focus'], out['where'] = seg, f'{label} 제{para}항'
        elif item is None and (seg := _item(full, para)):
            # '제2조 3항'처럼 물었는데 그 조가 항(①②) 없이 호(1. 2.)로만 나뉘어 있으면 그 호를 보여 준다
            out['focus'], out['where'], out['item'] = seg, f'{label} 제{para}호', para
            out['note'] = f'{label}는 항(①②…) 없이 호(1. 2. …)로 나뉘어 있어 제{para}호를 보여 드려요.'
        else:
            out['note'] = f'{label}에서 제{para}항을 찾지 못해 조 전체를 보여 드려요.'
    if item and (not para or out['where'].endswith('항')):
        seg = _item(out['focus'] or full, item)
        if seg:
            out['focus'], out['where'] = seg, f"{out['where']} 제{item}호"
        else:
            out['note'] = f"{out['where']}에서 제{item}호를 찾지 못해 {out['where']} 전체를 보여 드려요."
    return out


def find_annex(reg_name: str, annex: str, contains: str = '') -> str | None:
    keyn = re.sub(r'\s', '', reg_name)
    for a in data()['arts'].values():
        reg = data()['regs'].get(a['reg']) or {}
        if re.sub(r'\s', '', reg.get('name', '')) == keyn and a['no'] == annex and (not contains or contains in (a['path'] or '')):
            return a['id']
    return None
