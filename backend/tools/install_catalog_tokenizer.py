"""고정된 공개 토크나이저만 설치한다. 모델 가중치·추론 API는 사용하지 않는다."""
import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalog_budget import TOKENIZER_SHA256, TOKENIZER_URL, tokenizer_path


def main() -> None:
    path = tokenizer_path()
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == TOKENIZER_SHA256:
        print('후보 입력량 검사 토크나이저: 고정 버전 확인')
        return
    with urllib.request.urlopen(TOKENIZER_URL, timeout=60) as response:
        content = response.read(20_000_001)
    if len(content) > 20_000_000 or hashlib.sha256(content).hexdigest() != TOKENIZER_SHA256:
        raise ValueError('토크나이저 크기 또는 SHA-256 검증 실패')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.download')
    temporary.write_bytes(content)
    temporary.replace(path)
    print('후보 입력량 검사 토크나이저 설치 완료; 가중치/추론 호출 없음')


if __name__ == '__main__':
    main()
