"""규정 원문 PDF (2026-10-26 사용자 결정): 관리자는 규정을 고치지 않고 원문 PDF 를 올리고 내려받기만 한다.

규정은 벡터 DB 를 거친 RAG 에 쓰여서, 관리자가 올린 PDF 는 시스템 관리자(서비스 운영팀)가 내려받아 임베딩·벡터 DB 를 갱신한다.
처리 상태는 두지 않는다(사용자 결정). 운영팀이 DB 를 갱신하면 도우미는 regstore 캐시(5분)가 지난 뒤 새 규정을 쓴다.

- 지금 규정: 팀 DB regulations.regulation_files 의 PDF. storage_key 는 팀 규정 묶음 폴더 기준 상대 경로(source/…/….pdf)라
  그 폴더를 GP5_REGULATION_FILES_DIR 에 둔다.
- 올린 PDF: 서버 폴더 var/uploads/regulations/{upload_id}.pdf 와 app_ext.regulation_uploads(누가·언제·메모).
  잘못 올린 PDF 는 관리자가 지운다: 파일과 기록을 함께 지우고 되돌리지 않는다(2026-10-26 사용자 결정 · 처리 상태가 없어 숨김 기록도 두지 않음).
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from . import db
from .config import S
from .errors import ApiError

UPLOAD_MAX = 20_000_000   # 화면 nginx 의 client_max_body_size(25MB) 안쪽
MEMO_MAX = 500

_CURRENT_SQL = """SELECT DISTINCT ON (r.regulation_id) r.regulation_id, r.name, r.category, m.employee_group, m.overseas_only,
        v.version_label, v.effective_from, f.file_name, f.storage_key
    FROM regulations.regulations r
    JOIN regulations.regulation_versions v ON v.regulation_id = r.regulation_id AND v.availability_status = 'available'
    LEFT JOIN app_ext.regulation_meta m ON m.regulation_id = r.regulation_id
    LEFT JOIN regulations.regulation_files f ON f.regulation_version_id = v.regulation_version_id AND f.file_format = 'pdf'
    ORDER BY r.regulation_id, v.effective_from DESC NULLS LAST, v.version_label DESC, (f.file_role = 'original') DESC NULLS LAST"""


def _upload_dir() -> Path:
    return S.var_dir / 'uploads' / 'regulations'


def _source(storage_key: str | None) -> Path | None:
    """팀 규정 묶음 폴더 안의 원문 파일. 폴더 밖을 가리키거나 파일이 없으면 None"""
    if not storage_key:
        return None
    root = S.regulation_files_dir.resolve()
    p = (root / storage_key).resolve()
    return p if p.is_relative_to(root) and p.is_file() else None


def _current_rows() -> list[dict]:
    # 지금 버전 = 도우미가 쓰는 버전(regstore 와 같은 순서). 규정이 많은 직원 구분부터(일반직 먼저) → 이름 순
    rows = db.all_(_CURRENT_SQL)
    n: dict = {}
    for r in rows:
        n[r['employee_group']] = n.get(r['employee_group'], 0) + 1
    return sorted(rows, key=lambda r: (r['employee_group'] is None, -n[r['employee_group']], r['employee_group'] or '', r['name']))


def current() -> list[dict]:
    out = []
    for r in _current_rows():
        src = _source(r['storage_key'])
        out.append({'id': r['regulation_id'], 'name': r['name'], 'category': r['category'] or '', 'group': r['employee_group'] or '',
                    'overseas': bool(r['overseas_only']), 'version': r['version_label'] or '', 'effective': str(r['effective_from'] or ''),
                    'fileName': r['file_name'] or '', 'size': src.stat().st_size if src else 0, 'available': src is not None})
    return out


def current_pdf(regulation_id: str) -> tuple[bytes, str]:
    r = next((x for x in _current_rows() if x['regulation_id'] == regulation_id), None)
    if not r:
        raise ApiError(404, 'NO_REGULATION', '규정을 찾을 수 없어요', '목록을 새로 불러와 다시 골라 주세요')
    src = _source(r['storage_key'])
    if not src:
        raise ApiError(404, 'NO_PDF', f"「{r['name']}」의 원문 PDF가 서버에 없어요",
                       '서비스 운영팀에 알려 주세요(팀 DB 규정 묶음 폴더를 GP5_REGULATION_FILES_DIR 에 두어야 해요)', kind='config')
    return src.read_bytes(), r['file_name'] or f"{r['name']}.pdf"


def _upload_view(r: dict) -> dict:
    return {'id': str(r['upload_id']), 'fileName': r['file_name'], 'size': r['file_size'], 'memo': r['memo'] or '',
            'admin': r['admin_name'] or '', 'createdAt': r['created_at'].strftime('%Y-%m-%d %H:%M')}


_UPLOAD_SQL = """SELECT u.upload_id, u.file_name, u.file_size, u.memo, u.created_at, a.name AS admin_name FROM app_ext.regulation_uploads u
                 LEFT JOIN app_ext.admin_accounts a ON a.admin_id = u.admin_id"""


def uploads(limit: int = 100) -> list[dict]:
    return [_upload_view(r) for r in db.all_(_UPLOAD_SQL + ' ORDER BY u.created_at DESC LIMIT :l', l=limit)]


def save_upload(admin_id: int, file_name: str, raw: bytes, memo: str) -> dict:
    name = Path((file_name or '').replace('\\', '/')).name.strip()   # 경로째 보내는 브라우저 대비 · 파일 이름만 남긴다
    if not name.lower().endswith('.pdf') or not raw.startswith(b'%PDF-'):
        raise ApiError(400, 'NOT_PDF', 'PDF 파일만 올릴 수 있어요', '규정 원문을 PDF로 저장해 다시 올려 주세요')
    memo = (memo or '').replace('\r\n', '\n').strip()   # 브라우저 폼은 줄바꿈을 CRLF 로 보낸다
    if len(memo) > MEMO_MAX:
        raise ApiError(400, 'MEMO_TOO_LONG', f'메모는 {MEMO_MAX}자까지 적을 수 있어요')
    uid = str(uuid.uuid4())
    folder = _upload_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{uid}.pdf'
    path.write_bytes(raw)
    try:
        db.val("""INSERT INTO app_ext.regulation_uploads(upload_id, admin_id, file_name, file_size, file_sha256, memo)
                  VALUES(CAST(:u AS uuid), :a, :f, :s, :h, :m) RETURNING 1""",
               u=uid, a=admin_id, f=name[:200], s=len(raw), h=hashlib.sha256(raw).hexdigest(), m=memo or None)
    except Exception:
        path.unlink(missing_ok=True)   # 기록 없는 파일을 남기지 않는다
        raise
    return _upload_view(db.one(_UPLOAD_SQL + ' WHERE u.upload_id = CAST(:u AS uuid)', u=uid))


def _upload_id(upload_id: str) -> str:
    try:
        return str(uuid.UUID(upload_id))
    except ValueError:
        raise ApiError(404, 'NO_UPLOAD', '올린 PDF를 찾을 수 없어요') from None


def upload_pdf(upload_id: str) -> tuple[bytes, str]:
    uid = _upload_id(upload_id)
    r = db.one('SELECT file_name FROM app_ext.regulation_uploads WHERE upload_id = CAST(:u AS uuid)', u=uid)
    path = _upload_dir() / f'{uid}.pdf'
    if not r or not path.is_file():
        raise ApiError(404, 'NO_UPLOAD', '올린 PDF를 찾을 수 없어요')
    return path.read_bytes(), r['file_name']


def delete_upload(upload_id: str) -> None:
    """잘못 올린 PDF 지우기: 기록을 먼저 지우고(없으면 404) 파일을 지운다. 운영팀이 이미 받아 반영했다면 벡터 DB 에는 남는다"""
    uid = _upload_id(upload_id)
    if not db.val('DELETE FROM app_ext.regulation_uploads WHERE upload_id = CAST(:u AS uuid) RETURNING 1', u=uid):
        raise ApiError(404, 'NO_UPLOAD', '올린 PDF를 찾을 수 없어요', '이미 지웠을 수 있어요. 목록을 새로 불러와 주세요')
    (_upload_dir() / f'{uid}.pdf').unlink(missing_ok=True)


def overview() -> dict:
    cur = current()
    last = db.one('SELECT count(*) AS n, max(created_at) AS at FROM app_ext.regulation_uploads')
    return {'count': len(cur), 'files': sum(1 for x in cur if x['available']), 'uploads': last['n'],
            'lastUpload': last['at'].strftime('%Y-%m-%d %H:%M') if last['at'] else None}
