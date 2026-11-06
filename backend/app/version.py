"""저장소 VERSION을 API의 제품 버전으로 읽는다."""
from __future__ import annotations

import re
from pathlib import Path


VERSION_PATH = Path(__file__).resolve().parents[2] / 'VERSION'
_VERSION_PATTERN = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')


def read_project_version(path: Path = VERSION_PATH) -> str:
    """잘못된 배포에서 임의 버전을 표시하지 않고 시작을 중단한다."""
    try:
        version = path.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f'프로젝트 버전 파일을 읽을 수 없어요: {path}') from exc
    if not _VERSION_PATTERN.fullmatch(version):
        raise ValueError(f'프로젝트 버전은 앞자리 0 없는 X.Y.Z 형식이어야 해요: {path}')
    return version
