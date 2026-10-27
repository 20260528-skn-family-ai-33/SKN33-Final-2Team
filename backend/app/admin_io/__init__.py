"""관리자 데이터 관리(인적·교육): 내려받기 · 미리보기 · 반영 · 이력.

흐름: 올린 파일 → 시트별 행 정리(base.read_upload) → 지금 DB 값과 비교(base.diff) → 데이터별 검사(check)
     → 미리보기 저장(app_ext.admin_uploads · 정리한 행과 계산 결과) → '반영'을 누르면 같은 계산을 다시 해서 미리보기와 같을 때만 한 트랜잭션으로 반영.
화면에서 한 건씩 고치기(edit · 2026-10-22): 고친 칸을 파일의 한 행처럼 만들어 같은 검사·반영을 거친다. 엑셀·CSV는 여러 건을 한꺼번에 고칠 때 쓴다.
규정은 여기서 다루지 않는다(2026-10-26 사용자 결정 · 원문 PDF 올리기·내려받기만, app/regfiles.py). 예전 규정 기록(dataset 'regulations')은 이력에서 보기만 된다.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from .. import db
from ..config import S
from ..errors import ApiError
from . import base, education, hr

DATASETS = {'hr': hr, 'education': education}
PREVIEW_TTL = timedelta(minutes=30)
LOCK = {'hr': 7631001, 'education': 7631003}


def get(ds: str):
    mod = DATASETS.get(ds)
    if not mod:
        raise ApiError(404, 'NO_DATASET', '없는 데이터예요(인적·교육 중에서 골라 주세요)')
    return mod


def sheet_of(mod, name: str) -> base.Sheet:
    sh = next((s for s in mod.SHEETS if s.name == name), None)
    if not sh:
        raise ApiError(404, 'NO_SHEET', f"‘{name}’ 시트가 없어요 ({', '.join(s.name for s in mod.SHEETS)})")
    return sh


def guide(mod) -> list[str]:
    return mod.guide() if hasattr(mod, 'guide') else mod.GUIDE


# ── 보기·내려받기 ──
def rows(ds: str, sheet: str, q: str = '', limit: int = 50, offset: int = 0) -> dict:
    mod = get(ds)
    sh = sheet_of(mod, sheet)
    cur = list(mod.current(sheet).values())
    view = [{c.field: base.show(c, r.get(c.field)) for c in sh.cols} for r in cur]
    if q:
        ql = q.lower()
        view = [v for v in view if any(ql in str(x).lower() for x in v.values())]
    opts = mod.options(sheet) if hasattr(mod, 'options') else {}
    return {'dataset': ds, 'sheet': sheet, 'columns': [{'field': c.field, 'header': c.header, 'readonly': c.readonly, 'key': c.field in sh.key, 'required': c.required,
                                                         'kind': c.kind, 'help': c.help, 'choices': list(c.choices), 'default': base.show(c, c.default),
                                                         'options': opts.get(c.field)} for c in sh.cols],
            'sheetInfo': {'autoKey': sh.auto_key, 'deletable': sh.deletable, 'help': sh.help,
                          'deleteLabel': getattr(mod, 'DELETE_LABEL', {}).get(sheet, '삭제')},
            'total': len(view), 'rows': view[offset:offset + limit]}


def export(ds: str, fmt: str, sheet: str = '', empty: bool = False) -> tuple[bytes, str, str]:
    mod = get(ds)
    stamp = datetime.now().strftime('%Y%m%d')
    if fmt == 'csv':
        sh = sheet_of(mod, sheet or mod.SHEETS[0].name)
        data = [] if empty else list(mod.current(sh.name).values())
        return base.to_csv(sh, data), f"GrowPath_{mod.TITLE}_{sh.name}_{'양식' if empty else stamp}.csv", 'text/csv; charset=utf-8'
    sheets = [sheet_of(mod, sheet)] if sheet else mod.SHEETS
    data = {} if empty else {s.name: list(mod.current(s.name).values()) for s in sheets}
    title = f"GrowPath {mod.TITLE} · {'빈 양식' if empty else datetime.now().strftime('%Y-%m-%d %H:%M') + ' 기준'}"
    return (base.to_xlsx(title, guide(mod), sheets, data), f"GrowPath_{mod.TITLE}_{'양식' if empty else stamp}.xlsx",
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ── 미리보기·반영 ──
def _compute(mod, found: dict[str, list[base.Row]]) -> dict[str, dict]:
    cur = {s.name: mod.current(s.name) for s in mod.SHEETS}
    for name, rs in found.items():
        sh = sheet_of(mod, name)
        for r in rs:
            r.key = tuple(r.values.get(k) for k in sh.key)
        base.diff(sh, rs, cur[name], lambda v, n=name: mod.label(n, v))
    mod.check(found, cur)
    return cur


def _result(found: dict[str, list[base.Row]], notes: list[str]) -> dict:
    errors = sum(1 for rs in found.values() for r in rs if r.errors)
    changes = sum(1 for rs in found.values() for r in rs if r.action in ('add', 'update', 'delete'))
    return {'summary': base.summary(found), 'notes': notes, 'errorRows': errors, 'changeRows': changes, 'canApply': errors == 0 and changes > 0,
            'rows': [r.view() for rs in found.values() for r in rs if r.action not in ('same',)][:2000]}


def preview(ds: str, admin_id: int, file_name: str, raw: bytes, sheet_hint: str | None) -> dict:
    mod = get(ds)
    found, notes = base.read_upload(file_name, raw, mod.SHEETS, sheet_hint)
    _compute(mod, found)
    out = _result(found, notes)
    sha = hashlib.sha256(raw).hexdigest()
    plan = {'states': [r.state() for rs in found.values() for r in rs], 'signature': base.signature(found), 'fileHash': sha, 'view': out['rows']}
    uid = str(db.val("""INSERT INTO app_ext.admin_uploads(admin_id, dataset, file_name, status, summary, plan) VALUES(:a, :d, :f, 'previewed', :s, :p) RETURNING upload_id""",
                     a=admin_id, d=ds, f=file_name[:200], s=db.J({k: out[k] for k in ('summary', 'notes', 'errorRows', 'changeRows', 'canApply')}), p=db.J(plan)))
    # 원본 파일은 서버 폴더에 남긴다(규정 새 버전의 원본 파일 기록 · 배포 때는 파일 저장소)
    folder = S.var_dir / 'uploads' / 'admin'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{uid}.{file_name.rsplit('.', 1)[-1].lower()[:5]}").write_bytes(raw)
    return dict(out, uploadId=uid, dataset=ds, fileName=file_name)


def apply(upload_id: str, admin_id: int, goal_mode: str | None = None) -> dict:
    up = db.one('SELECT * FROM app_ext.admin_uploads WHERE upload_id = CAST(:u AS uuid)', u=upload_id)
    if not up:
        raise ApiError(404, 'NO_UPLOAD', '미리보기 기록을 찾을 수 없어요')
    if up['status'] != 'previewed':
        raise ApiError(409, 'UPLOAD_DONE', {'applied': '이미 반영한 파일이에요', 'rejected': '취소한 미리보기예요', 'expired': '시간이 지난 미리보기예요'}.get(up['status'], '반영할 수 없어요'))
    if datetime.now(timezone.utc) - up['created_at'] > PREVIEW_TTL:
        db.val("UPDATE app_ext.admin_uploads SET status = 'expired' WHERE upload_id = CAST(:u AS uuid) RETURNING 1", u=upload_id)
        raise ApiError(409, 'PREVIEW_EXPIRED', '미리보기한 지 30분이 지났어요', '파일을 다시 올려 미리보기를 확인한 뒤 반영해 주세요')
    mod = get(up['dataset'])
    plan = up['plan']
    ext = up['file_name'].rsplit('.', 1)[-1].lower()[:5]
    ctx = {'admin_id': admin_id, 'upload_id': upload_id, 'file_name': up['file_name'], 'file_hash': plan['fileHash'],
           'storage_key': f'var/uploads/admin/{upload_id}.{ext}', 'goal_mode': goal_mode}
    with db.tx() as t:
        t.run('SELECT pg_advisory_xact_lock(:k)', k=LOCK[up['dataset']])  # 같은 데이터를 두 관리자가 동시에 반영하지 않게
        found = base.rows_from_state(plan['states'])
        cur = _compute(mod, found)
        if any(r.errors for rs in found.values() for r in rs):
            raise ApiError(409, 'NOW_INVALID', '미리보기 뒤 데이터가 바뀌어 지금은 오류가 있어요', '파일을 다시 올려 미리보기를 확인해 주세요')
        if json.dumps(base.signature(found), ensure_ascii=False) != json.dumps(plan['signature'], ensure_ascii=False):
            raise ApiError(409, 'STALE_PREVIEW', '미리보기 뒤 데이터가 바뀌었어요', '파일을 다시 올려 바뀐 미리보기를 확인한 뒤 반영해 주세요')
        res = mod.apply(t, found, cur, ctx)
        t.run("UPDATE app_ext.admin_uploads SET status = 'applied', applied_at = now(), summary = summary || :r WHERE upload_id = CAST(:u AS uuid)",
              r=db.J({'applied': {k: v for k, v in res.items() if k != 'goal_ids'}, 'goalCount': len(res.get('goal_ids', []))}), u=upload_id)
    mod.after(res, ctx)
    return {'uploadId': upload_id, 'dataset': up['dataset'], 'applied': {k: v for k, v in res.items() if k != 'goal_ids'}, 'goalCount': len(res.get('goal_ids', []))}


# ── 화면에서 한 건씩 고치기 ──
EDIT_ACT = {'add': '추가', 'update': '수정', 'delete': '삭제'}


def _form_rows(mod, items: list[dict]) -> tuple[dict[str, list[base.Row]], list[tuple[base.Row, bool]]]:
    """화면에서 보낸 행 → 파일의 한 행과 같은 Row. 값은 파일 칸과 같은 글자로 받아 같은 규칙(base.parse)으로 읽는다.
    key 가 있으면 그 행을 고치고(열쇠는 바꾸지 않음), 없으면 새 행. 보낸 칸만 바꾼다(파일에 없는 열은 그대로인 것과 같음)"""
    found: dict[str, list[base.Row]] = {}
    pairs: list[tuple[base.Row, bool]] = []
    for n, it in enumerate(items, 1):
        sh = sheet_of(mod, str(it.get('sheet') or ''))
        orig, vals = it.get('key'), it.get('values') or {}
        r = base.Row(sh.name, n, {}, set(), delete=bool(it.get('delete')))
        for c in sh.cols:
            if c.readonly:
                continue
            if c.field in sh.key:
                raw = (orig or {}).get(c.field) if orig is not None else vals.get(c.field)
            elif c.field in vals and not r.delete:
                raw = vals[c.field]
            else:
                continue
            v, e = base.parse(c, raw)
            if e:
                r.err(c.header, e)
            r.values[c.field] = v
            r.present.add(c.field)
        r.key = tuple(r.values.get(k) for k in sh.key)
        found.setdefault(sh.name, []).append(r)
        pairs.append((r, orig is None))
    return found, pairs


def _intent(mod, pairs: list[tuple[base.Row, bool]]) -> None:
    """새 행으로 보냈는데 같은 열쇠가 있거나, 고치려던 행이 그새 없어졌으면 오류(파일은 열쇠로만 정하지만 화면은 의도가 분명하다)"""
    for r, new in pairs:
        if r.errors:
            continue
        sh = sheet_of(mod, r.sheet)
        name = ' · '.join(sh.col(k).header for k in sh.key)
        if new and r.action in ('update', 'same', 'delete'):
            r.err(name, f'같은 {name}의 행이 이미 있어요. 목록에서 그 행을 골라 고쳐 주세요')
        elif not new and r.action in ('add', 'skip'):
            r.err(name, '지금 데이터에 없는 행이에요. 목록을 새로 불러와 다시 골라 주세요')


def _token(ds: str, found: dict[str, list[base.Row]]) -> str:
    """확인 창에 보여 준 계산 결과. 저장 때 다시 계산한 결과와 같아야 저장한다"""
    return hashlib.sha256(json.dumps([ds, base.signature(found)], ensure_ascii=False, default=str).encode('utf-8')).hexdigest()[:24]


def _check_edit(mod, items: list[dict]) -> tuple[dict[str, list[base.Row]], dict, dict]:
    found, pairs = _form_rows(mod, items)
    cur = _compute(mod, found)
    _intent(mod, pairs)
    return found, cur, _result(found, [])


def edit(ds: str, admin_id: int, items: list, save: bool = False, token: str | None = None, goal_mode: str | None = None) -> dict:
    """save=False: 확인(바뀌는 칸·태그·오류와 token). save=True: 같은 계산을 다시 해서 token 이 같을 때만 한 트랜잭션으로 반영하고 이력을 남긴다"""
    mod = get(ds)
    if not isinstance(items, list) or not items or len(items) > 10 or not all(isinstance(x, dict) for x in items):
        raise ApiError(400, 'BAD_EDIT', '고칠 행을 보내 주세요')
    if not save:
        found, _, out = _check_edit(mod, items)
        return dict(out, dataset=ds, token=_token(ds, found))
    uid = str(uuid.uuid4())
    body = json.dumps({'dataset': ds, 'rows': items}, ensure_ascii=False, default=str).encode('utf-8')
    ctx = {'admin_id': admin_id, 'upload_id': uid, 'file_name': f'화면 수정 {datetime.now():%Y%m%d-%H%M%S}.json', 'file_hash': hashlib.sha256(body).hexdigest(),
           'storage_key': f'var/uploads/admin/{uid}.json', 'goal_mode': goal_mode, 'source': 'form'}
    with db.tx() as t:
        t.run('SELECT pg_advisory_xact_lock(:k)', k=LOCK[ds])
        found, cur, out = _check_edit(mod, items)
        if out['errorRows']:
            raise ApiError(409, 'NOW_INVALID', '확인한 뒤 데이터가 바뀌어 지금은 저장할 수 없어요', '저장을 다시 눌러 바뀐 내용을 확인해 주세요')
        if not out['changeRows']:
            raise ApiError(409, 'NO_CHANGE', '바뀐 내용이 없어요')
        if token != _token(ds, found):
            raise ApiError(409, 'STALE_EDIT', '확인한 뒤 데이터가 바뀌었어요', '저장을 다시 눌러 바뀐 내용을 확인해 주세요')
        res = mod.apply(t, found, cur, ctx)
        applied, goal_n = {k: v for k, v in res.items() if k != 'goal_ids'}, len(res.get('goal_ids', []))
        first = next(r for rs in found.values() for r in rs if r.action in EDIT_ACT)
        more = out['changeRows'] - 1
        act = getattr(mod, 'DELETE_LABEL', {}).get(first.sheet, '삭제') if first.action == 'delete' else EDIT_ACT[first.action]
        name = f"화면에서 {act} · {first.sheet} · {first.label or ' · '.join(str(k) for k in first.key if k not in (None, '')) or '새 행'}{f' 외 {more}건' if more else ''}"
        t.run("""INSERT INTO app_ext.admin_uploads(upload_id, admin_id, dataset, file_name, status, summary, plan, applied_at)
                 VALUES(CAST(:u AS uuid), :a, :d, :f, 'applied', :s, :p, now())""",
              u=uid, a=admin_id, d=ds, f=name[:200],
              s=db.J(dict({k: out[k] for k in ('summary', 'notes', 'errorRows', 'changeRows')}, canApply=False, source='form', applied=applied, goalCount=goal_n)),
              p=db.J({'states': [r.state() for rs in found.values() for r in rs], 'signature': base.signature(found), 'fileHash': ctx['file_hash'], 'view': out['rows']}))
    # 고친 내용은 서버 폴더에 JSON 으로 남긴다(올린 파일을 남기는 것과 같음 · 규정 새 버전의 원본 기록)
    folder = S.var_dir / 'uploads' / 'admin'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{uid}.json').write_bytes(body)
    mod.after(res, ctx)
    return {'uploadId': uid, 'dataset': ds, 'applied': applied, 'goalCount': goal_n, 'rows': out['rows']}


def one(upload_id: str) -> dict:
    """미리보기 다시 보기(새로 고침 뒤)"""
    up = db.one('SELECT * FROM app_ext.admin_uploads WHERE upload_id = CAST(:u AS uuid)', u=upload_id)
    if not up:
        raise ApiError(404, 'NO_UPLOAD', '미리보기 기록을 찾을 수 없어요')
    sm = up['summary'] or {}
    expired = up['status'] == 'previewed' and datetime.now(timezone.utc) - up['created_at'] > PREVIEW_TTL
    return {'uploadId': upload_id, 'dataset': up['dataset'], 'fileName': up['file_name'], 'status': 'expired' if expired else up['status'],
            'summary': sm.get('summary'), 'notes': sm.get('notes', []), 'errorRows': sm.get('errorRows'), 'changeRows': sm.get('changeRows'),
            'canApply': bool(sm.get('canApply')) and up['status'] == 'previewed' and not expired, 'rows': (up['plan'] or {}).get('view', []),
            'applied': sm.get('applied'), 'goalCount': sm.get('goalCount'), 'source': sm.get('source') or 'file', 'createdAt': up['created_at'].strftime('%Y-%m-%d %H:%M')}


def discard(upload_id: str) -> None:
    db.val("UPDATE app_ext.admin_uploads SET status = 'rejected' WHERE upload_id = CAST(:u AS uuid) AND status = 'previewed' RETURNING 1", u=upload_id)


def history(ds: str = '', limit: int = 30) -> list[dict]:
    rows = db.all_("""SELECT u.upload_id, u.dataset, u.file_name, u.status, u.summary, u.created_at, u.applied_at, a.name AS admin_name FROM app_ext.admin_uploads u
                      LEFT JOIN app_ext.admin_accounts a ON a.admin_id = u.admin_id WHERE (:d = '' OR u.dataset = :d) ORDER BY u.created_at DESC LIMIT :l""", d=ds, l=limit)
    return [{'uploadId': str(r['upload_id']), 'dataset': r['dataset'], 'fileName': r['file_name'], 'status': r['status'], 'summary': r['summary'],
             'createdAt': r['created_at'].strftime('%Y-%m-%d %H:%M'), 'appliedAt': r['applied_at'].strftime('%Y-%m-%d %H:%M') if r['applied_at'] else None,
             'admin': r['admin_name']} for r in rows]
