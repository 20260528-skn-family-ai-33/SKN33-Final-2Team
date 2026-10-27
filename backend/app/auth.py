"""로그인·세션 (설계서 v1.7 API-01~04, 6.2 인증·권한).

- 직원: 사번 + 비밀번호(팀 DB employees.password_hash · Argon2id). 시연 초기 비밀번호는 .env 의 GP5_DEMO_PASSWORD(기본값 없음 · 저장소에 값을 적지 않는다).
- 관리자: 직원과 별개인 관리자 전용 계정(app_ext.admin_accounts · 2026-10-21 사용자 결정). 로그인 아이디는 사번 자리에 적는다.
- 세션: 쿠키에는 무작위 토큰만 두고, DB(app_ext.sessions)에는 그 SHA-256 만 둔다. 서버를 여러 대 띄워도 같은 세션을 본다.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request, Response

from . import db
from .config import env
from .errors import ApiError

# 같은 PC에서 여러 환경(원본 5차·다른 리팩터링 안)을 한 브라우저로 번갈아 열 때 로그인이 서로 덮이지 않게 쿠키 이름을 설정으로 뺐다(2026-10-26)
COOKIE = env('GP5_SESSION_COOKIE', 'gp5_session')
_ph = PasswordHasher()
KEEP_DAYS, SHORT_HOURS = 30, 12


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(stored: str | None, pw: str) -> bool:
    if not stored:
        return False
    try:
        return _ph.verify(stored, pw)
    except (VerificationError, InvalidHashError):
        return False


@dataclass
class Account:
    type: str  # employee | admin
    id: int
    name: str


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def start_session(resp: Response, account_type: str, account_id: int, keep: bool) -> None:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + (timedelta(days=KEEP_DAYS) if keep else timedelta(hours=SHORT_HOURS))
    with db.tx() as t:
        t.run('DELETE FROM app_ext.sessions WHERE expires_at < now()')
        t.run('INSERT INTO app_ext.sessions(token_hash, account_type, account_id, keep_signed_in, expires_at) VALUES(:h, :t, :i, :k, :e)',
              h=_digest(token), t=account_type, i=account_id, k=keep, e=expires)
    # '로그인 상태 유지'가 아니면 브라우저를 닫을 때 지워지는 쿠키
    resp.set_cookie(COOKIE, token, max_age=KEEP_DAYS * 86400 if keep else None, httponly=True, samesite='lax', path='/')


def end_session(request: Request, resp: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with db.tx() as t:
            t.run('DELETE FROM app_ext.sessions WHERE token_hash = :h', h=_digest(token))
    resp.delete_cookie(COOKIE, path='/')


def account_of(request: Request) -> Account | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db.tx() as t:
        s = t.one('UPDATE app_ext.sessions SET last_seen_at = now() WHERE token_hash = :h AND expires_at > now() RETURNING account_type, account_id', h=_digest(token))
        if not s:
            return None
        if s['account_type'] == 'admin':
            a = t.one('SELECT admin_id, name FROM app_ext.admin_accounts WHERE admin_id = :i AND is_active', i=s['account_id'])
            return Account('admin', a['admin_id'], a['name']) if a else None
        e = t.one("""SELECT e.employee_id, e.name, coalesce(h.account_status, 'active') AS acc, coalesce(h.employment_status, '재직') AS st
                     FROM public.employees e LEFT JOIN app_ext.employee_hr h USING (employee_id) WHERE e.employee_id = :i""", i=s['account_id'])
        if not e or e['acc'] != 'active' or e['st'] != '재직':
            return None
        return Account('employee', e['employee_id'], e['name'])


def require_account(request: Request) -> Account:
    a = account_of(request)
    if not a:
        raise ApiError(401, 'AUTH_REQUIRED', '로그인이 필요해요')
    return a


def require_employee(request: Request) -> Account:
    a = require_account(request)
    if a.type != 'employee':
        raise ApiError(403, 'EMPLOYEE_ONLY', '직원 계정으로 로그인해야 쓸 수 있어요')
    return a


def require_admin(request: Request) -> Account:
    a = require_account(request)
    if a.type != 'admin':
        raise ApiError(403, 'ADMIN_ONLY', '관리자 계정으로 로그인해야 쓸 수 있어요')
    return a


def login(login_id: str, password: str) -> Account:
    """사번(직원) 또는 관리자 아이디. 실패 이유는 구분하지 않고 같은 문구로 알린다"""
    login_id = (login_id or '').strip()
    fail = ApiError(401, 'AUTH_FAILED', '사번 또는 비밀번호가 맞지 않아요')
    if not login_id or not password:
        raise ApiError(400, 'AUTH_MISSING', '사번과 비밀번호를 입력해 주세요')
    with db.tx() as t:
        a = t.one('SELECT admin_id, name, password_hash, is_active FROM app_ext.admin_accounts WHERE login_id = :l', l=login_id)
        if a:
            if not verify_password(a['password_hash'], password):
                raise fail
            if not a['is_active']:
                raise ApiError(403, 'ACCOUNT_INACTIVE', '지금은 쓸 수 없는 계정이에요')
            return Account('admin', a['admin_id'], a['name'])
        rows = t.all("""SELECT e.employee_id, e.name, e.password_hash, coalesce(h.account_status, 'active') AS acc, coalesce(h.employment_status, '재직') AS st
                        FROM public.employees e LEFT JOIN app_ext.employee_hr h USING (employee_id) WHERE e.employee_number = :n""", n=login_id)
    if len(rows) != 1 or not verify_password(rows[0]['password_hash'], password):
        raise fail
    e = rows[0]
    if e['acc'] != 'active' or e['st'] != '재직':
        raise ApiError(403, 'ACCOUNT_INACTIVE', '지금은 쓸 수 없는 계정이에요. 인사 담당 부서(인재경영실 · 가상)에 문의해 주세요')
    return Account('employee', e['employee_id'], e['name'])
