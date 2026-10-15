"""목업 실행에 필요한 로컬 파일과 설치 상태만 확인한다. 자동 설치·외부 연결 없음."""
from __future__ import annotations

from html.parser import HTMLParser
from importlib import import_module, metadata
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
PACKAGES = {'pypdf': 'pypdf', 'olefile': 'olefile', 'Pillow': 'PIL.Image'}


class AssetLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        if tag not in ('script', 'link'):
            return
        for key, value in attrs:
            if key in ('src', 'href') and value and value.startswith('assets/'):
                self.paths.add(value)


def main() -> int:
    failures = []
    print('GrowPath 목업 실행환경 확인')
    version = sys.version_info
    if version < (3, 10):
        failures.append('Python 3.10 이상이 필요합니다. Python 3.12를 권장합니다.')
    else:
        print(f'[확인] Python {version.major}.{version.minor}.{version.micro} (권장: 3.12)')

    for name in ('index.html', 'server.py', 'docread.py', 'requirements.txt'):
        if not (ROOT / name).is_file():
            failures.append(f'필수 파일이 없습니다: {name}')
    if not (ROOT / 'assets').is_dir():
        failures.append('필수 폴더가 없습니다: assets/')
    if (ROOT / 'index.html').is_file():
        try:
            links = AssetLinks()
            links.feed((ROOT / 'index.html').read_text(encoding='utf-8'))
            missing = sorted(name for name in links.paths if not (ROOT / name).is_file())
            failures.extend(f'화면 파일이 없습니다: {name}' for name in missing)
            if not missing:
                print(f'[확인] index.html의 로컬 화면 파일 {len(links.paths)}개')
        except (OSError, UnicodeError):
            failures.append('index.html을 UTF-8로 읽을 수 없습니다.')

    try:
        requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError):
        requirements = ''
        failures.append('requirements.txt를 읽을 수 없습니다.')
    for package, module in PACKAGES.items():
        match = re.search(r'^' + re.escape(package) + r'==([^\s#]+)', requirements, re.MULTILINE | re.IGNORECASE)
        if not match:
            failures.append(f'requirements.txt의 {package} 고정 버전을 확인하세요.')
            continue
        expected = match.group(1)
        try:
            installed = metadata.version(package)
            import_module(module)
        except (metadata.PackageNotFoundError, ImportError, OSError):
            failures.append(f'{package}=={expected} 설치 또는 불러오기에 실패했습니다.')
            continue
        if installed != expected:
            failures.append(f'{package} 버전 불일치: 설치 {installed}, 필요 {expected}')
        else:
            print(f'[확인] {package}=={installed}')

    # 원본 server.py와 같이 .env를 읽되 설정값·모델 주소·키를 출력하지 않는다.
    settings = {}
    env_file = ROOT / '.env'
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    settings[key.strip()] = value.strip().strip('"').strip("'")
        except (OSError, UnicodeError):
            failures.append('.env를 읽을 수 없습니다. UTF-8 형식과 읽기 권한을 확인하세요.')
    for key, label in (('OLLAMA_BASE_URL', 'Ollama'), ('OPENAI_API_KEY', 'OpenAI')):
        configured = bool(os.environ.get(key) or settings.get(key))
        print(f'[선택] {label}: {"설정 있음" if configured else "미설정"} (연결·모델 동작은 확인하지 않음)')
    print('[안내] .env와 AI 설정 없이도 가데이터로 화면 목업을 실행할 수 있습니다.')

    if failures:
        for message in failures:
            print(f'[필요] {message}')
        print('의존성 설치: python -m pip install -r requirements.txt')
        return 1
    print('[완료] 로컬 실행환경 확인 완료. python server.py --open-browser 로 실행하세요.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
