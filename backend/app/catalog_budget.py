"""후보와 전체 요청의 입력량을 로컬 토크나이저로 제한한다. 네트워크 호출 없음."""
from __future__ import annotations

import hashlib
from copy import deepcopy
import json
from functools import lru_cache
from pathlib import Path

from . import catalog_candidates as candidates
from .config import ROOT, env
from .browser_console import options

TOKENIZER_REVISION = '1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
TOKENIZER_SHA256 = '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
TOKENIZER_URL = f'https://huggingface.co/Qwen/Qwen3.8-27B/resolve/{TOKENIZER_REVISION}/tokenizer.json'
CATALOG_TOKENS = 5000
EXPANDED_CATALOG_TOKENS = 6000
INPUT_TOKENS = 11000
OUTPUT_RESERVE = 7000
# 입력에는 FRAMING_RESERVE 포함. 입력 11K·출력 7K와 안전 여유를 위한 20K 기준.
CONTEXT_RESERVE = 1024
DEFAULT_CONTEXT = 20480
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
    # runtime.llm_json(role='roadmap')와 같은 문자열을 센다. 문자열 내부 공백은 유지한다.
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, separators=(',', ':'))
    return len(_tokenizer(str(tokenizer_path())).encode(text, add_special_tokens=False).ids)


def _balanced(entries: list[dict], selection: candidates.Selection) -> list[dict]:
    required = set(selection.required)
    ordered = [row for row in entries if row['id'] in required]
    remaining = [row for row in entries if row['id'] not in required]
    codes = [f'S{i + 1}' for i in range(len(selection.skills))]
    counts = {code: sum(code in row['skills'] for row in ordered) for code in codes}
    while remaining:
        available = [code for code in codes if any(code in row['skills'] for row in remaining)]
        code = min(available, key=lambda value: counts[value]) if available else None
        index = next((i for i, row in enumerate(remaining) if code in row['skills']), 0)
        row = remaining.pop(index)
        ordered.append(row)
        for value in row['skills']:
            counts[value] += 1
    return ordered


def _compact(entries: list[dict], selection: candidates.Selection) -> list[dict]:
    """삭제 전에 발췌 수를 줄인다. 실제 단원 위치·시간·가격·불확실성은 보존한다."""
    rows = deepcopy(entries)
    for row in rows:
        evidence = row.get('curriculum') or []
        if len(evidence) > 1:
            strongest = max(evidence, key=lambda pair: candidates.matches(pair[1].casefold(), selection.terms))
            row['curriculum'] = [strongest]
            row['curriculumOmitted'] = max(0, len(selection.index[row['id']]['rows']) - 1)
    return rows


def pack(selection: candidates.Selection, system: str = '', payload: dict | None = None,
         context_limit: int = DEFAULT_CONTEXT) -> dict:
    """32개가 기본. 필수 자료가 많은 경우에만 40개를 먼저 검토한다.

    OpenAI에서도 같은 입력 비용 정책을 사용하지만 Qwen 계산값이 OpenAI의 과금 토큰 수는 아니다.
    요청 본문과 시스템 지시는 자르지 않는다. 필수 자료가 안 들어가면 명시적으로 실패한다.
    """
    limits = options.get()
    limit = min(limits.input_tokens or INPUT_TOKENS, (context_limit or DEFAULT_CONTEXT) - (limits.output_tokens or OUTPUT_RESERVE) - CONTEXT_RESERVE)
    base = deepcopy(payload or {})
    base.update(catalog=[], catalogSkillMap={f'S{i + 1}': s for i, s in enumerate(selection.skills)},
                catalogPolicy=GUIDE, catalogExcluded=selection.excluded,
                catalogDefaults={'kind': '강좌', 'timeStatus': 'confirmed', 'curriculumCoverage': 'public_outline'})
    system_tokens = tokens(system) + FRAMING_RESERVE
    if system_tokens + tokens(base) > limit:
        raise ValueError('기획서·기존 계획·요청 내용이 추천 입력량 한도를 넘습니다. 내용을 줄인 뒤 다시 요청해 주세요.')
    entries = _balanced([candidates.entry(r, selection) for r in selection.records[:candidates.MAX_COUNT]], selection)
    required_count = len(selection.required)
    if not set(selection.required).issubset({row['id'] for row in entries}):
        raise ValueError('필수 자료가 후보에 없습니다. 선택 자료를 확인해 주세요.')

    def packed(rows: list[dict], compact: bool) -> dict:
        result = dict(base, catalog=rows)
        defaults = dict(base['catalogDefaults'])
        # 반복 메타데이터는 값이 모두 동일할 때만 한 번 전달한다.
        for key in ('timeStatus', 'curriculumCoverage', 'format', 'difficulty', 'durationKind', 'timeNote'):
            values = [row.get(key, defaults.get(key)) for row in rows]
            if values and values[0] is not None and all(value == values[0] for value in values):
                defaults[key] = values[0]
                rows = [{k: v for k, v in row.items() if k != key} for row in rows]
        result.update(catalog=rows, catalogDefaults=defaults,
                      catalogCounts={'available': len(selection.records), 'sent': len(rows),
                                     'perSkill': {f'S{i + 1}': sum(f'S{i + 1}' in row['skills'] for row in rows)
                                                  for i in range(len(selection.skills))},
                                     'evidence': 'compact' if compact else 'standard'})
        return result

    def fits(result: dict, budget: int) -> bool:
        return tokens(result['catalog']) <= budget and system_tokens + tokens(result) <= limit

    expanded = required_count > candidates.DEFAULT_COUNT
    target = min(candidates.MAX_COUNT if expanded else candidates.DEFAULT_COUNT, len(entries))
    budget = EXPANDED_CATALOG_TOKENS if expanded else CATALOG_TOKENS
    compact_entries = _compact(entries, selection)
    # 가능한 스킬마다 최소 한 후보를 유지한다. 희소 스킬을 예산 때문에 숨기지 않는다.
    available_codes = {code for row in entries for code in row['skills']}
    for count in range(target, max(required_count, 1 if entries else 0) - 1, -1):
        if expanded and count <= candidates.DEFAULT_COUNT and required_count <= candidates.DEFAULT_COUNT:
            budget = CATALOG_TOKENS
        for source, compact in ((entries, False), (compact_entries, True)):
            rows = source[:count]
            if {code for row in rows for code in row['skills']} != available_codes:
                continue
            result = packed(rows, compact)
            if fits(result, budget):
                return result
    raise ValueError('선택 자료와 스킬별 추천 근거가 입력량 한도에 들어가지 않습니다. 자료나 요청 내용을 줄여 주세요.')
