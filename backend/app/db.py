"""DB 연결: SQLAlchemy 엔진(연결 풀) 위에서 SQL 문장(text)을 그대로 실행한다.

팀 DB 표는 팀원이 SQL 마이그레이션으로 관리하므로 ORM 모델을 두지 않는다. 결과는 dict 로 돌려준다.
jsonb 열에 넣을 값은 J() 로 감싼다(드라이버가 JSON 으로 보냄).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg.types.json import Jsonb
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from .config import S

if not S.database_url:
    raise SystemExit('DB 설정이 없어요: .env 에 GP5_DB_PASSWORD(로컬 Docker DB) 또는 DATABASE_URL(다른 DB)을 적어 주세요 (.env.example 참고)')

# 화면에 보이는 날짜·시각은 한국 시간(DB 세션 시간대). 저장은 timestamptz 라 시간대와 관계없이 같은 순간이다
engine = create_engine(S.database_url, pool_size=8, max_overflow=8, pool_pre_ping=True, future=True,
                       connect_args={'options': f'-c timezone={S.db_timezone}'})


def J(v: Any) -> Jsonb:
    """jsonb 열에 넣을 값"""
    return Jsonb(v)


def _row(r) -> dict:
    return dict(r._mapping)


class Tx:
    """한 트랜잭션 안에서 쓰는 도우미. all/one/val/run"""

    def __init__(self, conn: Connection):
        self.c = conn

    def all(self, sql: str, **p) -> list[dict]:
        return [_row(r) for r in self.c.execute(text(sql), p)]

    def one(self, sql: str, **p) -> dict | None:
        r = self.c.execute(text(sql), p).first()
        return _row(r) if r is not None else None

    def val(self, sql: str, **p) -> Any:
        r = self.c.execute(text(sql), p).first()
        return r[0] if r is not None else None

    def run(self, sql: str, **p) -> int:
        return self.c.execute(text(sql), p).rowcount

    def actor(self, employee_id: int) -> None:
        """팀 DB 트리거(guard_roadmap_comment)가 읽는 작성자 정보. 이 트랜잭션 안에서만 유효"""
        self.c.execute(text("SELECT set_config('growpath.employee_id', :v, true)"), {'v': str(employee_id)})


@contextmanager
def tx() -> Iterator[Tx]:
    with engine.begin() as conn:
        yield Tx(conn)


def all_(sql: str, **p) -> list[dict]:
    with tx() as t:
        return t.all(sql, **p)


def one(sql: str, **p) -> dict | None:
    with tx() as t:
        return t.one(sql, **p)


def val(sql: str, **p) -> Any:
    with tx() as t:
        return t.val(sql, **p)


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)
