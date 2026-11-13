"""서버 환경의 기본 키와 관리자가 등록한 제공자별 키."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from .config import Settings

Provider = Literal['openai', 'ollama']


@dataclass(frozen=True)
class Credential:
    value: str = field(repr=False)
    source: Literal['admin', 'env', 'none']


def _path(settings: Settings, provider: Provider) -> Path:
    filename = {'openai': 'openai', 'ollama': 'ollama'}[provider]
    return settings.var_dir / 'provider-keys' / filename


def read(settings: Settings, provider: Provider) -> Credential:
    try:
        value = _path(settings, provider).read_text(encoding='ascii')
    except FileNotFoundError:
        value = settings.openai_key if provider == 'openai' else settings.ollama_key
        return Credential(value, 'env' if value else 'none')
    return Credential(value, 'admin')


def save(settings: Settings, provider: Provider, value: str) -> None:
    _write(_path(settings, provider), value)


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # 같은 볼륨의 소유자 전용 임시 파일을 완성한 뒤 교체한다.
    tmp = NamedTemporaryFile(dir=path.parent, delete=False)
    staged = Path(tmp.name)
    try:
        with tmp:
            tmp.write(value.encode('ascii'))
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def reset(settings: Settings, provider: Provider) -> None:
    _path(settings, provider).unlink(missing_ok=True)


@dataclass(frozen=True)
class RunpodConnection:
    url: str
    key: Credential
    target: str
    managed: bool = False


def runpod(settings: Settings) -> RunpodConnection:
    path = _path(settings, 'ollama').with_name('runpod.json')
    try:
        record = json.loads(path.read_text(encoding='ascii'))
    except FileNotFoundError:
        return RunpodConnection(settings.ollama_url, read(settings, 'ollama'), settings.ollama_target)
    key = record['key']
    return RunpodConnection(record['url'], Credential(key, 'admin' if key else 'none'), 'runpod', True)


def save_runpod(settings: Settings, connection: RunpodConnection) -> None:
    # 하나의 파일을 교체해 다른 프로세스도 같은 Pod의 주소·키를 한 쌍으로 읽는다.
    _write(_path(settings, 'ollama').with_name('runpod.json'),
           json.dumps({'url': connection.url, 'key': connection.key.value}))


def reset_runpod(settings: Settings) -> None:
    _path(settings, 'ollama').with_name('runpod.json').unlink(missing_ok=True)
