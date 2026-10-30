"""후보와 전체 요청의 입력량을 로컬 토크나이저로 제한한다. 네트워크 호출 없음."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from . import catalog_candidates as candidates
from .config import ROOT, env

TOKENIZER_REVISION = '1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
TOKENIZER_SHA256 = '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
TOKENIZER_URL = f'https://huggingface.co/Qwen/Qwen3.8-27B/resolve/{TOKENIZER_REVISION}/tokenizer.json'
CATALOG_TOKENS = 5000
EXPANDED_CATALOG_TOKENS = 6000
INPUT_TOKENS = 10000
OUTPUT_RESERVE = 4096
CONTEXT_RESERVE = 2048
FRAMING_RESERVE = 128
GUIDE = ('catalog의 생략된 필드는 catalogDefaults를 따른다. skills는 catalogSkillMap의 스킬 코드다. '
         'curriculum은 [저장된 단원의 0부터 시작하는 위치, 원문 발췌] 쌍의 배열이다. '
         'content는 소개의 원문 발췌다. curriculumCoverage가 description_only이면 목차를 확보하지 못했다. '
         '모든 근거는 일부 발췌이며 전체 커리큘럼으로 간주하지 않는다. 선수지식·수강대상은 학습 성과가 아니다. '
         'evidenceStatus가 unavailable이면 세부 학습 내용을 추정하지 않는다. '
         'format이 없으면 학습 형식이 확인되지 않았다. '
         'catalogExcluded는 이 안의 무료 조건으로 제외한 자료이므로 사용하지 않는다.')


def tokenizer_path() -> Path:
    return Path(env('ROADMAP_TOKENIZER_PATH', str(ROOT / 'tokenizer_assets' / 'qwen38.json')))


@lru_cache(maxsize=1)
def _tokenizer(path: str):
    from tokenizers import Tokenizer
    source = Path(path)
    if not source.is_file():
        raise ValueError('추천 입력량 검사 파일이 없습니다. backend에서 python tools/install_catalog_tokenizer.py를 실행해 주세요.')
    if hashlib.sha256(source.read_bytes()).hexdigest() != TOKENIZER_SHA256:
        raise ValueError('추천 입력량 검사 파일의 해시가 다릅니다. 고정 버전 토크나이저를 다시 설치해 주세요.')
    return Tokenizer.from_file(str(source))


def tokens(value) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return len(_tokenizer(str(tokenizer_path())).encode(text, add_special_tokens=False).ids)


def pack(selection: candidates.Selection, system: str = '', payload: dict | None = None,
         context_limit: int = 16384) -> dict:
    """32개가 기본. 스킬 4~5개 또는 필수 자료가 많은 경우에만 40개를 먼저 검토한다.

    OpenAI에서도 같은 입력 비용 정책을 사용하지만 Qwen 계산값이 OpenAI의 과금 토큰 수는 아니다.
    요청 본문과 시스템 지시는 자르지 않는다. 필수 자료가 안 들어가면 명시적으로 실패한다.
    """
    limit = min(INPUT_TOKENS, min(context_limit or 16384, 16384) - OUTPUT_RESERVE - CONTEXT_RESERVE)
    base = dict(payload or {})
    base.update(catalog=[], catalogSkillMap={f'S{i + 1}': s for i, s in enumerate(selection.skills)},
                catalogPolicy=GUIDE, catalogExcluded=selection.excluded,
                catalogDefaults={'kind': '강좌', 'timeStatus': 'confirmed', 'curriculumCoverage': 'public_outline'})
    system_tokens = tokens(system) + FRAMING_RESERVE
    if system_tokens + tokens(base) > limit:
        raise ValueError('기획서·기존 계획·요청 내용이 추천 입력량 한도를 넘습니다. 내용을 줄인 뒤 다시 요청해 주세요.')
    entries = [candidates.entry(r, selection) for r in selection.records[:candidates.MAX_COUNT]]
    required_count = len(selection.required)

    def fits(count: int, budget: int) -> bool:
        rows = entries[:count]
        return tokens(rows) <= budget and system_tokens + tokens(dict(base, catalog=rows)) <= limit

    expanded = len(selection.skills) >= 4 or required_count > candidates.DEFAULT_COUNT
    target = min(candidates.MAX_COUNT if expanded else candidates.DEFAULT_COUNT, len(entries))
    budget = EXPANDED_CATALOG_TOKENS if expanded else CATALOG_TOKENS
    if expanded and not fits(target, budget) and required_count <= candidates.DEFAULT_COUNT:
        target, budget = min(candidates.DEFAULT_COUNT, len(entries)), CATALOG_TOKENS
    while target >= required_count and not fits(target, budget):
        target -= 1
    if target < required_count or (entries and target == 0):
        raise ValueError('선택 자료와 추천 근거가 입력량 한도에 들어가지 않습니다. 자료나 요청 내용을 줄여 주세요.')
    base['catalog'] = entries[:target]
    return base
