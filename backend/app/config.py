"""설정: 이 폴더의 .env 를 읽고(GP5_ENV_FILE 이 있으면 그 파일로 덮어씀), 같은 이름의 환경변수가 있으면 환경변수를 쓴다.

AWS 등에 올릴 때는 .env 파일 없이 환경변수(DATABASE_URL·키)만 넣으면 된다. 키·비밀번호는 화면(브라우저)으로 보내지 않는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parent.parent


def _read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# GP5_ENV_FILE(모의 Ollama 시험용 등)은 .env 위에 덮어쓴다: DB 주소·비밀번호는 .env 것을 그대로 쓰고 바꿀 값만 적으면 된다
_FILE = dict(_read_env_file(ROOT / '.env'), **(_read_env_file(Path(os.environ['GP5_ENV_FILE'])) if os.environ.get('GP5_ENV_FILE') else {}))


def env(key: str, default: str = '') -> str:
    return os.environ.get(key) or _FILE.get(key) or default


def _local_db_url() -> str:
    """DATABASE_URL 을 비워 두면 docker compose 로컬 DB(GP5_DB_*)에 붙는다 — 비밀번호를 GP5_DB_PASSWORD 한 곳에만 적게"""
    password = env('GP5_DB_PASSWORD')
    if not password:
        return ''
    user, name = quote(env('GP5_DB_USER', 'growpath'), safe=''), env('GP5_DB_NAME', 'growpath')
    return f"postgresql+psycopg://{user}:{quote(password, safe='')}@127.0.0.1:{env('GP5_DB_PORT', '55435')}/{name}"


@dataclass(frozen=True)
class Settings:
    database_url: str
    db_timezone: str
    host: str
    port: int
    demo_password: str
    admin_login: str
    var_dir: Path
    regulation_files_dir: Path
    # OpenAI
    openai_key: str
    openai_model: str
    openai_embed: str
    openai_base: str
    openai_json: bool
    openai_vision: str
    # RunPod-Ollama
    ollama_url: str
    ollama_model: str
    ollama_model_roadmap: str
    ollama_model_regulation: str
    ollama_vision: str
    ollama_key: str
    ollama_timeout: int
    ollama_num_ctx: int
    ollama_keep_alive: str
    ollama_think: bool | None  # None 이면 think 를 보내지 않아 모델 기본값을 따른다

    @property
    def ollama_target(self) -> str:
        host = urlparse(self.ollama_url).hostname or ''
        return 'runpod' if host.endswith('runpod.net') else 'local' if host in ('127.0.0.1', 'localhost', '::1') else 'remote'


def _on_off(key: str) -> bool | None:
    """on/off 설정: 비우면 None. 오타를 기본값으로 넘기지 않게 다른 값이면 시작할 때 멈춘다"""
    v = env(key).lower()
    if v in ('', 'on', 'off'):
        return None if not v else v == 'on'
    raise ValueError(f'{key} 값은 on, off 중 하나이거나 비워 두어야 해요 (지금: {v})')


def load() -> Settings:
    # 모델 이름은 코드에 기본값을 두지 않는다: Pod에 받아 둔 모델만 쓸 수 있으므로 비우면 RunPod-Ollama 모드를 쓸 수 없게 한다
    model = env('OLLAMA_MODEL')
    return Settings(
        database_url=env('DATABASE_URL') or _local_db_url(),
        db_timezone=env('GP5_DB_TIMEZONE', 'Asia/Seoul'),
        host=env('GP5_HOST', '127.0.0.1'),
        port=int(env('GP5_PORT', '8785')),
        # 공개 저장소라 기본값을 두지 않는다(팀 database/RESTORE.md: 공용 기본 비밀번호 없음 · 2026-10-26). 비우면 시연 비밀번호를 쓰는 준비 단계를 건너뛴다
        demo_password=env('GP5_DEMO_PASSWORD'),
        admin_login=env('GP5_ADMIN_LOGIN', 'admin'),
        var_dir=Path(env('GP5_VAR_DIR', str(ROOT / 'var'))),
        # 팀 규정 묶음 폴더(그 안의 source/…/….pdf 가 팀 DB regulation_files.storage_key) · 관리자 '지금 규정' 내려받기에 쓴다
        regulation_files_dir=Path(env('GP5_REGULATION_FILES_DIR', str(ROOT.parent / 'team_db' / 'regulations'))),
        openai_key=env('OPENAI_API_KEY'),
        openai_model=env('OPENAI_MODEL', 'gpt-6-luna'),
        # 규정 검색 임베딩: RunPod-Ollama·OpenAI 모드 공통(팀 합의 2026-10-26) · 팀 DB 벡터와 같은 모델이어야 한다
        openai_embed=env('OPENAI_EMBED_MODEL', 'text-embedding-3-small'),
        openai_base=env('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/'),
        openai_json=env('OPENAI_JSON_MODE', 'on').lower() != 'off',
        openai_vision=env('OPENAI_VISION_MODEL'),
        ollama_url=env('OLLAMA_BASE_URL').rstrip('/'),
        ollama_model=model,
        ollama_model_roadmap=env('OLLAMA_MODEL_ROADMAP') or model,
        # 규정 에이전트(사내 생활 도우미·안별 지원 조건): 진단·로드맵과 다른 작은 모델을 같은 Pod에 올려 쓴다(팀 논의 2026-10-29 · #33)
        ollama_model_regulation=env('OLLAMA_MODEL_REGULATION') or model,
        ollama_vision=env('OLLAMA_VISION_MODEL'),
        ollama_key=env('OLLAMA_API_KEY'),
        ollama_timeout=int(env('OLLAMA_TIMEOUT', '180') or 180),
        ollama_num_ctx=int(env('OLLAMA_NUM_CTX', '0') or 0),
        ollama_keep_alive=env('OLLAMA_KEEP_ALIVE'),
        # 생각(thinking) 모드: off 면 생각 없이 바로 답한다(qwen3.8 등은 기본이 켜짐 · 응답이 길어져 느림)
        ollama_think=_on_off('OLLAMA_THINK'),
    )


S = load()
