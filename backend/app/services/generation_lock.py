"""프로세스·컨테이너 간 생성 중복 방지. 모델 호출 중 업무 행 잠금은 잡지 않는다."""
from contextlib import contextmanager
from hashlib import blake2b
from uuid import UUID
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app import db
from app.errors import ApiError

# 생성당 전용 세션. 일반 API의 DB 연결 풀을 모델 대기 중 점유하지 않는다.
lock_engine = create_engine(db.engine.url, poolclass=NullPool, connect_args={'connect_timeout': 5})


def lock_key(kind, identifier):
    try:
        identifier = str(UUID(str(identifier)))
    except ValueError:
        identifier = str(identifier)
    return int.from_bytes(blake2b(f'growpath:generation:{kind}:{identifier}'.encode(), digest_size=8).digest(), 'big', signed=True)


@contextmanager
def generation_guard(kind, identifier):
    key = lock_key(kind, identifier)
    with lock_engine.connect() as connection:
        connection = connection.execution_options(isolation_level='AUTOCOMMIT')
        acquired = connection.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}).scalar()
        if not acquired:
            raise ApiError(409, 'GENERATION_BUSY', '같은 초안 또는 로드맵의 생성을 진행 중이에요. 완료 후 다시 확인해 주세요.', retryable=True)
        try:
            yield
        finally:
            # 세션 종료도 잠금을 해제한다. 연결은 풀에 재사용하지 않는다.
            connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})


def generation_running(kind, identifier):
    """잠금을 획득하지 않고 실제 생성 세션의 존재만 확인한다."""
    key=lock_key(kind,identifier) & ((1 << 64)-1)
    return bool(db.val("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory' AND granted AND objsubid=1 AND classid::bigint=:hi AND objid::bigint=:lo AND database=(SELECT oid FROM pg_database WHERE datname=current_database()))",hi=key>>32,lo=key & ((1<<32)-1)))
