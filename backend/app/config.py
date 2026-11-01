"""설정: 이 폴더의 .env 를 읽고(GP5_ENV_FILE 이 있으면 그 파일로 덮어씀), 같은 이름의 환경변수가 있으면 환경변수를 쓴다.

AWS 등에 올릴 때는 .env 파일 없이 환경변수(DATABASE_URL·키)만 넣으면 된다. 키·비밀번호는 화면(브라우저)으로 보내지 않는다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parent.parent
# 추론 정도 단계 이름(on·off·none·low·medium·high·xhigh 등 모델이 정한 이름). 화면에서 받은 값도 이 모양만 받는다
LEVEL_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,19}$')
# 켜고 끄기는 on·off 로만 적는다: true·false 를 단계 이름으로 보내면 Ollama 가 모르는 이름이라 모델 기본값(생각 켬)으로 돈다
BOOL_WORDS = ('true', 'false', 'yes', 'no', '1', '0')


def level_ok(v: str) -> bool:
    return bool(LEVEL_RE.match(v)) and v not in BOOL_WORDS


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
    openai_reasoning_levels: tuple[str, ...]  # 모델이 받는 reasoning_effort 단계(.env · 비면 기본 모델만 코드 값). 비면 화면에서 고르지 못한다
    openai_reasoning: str | None  # reasoning_effort 기본값. None 이면 보내지 않아 모델 기본값을 따른다
    openai_model_reasoning: str | None  # 보내지 않을 때 모델이 쓰는 기본값(화면 '기본값 · 보통' 표시용). 모르는 모델이면 None
    openai_roadmap_timeout: int  # 로드맵 생성·재생성·수정의 HTTP 대기 제한(초)
    # RunPod-Ollama
    ollama_url: str
    ollama_model: str  # 진단·로드맵
    ollama_model_regulation: str  # 규정 에이전트(사내 생활 도우미·안별 지원 조건)
    ollama_vision: str
    ollama_key: str
    ollama_timeout: int
    ollama_num_ctx: int
    ollama_keep_alive: str
    ollama_think: str | None  # 추론 정도 기본값(on·off 또는 모델의 단계 이름). None 이면 think 를 보내지 않아 모델 기본값을 따른다

    @property
    def ollama_target(self) -> str:
        host = urlparse(self.ollama_url).hostname or ''
        return 'runpod' if host.endswith('runpod.net') else 'local' if host in ('127.0.0.1', 'localhost', '::1') else 'remote'


# RunPod-Ollama 기본 모델: 팀이 파인튜닝한 두 모델(팀 결정 2026-10-29 · #33). Pod 에서 허깅페이스 모델을 받아
# 채팅 형식(renderer·parser)을 붙여 만든 이름이다(backend/RunPod_Ollama_연결_절차.md 2-4). .env 의 모델 줄은 원본 Qwen 과 비교할 때만 적는다
OLLAMA_TEAM_MODEL = 'growpath-27b'  # 진단·로드맵 · hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4
OLLAMA_TEAM_REGULATION_MODEL = 'growpath-regulation-4b'  # 규정 에이전트 · hf.co/golddragon0926/qwen35-4b-diagnosis-agent
# 규정 에이전트는 생각(추론)을 끄고 학습한 모델이라 늘 끄고 부른다. 화면(직원)·.env 의 추론 정도로 바꾸지 않는다(사용자 결정 2026-10-29 · #28)
OLLAMA_REGULATION_THINK = 'off'

# OpenAI 기본 모델(OPENAI_MODEL 코드 기본값)의 추론 정도. OpenAI 는 모델이 받는 단계·기본값을 알려 주는 API 가 없어 확인한 값을 둔다:
# gpt-6-luna 는 Chat Completions 에서 none~xhigh(모델 문서의 max 는 400 · 2026-10-28 실제 호출 오류), 기본 medium(모델 문서)
OPENAI_DEFAULT_MODEL = 'gpt-6-luna'
OPENAI_DEFAULT_LEVELS = ('none', 'low', 'medium', 'high', 'xhigh')
OPENAI_DEFAULT_MODEL_REASONING = 'medium'


def _level(key: str) -> str | None:
    """추론 정도 설정: 비우면 None. 단계 이름 모양이 아니면(오타 등) 시작할 때 멈춘다.
    Ollama 단계는 모델마다 달라 이름 목록으로는 확인하지 못한다 — 모델이 모르는 이름이면 Ollama 가 모델 기본값을 쓴다"""
    v = env(key).strip().lower()
    if v and not level_ok(v):
        raise ValueError(f'{key} 값은 on, off 또는 모델의 추론 단계 이름(low, medium, high 등)이거나 비워 두어야 해요 (지금: {v})')
    return v or None


def _levels(key: str) -> tuple[str, ...]:
    """쉼표로 적은 단계 목록(순서대로 화면에 보임)"""
    out = tuple(dict.fromkeys(x.strip().lower() for x in env(key).split(',') if x.strip()))
    bad = [x for x in out if not level_ok(x)]
    if bad:
        raise ValueError(f'{key} 에 단계 이름이 아닌 값이 있어요: {", ".join(bad)}')
    return out


def load() -> Settings:
    # OpenAI 는 모델이 받는 단계를 알려 주는 API 가 없다: 기본 모델(gpt-6-luna)은 코드의 확인한 값, 다른 모델은 .env 에 적는다.
    # 기본값이 그 목록 밖이면 호출마다 400 이라 시작할 때 멈춘다
    openai_model = env('OPENAI_MODEL', OPENAI_DEFAULT_MODEL)
    known = openai_model == OPENAI_DEFAULT_MODEL
    openai_levels = _levels('OPENAI_REASONING_LEVELS') or (OPENAI_DEFAULT_LEVELS if known else ())
    openai_reasoning = _level('OPENAI_REASONING_EFFORT')
    if openai_reasoning and openai_levels and openai_reasoning not in openai_levels:
        raise ValueError(f'OPENAI_REASONING_EFFORT({openai_reasoning})가 OPENAI_REASONING_LEVELS 목록에 없어요')
    try:
        roadmap_timeout = int(env('OPENAI_ROADMAP_TIMEOUT', '180'))
    except ValueError as exc:
        raise ValueError('OPENAI_ROADMAP_TIMEOUT은 1~600 사이의 정수(초)여야 해요') from exc
    if not 1 <= roadmap_timeout <= 600:
        raise ValueError('OPENAI_ROADMAP_TIMEOUT은 1~600 사이의 정수(초)여야 해요')
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
        openai_model=openai_model,
        # 규정 검색 임베딩: RunPod-Ollama·OpenAI 모드 공통(팀 합의 2026-10-26) · 팀 DB 벡터와 같은 모델이어야 한다
        openai_embed=env('OPENAI_EMBED_MODEL', 'text-embedding-3-small'),
        openai_base=env('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/'),
        openai_json=env('OPENAI_JSON_MODE', 'on').lower() != 'off',
        openai_vision=env('OPENAI_VISION_MODEL'),
        openai_reasoning_levels=openai_levels,
        openai_reasoning=openai_reasoning,
        openai_model_reasoning=OPENAI_DEFAULT_MODEL_REASONING if known else None,
        openai_roadmap_timeout=roadmap_timeout,
        ollama_url=env('OLLAMA_BASE_URL').rstrip('/'),
        ollama_model=env('OLLAMA_MODEL', OLLAMA_TEAM_MODEL),
        ollama_model_regulation=env('OLLAMA_MODEL_REGULATION', OLLAMA_TEAM_REGULATION_MODEL),
        # 팀 모델은 이미지 입력이 없어 비워 두면 RunPod-Ollama 모드는 기획서 이미지 읽기를 건너뛴다
        ollama_vision=env('OLLAMA_VISION_MODEL'),
        ollama_key=env('OLLAMA_API_KEY'),
        ollama_timeout=int(env('OLLAMA_TIMEOUT', '180') or 180),
        ollama_num_ctx=int(env('OLLAMA_NUM_CTX', '0') or 0),
        ollama_keep_alive=env('OLLAMA_KEEP_ALIVE'),
        # 생각(thinking) 모드·추론 정도: off 면 생각 없이 바로 답한다(qwen3.8 등은 기본이 켜짐 · 응답이 길어져 느림)
        ollama_think=_level('OLLAMA_THINK'),
    )


S = load()
